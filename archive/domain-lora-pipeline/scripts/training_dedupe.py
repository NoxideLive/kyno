"""Lexical deduplication for domain training rows (per label)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip("?.!")
    return text


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard_similarity(a: str, b: str) -> float:
    na = _char_ngrams(normalize_text(a))
    nb = _char_ngrams(normalize_text(b))
    if not na or not nb:
        return 0.0
    return len(na & nb) / len(na | nb)


def similarity_score(a: str, b: str) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0
    short_word_count = min(len(a_norm.split()), len(b_norm.split()))
    if short_word_count <= 6:
        return SequenceMatcher(None, a_norm, b_norm).ratio()
    return jaccard_similarity(a_norm, b_norm)


def dedupe_training_rows(
    rows: list[dict],
    *,
    threshold: float = 0.88,
) -> tuple[list[dict], dict]:
    """Dedupe within each label bucket. Curated rows should be listed first."""
    stats = {
        "input": len(rows),
        "exact_removed": 0,
        "lexical_removed": 0,
        "output": 0,
        "by_label": {},
    }

    by_label: dict[str, list[dict]] = {"on_topic": [], "off_topic": []}
    for row in rows:
        label = row.get("label")
        if label in by_label:
            by_label[label].append(row)

    result: list[dict] = []
    for label, bucket in by_label.items():
        kept: list[dict] = []
        seen_exact: set[str] = set()

        for row in bucket:
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            norm = normalize_text(text)
            if norm in seen_exact:
                stats["exact_removed"] += 1
                continue
            seen_exact.add(norm)

            duplicate = False
            for existing in kept:
                if similarity_score(text, str(existing.get("text", ""))) >= threshold:
                    duplicate = True
                    stats["lexical_removed"] += 1
                    break
            if not duplicate:
                kept.append(row)

        stats["by_label"][label] = {
            "input": len(bucket),
            "output": len(kept),
        }
        result.extend(kept)

    stats["output"] = len(result)
    return result, stats
