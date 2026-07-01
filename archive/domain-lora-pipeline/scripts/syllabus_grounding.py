"""Fuzzy grounding checks for syllabus extraction and training generation."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def quote_in_source(quote: str, source_text: str, threshold: float = 0.85) -> bool:
    """Return True if quote fuzzy-matches a substring of source_text."""
    quote_norm = normalize_text(quote)
    if len(quote_norm) < 4:
        return False

    source_norm = normalize_text(source_text)
    if quote_norm in source_norm:
        return True

    # Sliding window by quote length (stepped for long sources)
    window = len(quote_norm)
    if window > len(source_norm):
        return similarity(quote_norm, source_norm) >= threshold

    step = max(1, window // 4)
    best = 0.0
    for start in range(0, len(source_norm) - window + 1, step):
        chunk = source_norm[start : start + window]
        best = max(best, SequenceMatcher(None, quote_norm, chunk).ratio())
        if best >= threshold:
            return True

    return best >= threshold


def is_grounded(quote: str, source_text: str, threshold: float = 0.85) -> bool:
    return quote_in_source(quote, source_text, threshold=threshold)


def filter_grounded_strings(
    items: list[str],
    source_text: str,
    threshold: float = 0.85,
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for item in items:
        if is_grounded(item, source_text, threshold=threshold):
            kept.append(item)
        else:
            dropped.append(item)
    return kept, dropped
