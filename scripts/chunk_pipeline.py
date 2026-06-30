"""Per-chunk parallel processing for domain training data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from caps_chunker import caps_excerpt_for_week, match_content_area_name
from domain_generation import generate_examples_for_chunk
from groq_client import chat_json
from syllabus_chunker import SyllabusChunk
from syllabus_grounding import filter_grounded_strings

EXTRACT_SYSTEM = """You extract DBE CAPS Mathematics ATP structure from source text.
Output JSON only with keys:
  term (int), week (int), topics (string array), skills (string array),
  content_area (string — CAPS content area name),
  short_phrases (string array — 1–3 word topic phrases from the chunk),
  assessment_notes (string array — assessment/AFL/exam mentions).
Copy topic and skill phrases from the source text. Do not invent content not present in the source."""


@dataclass
class ChunkWorkContext:
    grade: int
    extract_model: str
    generate_model: str
    domain_spec: str
    phase_sections: dict[str, Any]
    caps_summary: dict[str, Any]
    examples_per_week: int
    on_off_ratio: float
    min_short_per_chunk: int
    ground_threshold: float
    hard_off_ratio: float = 0.7


@dataclass
class ChunkResult:
    chunk_index: int
    week_data: dict[str, Any]
    training_rows: list[dict]
    dropped: list[dict]
    short_stats: dict[str, Any]
    timing: dict[str, float]
    caps_matched: bool
    extract_error: str | None = None
    generate_error: str | None = None


def extract_week_from_chunk(
    chunk: SyllabusChunk,
    *,
    model: str,
    ground_threshold: float,
    content_area_names: list[str] | None = None,
) -> dict[str, Any]:
    user = (
        f"Grade: {chunk.grade}\n"
        f"Term: {chunk.term}\n"
        f"Week: {chunk.week}\n\n"
        f"ATP source text:\n{chunk.text[:12000]}"
    )
    raw = chat_json(system=EXTRACT_SYSTEM, user=user, model=model)
    topics = [str(t).strip() for t in raw.get("topics", []) if str(t).strip()]
    skills = [str(s).strip() for s in raw.get("skills", []) if str(s).strip()]
    short_phrases = [
        str(p).strip() for p in raw.get("short_phrases", []) if str(p).strip()
    ]
    assessment_notes = [
        str(n).strip() for n in raw.get("assessment_notes", []) if str(n).strip()
    ]

    topics, _ = filter_grounded_strings(topics, chunk.text, threshold=ground_threshold)
    skills, _ = filter_grounded_strings(skills, chunk.text, threshold=ground_threshold)
    short_phrases, _ = filter_grounded_strings(
        short_phrases, chunk.text, threshold=ground_threshold
    )
    short_phrases = [p for p in short_phrases if len(p.split()) <= 3]
    assessment_notes, _ = filter_grounded_strings(
        assessment_notes, chunk.text, threshold=ground_threshold
    )

    content_area = str(raw.get("content_area", "")).strip()
    if content_area_names:
        matched = match_content_area_name(content_area, content_area_names)
        content_area = matched or content_area

    return {
        "term": int(raw.get("term", chunk.term)),
        "week": int(raw.get("week", chunk.week)),
        "topics": topics,
        "skills": skills,
        "content_area": content_area,
        "short_phrases": short_phrases,
        "assessment_notes": assessment_notes,
    }


def empty_week_data(chunk: SyllabusChunk) -> dict[str, Any]:
    return {
        "term": chunk.term,
        "week": chunk.week,
        "topics": [],
        "skills": [],
        "content_area": "",
        "short_phrases": [],
        "assessment_notes": [],
        "caps_excerpt": "",
    }


def process_single_chunk(
    chunk_index: int,
    chunk: SyllabusChunk,
    ctx: ChunkWorkContext,
) -> ChunkResult:
    timing: dict[str, float] = {}
    week_data = empty_week_data(chunk)
    training_rows: list[dict] = []
    dropped: list[dict] = []
    short_stats: dict[str, Any] = {
        "short_requested": ctx.min_short_per_chunk,
        "short_kept": 0,
        "on_kept": 0,
        "off_kept": 0,
        "short_quota_met": False,
        "chunks_processed": 0,
    }
    extract_error: str | None = None
    generate_error: str | None = None
    caps_matched = False

    extract_start = time.monotonic()
    try:
        week_data = extract_week_from_chunk(
            chunk,
            model=ctx.extract_model,
            ground_threshold=ctx.ground_threshold,
            content_area_names=ctx.caps_summary.get("content_area_names", []),
        )
    except RuntimeError as exc:
        extract_error = str(exc)
        week_data = empty_week_data(chunk)
    timing["extract_ms"] = (time.monotonic() - extract_start) * 1000

    caps_start = time.monotonic()
    caps_excerpt, matched_area = caps_excerpt_for_week(
        ctx.phase_sections,
        ctx.grade,
        week_data.get("topics", []),
        week_data.get("skills", []),
    )
    timing["caps_ms"] = (time.monotonic() - caps_start) * 1000
    week_data["caps_excerpt"] = caps_excerpt
    if matched_area and not week_data.get("content_area"):
        week_data["content_area"] = matched_area
    caps_matched = bool(
        matched_area and (week_data.get("topics") or week_data.get("skills"))
    )

    if not week_data.get("topics") and not week_data.get("skills"):
        return ChunkResult(
            chunk_index=chunk_index,
            week_data=week_data,
            training_rows=training_rows,
            dropped=dropped,
            short_stats=short_stats,
            timing=timing,
            caps_matched=caps_matched,
            extract_error=extract_error,
            generate_error=generate_error,
        )

    generate_start = time.monotonic()
    try:
        kept, dropped, chunk_stats = generate_examples_for_chunk(
            chunk,
            week_data,
            model=ctx.generate_model,
            examples_per_week=ctx.examples_per_week,
            on_off_ratio=ctx.on_off_ratio,
            min_short_per_chunk=ctx.min_short_per_chunk,
            domain_spec=ctx.domain_spec,
            ground_threshold=ctx.ground_threshold,
            hard_off_ratio=ctx.hard_off_ratio,
            caps_excerpt=caps_excerpt,
        )
        training_rows = kept
        short_stats = chunk_stats
        short_stats["chunks_processed"] = 1
    except RuntimeError as exc:
        generate_error = str(exc)
    timing["generate_ms"] = (time.monotonic() - generate_start) * 1000

    return ChunkResult(
        chunk_index=chunk_index,
        week_data=week_data,
        training_rows=training_rows,
        dropped=dropped,
        short_stats=short_stats,
        timing=timing,
        caps_matched=caps_matched,
        extract_error=extract_error,
        generate_error=generate_error,
    )
