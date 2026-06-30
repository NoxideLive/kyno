"""Label balance helpers and off_topic top-up for domain training data."""

from __future__ import annotations

import math
from typing import Any

from domain_generation import generate_global_off_topic


def label_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"on_topic": 0, "off_topic": 0}
    for row in rows:
        label = row.get("label")
        if label in counts:
            counts[label] += 1
    return counts


def off_topic_deficit(rows: list[dict], target_ratio: float = 0.5) -> int:
    """How many off_topic rows to add so off / total >= target_ratio."""
    counts = label_counts(rows)
    on_n = counts["on_topic"]
    off_n = counts["off_topic"]
    total = on_n + off_n
    if total == 0:
        return 0
    current_ratio = off_n / total
    if current_ratio >= target_ratio:
        return 0
    # off_n + x >= target_ratio * (total + x)
    # x * (1 - target_ratio) >= target_ratio * total - off_n
    needed = math.ceil((target_ratio * total - off_n) / (1 - target_ratio))
    return max(0, needed)


def top_up_off_topic(
    rows: list[dict],
    *,
    model: str,
    domain_spec: str,
    target_ratio: float = 0.5,
    hard_off_ratio: float = 0.7,
    buffer_ratio: float = 0.1,
) -> tuple[list[dict], dict[str, Any]]:
    """Append Groq-generated off_topic rows until target ratio is met (pre-dedupe)."""
    deficit = off_topic_deficit(rows, target_ratio=target_ratio)
    if deficit == 0:
        return rows, {"global_off_topup": 0, "deficit_before": 0}

    request_count = max(deficit, int(math.ceil(deficit * (1 + buffer_ratio))))
    generated = generate_global_off_topic(
        model=model,
        count=request_count,
        domain_spec=domain_spec,
        hard_off_ratio=hard_off_ratio,
    )
    merged = list(rows) + generated
    return merged, {
        "global_off_topup": len(generated),
        "deficit_before": deficit,
        "requested": request_count,
        "label_counts_after_topup": label_counts(merged),
    }
