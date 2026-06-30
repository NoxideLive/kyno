"""Structured Groq generation and validation for domain training data."""

from __future__ import annotations

import json
import re
from typing import Any

from caps_chunker import combined_grounding_text
from groq_client import chat_json
from syllabus_chunker import SyllabusChunk
from syllabus_grounding import is_grounded

# ATP section headings — not user chat queries
ATP_HEADER_DENYLIST = frozenset(
    {
        "topics",
        "topic",
        "supporting",
        "diagnostic",
        "consolidation",
        "endline",
        "baseline",
        "introduction",
        "revision",
        "assessment",
        "overview",
    }
)

GENERATE_SYSTEM = """You generate user chat messages for a CAPS Mathematics domain classifier (Grades 1–12).
Output JSON only with three arrays:
  short_on_topic: objects with text (1–3 words), source_quote (optional), style "short"
  on_topic: objects with text, source_quote (verbatim from ATP chunk or CAPS context), style (teacher|learner|meta|afrikaans)
  off_topic: objects with text, style "hard_boundary" or "easy" (no source_quote)

Rules:
- short_on_topic text MUST be 1–3 words, a topic/skill from the extracted list or source text.
- All on_topic rows MUST include source_quote copied from the ATP chunk or CAPS context block.
- off_topic hard_boundary (~70%): Mathematical Literacy, other CAPS subjects, IB/Cambridge, homographs (Caps = capitalization), Physical Sciences, Geography, Accounting, peanuts jokes.
- off_topic easy (~30%): weather, coding, sports, unrelated trivia.
- Do not put maths source quotes in off_topic messages."""

OFF_TOPIC_SYSTEM = """You generate off_topic user messages for a CAPS Mathematics domain classifier.
Output JSON: {"off_topic": [{"text": "...", "style": "hard_boundary" | "easy"}]}

hard_boundary (domain-adjacent, out of scope):
- Other CAPS subjects (Life Orientation, Natural Sciences, History, Geography, Languages)
- Mathematical Literacy (FET — not Mathematics)
- IB Mathematics, Cambridge IGCSE, university maths modules
- Homographs: Caps/caps meaning capitalization, not the curriculum
- Physical Sciences or Accounting questions using maths vocabulary
- Grade N History/CAPS essay, Geography map work

easy (clearly unrelated):
- Weather, coding, relationship advice, sports, entertainment

Do not generate on_topic CAPS Mathematics questions."""


def chunk_example_counts(
    examples_per_week: int,
    on_off_ratio: float,
    min_short_per_chunk: int,
    *,
    hard_off_ratio: float = 0.7,
) -> dict[str, int]:
    on_count = max(1, round(examples_per_week * on_off_ratio))
    on_count = min(on_count, examples_per_week - 1) if examples_per_week > 1 else 1
    off_count = max(0, examples_per_week - on_count)
    short_count = min(min_short_per_chunk, on_count)
    other_on_count = max(0, on_count - short_count)
    hard_off = round(off_count * hard_off_ratio) if off_count else 0
    easy_off = max(0, off_count - hard_off)
    return {
        "on_count": on_count,
        "off_count": off_count,
        "short_count": short_count,
        "other_on_count": other_on_count,
        "hard_off_count": hard_off,
        "easy_off_count": easy_off,
    }


def build_chunk_user_prompt(
    *,
    domain_spec: str,
    chunk: SyllabusChunk,
    week_data: dict[str, Any],
    counts: dict[str, int],
    caps_excerpt: str = "",
) -> str:
    caps_block = ""
    if caps_excerpt.strip():
        caps_block = f"\nCAPS context for this grade/week:\n{caps_excerpt[:4000]}\n"

    content_area = week_data.get("content_area", "")
    short_phrases = week_data.get("short_phrases", [])

    return (
        f"{domain_spec}\n\n"
        f"Grade: {chunk.grade}, Term: {chunk.term}, Week: {chunk.week}\n"
        f"Extracted topics: {json.dumps(week_data.get('topics', []))}\n"
        f"Extracted skills: {json.dumps(week_data.get('skills', []))}\n"
        f"Content area: {content_area}\n"
        f"Short phrases: {json.dumps(short_phrases)}\n\n"
        f"Return exactly {counts['short_count']} short_on_topic (1–3 words each), "
        f"{counts['other_on_count']} other on_topic, "
        f"{counts['hard_off_count']} off_topic hard_boundary, "
        f"and {counts['easy_off_count']} off_topic easy.\n"
        f"ATP chunk text:\n{chunk.text[:10000]}"
        f"{caps_block}"
    )


def parse_structured_generation(raw: dict[str, Any]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {
        "short_on_topic": [],
        "on_topic": [],
        "off_topic": [],
    }
    for bucket in result:
        items = raw.get(bucket, [])
        if isinstance(items, list):
            result[bucket] = [ex for ex in items if isinstance(ex, dict)]
    return result


def word_count(text: str) -> int:
    return len(text.split())


def normalize_label_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def is_atp_header_junk(text: str) -> bool:
    normalized = normalize_label_text(text)
    if normalized in ATP_HEADER_DENYLIST:
        return True
    words = normalized.split()
    return len(words) <= 2 and normalized in ATP_HEADER_DENYLIST


def short_matches_week_lists(text: str, week_data: dict[str, Any]) -> bool:
    """True if short text aligns with extracted short_phrases, topics, or skills."""
    normalized = normalize_label_text(text)
    if not normalized or word_count(text) > 3:
        return False

    candidates: list[str] = []
    for key in ("short_phrases", "topics", "skills"):
        for item in week_data.get(key, []):
            item_norm = normalize_label_text(str(item))
            if not item_norm:
                continue
            candidates.append(item_norm)
            first_token = item_norm.split(":")[0].split("—")[0].strip()
            if first_token and first_token not in candidates:
                candidates.append(first_token)

    for candidate in candidates:
        if normalized == candidate:
            return True
        if len(normalized.split()) <= 3 and (
            normalized in candidate or candidate.startswith(normalized)
        ):
            return True
    return False


def fill_short_on_topic_quota(
    week_data: dict[str, Any],
    *,
    grade: int,
    kept: list[dict],
    min_short_per_chunk: int,
) -> tuple[list[dict], int]:
    """Synthesize short on_topic rows from extracted phrases when LLM quota is unmet."""
    current_short = sum(
        1
        for row in kept
        if row.get("label") == "on_topic" and word_count(str(row.get("text", ""))) <= 3
    )
    if current_short >= min_short_per_chunk:
        return kept, 0

    existing = {normalize_label_text(str(r.get("text", ""))) for r in kept}
    added = 0
    deficit = min_short_per_chunk - current_short

    phrase_sources: list[str] = []
    for key in ("short_phrases", "topics", "skills"):
        for item in week_data.get(key, []):
            clean = str(item).strip()
            if not clean:
                continue
            short = clean.split(":")[0].split("—")[0].strip()
            for candidate in (clean, short):
                if candidate and word_count(candidate) <= 3:
                    phrase_sources.append(candidate)

    templates = [
        lambda p: p,
        lambda p: f"Grade {grade} {p}",
        lambda p: f"help with {p}",
    ]

    for phrase in phrase_sources:
        if added >= deficit:
            break
        for tmpl in templates:
            text = tmpl(phrase)
            if word_count(text) > 3:
                continue
            norm = normalize_label_text(text)
            if norm in existing or is_atp_header_junk(text):
                continue
            kept.append({"text": text, "label": "on_topic"})
            existing.add(norm)
            added += 1
            if added >= deficit:
                break

    return kept, added


def validate_example(
    ex: dict[str, Any],
    *,
    bucket: str,
    chunk_text: str,
    ground_threshold: float,
    week_data: dict[str, Any] | None = None,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    text = str(ex.get("text", "")).strip()
    if not text:
        return None, {"text": text, "reason": "empty_text", "bucket": bucket}

    if bucket in ("short_on_topic", "on_topic") and is_atp_header_junk(text):
        return None, {"text": text, "reason": "atp_header_junk", "bucket": bucket}

    style = str(ex.get("style", "")).lower()
    quote = str(ex.get("source_quote", "")).strip()
    week = week_data or {}

    if bucket == "short_on_topic":
        if word_count(text) > 3:
            return None, {"text": text, "reason": "short_too_long", "bucket": bucket}
        if style and style != "short":
            return None, {"text": text, "reason": "short_wrong_style", "bucket": bucket}
        grounded_quote = quote and is_grounded(quote, chunk_text, threshold=ground_threshold)
        if grounded_quote or short_matches_week_lists(text, week):
            return {"text": text, "label": "on_topic"}, None
        return None, {
            "text": text,
            "reason": "ungrounded_short",
            "quote": quote,
            "bucket": bucket,
        }

    if bucket == "on_topic":
        if style == "short":
            return None, {"text": text, "reason": "short_in_wrong_bucket", "bucket": bucket}
        if not quote or not is_grounded(quote, chunk_text, threshold=ground_threshold):
            return None, {
                "text": text,
                "reason": "ungrounded_quote",
                "quote": quote,
                "bucket": bucket,
            }
        return {"text": text, "label": "on_topic"}, None

    if bucket == "off_topic":
        if quote and is_grounded(quote, chunk_text, threshold=ground_threshold):
            return None, {"text": text, "reason": "off_topic_quoted_chunk", "bucket": bucket}
        if style and style not in ("hard_boundary", "hard_negative", "easy"):
            return None, {"text": text, "reason": "off_topic_wrong_style", "bucket": bucket}
        return {"text": text, "label": "off_topic"}, None

    return None, {"text": text, "reason": "unknown_bucket", "bucket": bucket}


def validate_chunk_generation(
    parsed: dict[str, list[dict]],
    *,
    chunk_text: str,
    ground_threshold: float,
    min_short_per_chunk: int,
    week_data: dict[str, Any],
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    kept: list[dict] = []
    dropped: list[dict] = []
    short_kept = 0
    on_kept = 0
    off_kept = 0

    for bucket, examples in parsed.items():
        for ex in examples:
            row, drop = validate_example(
                ex,
                bucket=bucket,
                chunk_text=chunk_text,
                ground_threshold=ground_threshold,
                week_data=week_data,
            )
            if row:
                kept.append(row)
                if bucket == "short_on_topic":
                    short_kept += 1
                elif bucket == "on_topic":
                    on_kept += 1
                else:
                    off_kept += 1
            elif drop:
                dropped.append(drop)

    kept, synthesized = fill_short_on_topic_quota(
        week_data,
        grade=int(week_data.get("grade", 0) or 0),
        kept=kept,
        min_short_per_chunk=min_short_per_chunk,
    )
    if synthesized:
        short_kept += synthesized

    short_kept = sum(
        1 for row in kept if row.get("label") == "on_topic" and word_count(str(row.get("text", ""))) <= 3
    )

    stats = {
        "short_requested": min_short_per_chunk,
        "short_kept": short_kept,
        "short_synthesized": synthesized,
        "on_kept": on_kept,
        "off_kept": off_kept,
        "short_quota_met": short_kept >= min_short_per_chunk,
    }
    return kept, dropped, stats


def count_short_on_topic(rows: list[dict]) -> int:
    return sum(
        1 for row in rows if row.get("label") == "on_topic" and word_count(str(row.get("text", ""))) <= 3
    )


def generate_examples_for_chunk(
    chunk: SyllabusChunk,
    week_data: dict[str, Any],
    *,
    model: str,
    examples_per_week: int,
    on_off_ratio: float,
    min_short_per_chunk: int,
    domain_spec: str,
    ground_threshold: float,
    hard_off_ratio: float = 0.7,
    caps_excerpt: str = "",
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    week_data = {**week_data, "grade": chunk.grade}
    counts = chunk_example_counts(
        examples_per_week,
        on_off_ratio,
        min_short_per_chunk,
        hard_off_ratio=hard_off_ratio,
    )
    user = build_chunk_user_prompt(
        domain_spec=domain_spec,
        chunk=chunk,
        week_data=week_data,
        counts=counts,
        caps_excerpt=caps_excerpt,
    )
    raw = chat_json(system=GENERATE_SYSTEM, user=user, model=model)
    parsed = parse_structured_generation(raw)
    grounding_text = combined_grounding_text(chunk.text, caps_excerpt)
    kept, dropped, stats = validate_chunk_generation(
        parsed,
        chunk_text=grounding_text,
        ground_threshold=ground_threshold,
        min_short_per_chunk=min_short_per_chunk,
        week_data=week_data,
    )
    stats["counts_requested"] = counts
    return kept, dropped, stats


def _parse_off_topic_response(raw: dict[str, Any]) -> list[dict]:
    kept: list[dict] = []
    items = raw.get("off_topic", raw.get("examples", []))
    if not isinstance(items, list):
        return kept
    for ex in items:
        if not isinstance(ex, dict):
            continue
        text = str(ex.get("text", "")).strip()
        label = ex.get("label", "off_topic")
        if text and label == "off_topic":
            kept.append({"text": text, "label": "off_topic"})
    return kept


def _off_topic_prompt_suffix(count: int, hard_off_ratio: float) -> str:
    hard = max(0, round(count * hard_off_ratio))
    easy = max(0, count - hard)
    return (
        f"Generate {count} off_topic messages: {hard} hard_boundary, {easy} easy. "
        'Output JSON: {"off_topic": [{"text": "...", "style": "hard_boundary" | "easy"}]}'
    )


def generate_grade_off_topic(
    grade: int,
    *,
    model: str,
    count: int,
    domain_spec: str,
    hard_off_ratio: float = 0.7,
) -> list[dict]:
    user = (
        f"{domain_spec}\n\n"
        f"Grade {grade} context.\n"
        f"{_off_topic_prompt_suffix(count, hard_off_ratio)}"
    )
    raw = chat_json(system=OFF_TOPIC_SYSTEM, user=user, model=model)
    return _parse_off_topic_response(raw)[:count]


def generate_global_off_topic(
    *,
    model: str,
    count: int,
    domain_spec: str,
    hard_off_ratio: float = 0.7,
) -> list[dict]:
    user = (
        f"{domain_spec}\n\n"
        f"Diverse Grades 1–12 context.\n"
        f"{_off_topic_prompt_suffix(count, hard_off_ratio)}"
    )
    raw = chat_json(system=OFF_TOPIC_SYSTEM, user=user, model=model)
    return _parse_off_topic_response(raw)[:count]
