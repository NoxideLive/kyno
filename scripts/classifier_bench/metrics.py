"""Bench metrics and report builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CaseResult:
    id: str
    suite: str
    label: str
    text: str
    expected: str
    actual: str
    confidence: float | None
    block_reason: str | None
    ok: bool
    meta: dict


def confusion_for_label(results: list[CaseResult], positive_label: str) -> dict[str, int]:
    tp = fp = tn = fn = 0
    for result in results:
        expected_pos = result.label == positive_label
        actual_pos = result.actual == positive_label
        if expected_pos and actual_pos:
            tp += 1
        elif expected_pos and not actual_pos:
            fn += 1
        elif not expected_pos and actual_pos:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def metrics_from_counts(counts: dict[str, int]) -> dict[str, float]:
    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def build_report(
    *,
    gateway_url: str,
    workers: int,
    label_counts: dict[str, dict[str, int]],
    results: list[CaseResult],
    elapsed_sec: float,
) -> dict[str, Any]:
    by_suite: dict[str, list[CaseResult]] = {}
    for result in results:
        by_suite.setdefault(result.suite, []).append(result)

    suite_summaries: dict[str, Any] = {}
    for suite, suite_results in by_suite.items():
        labels = sorted({r.label for r in suite_results})
        label_metrics: dict[str, Any] = {}
        for label in labels:
            counts = confusion_for_label(suite_results, label)
            label_metrics[label] = {**counts, **metrics_from_counts(counts)}
        passed = sum(1 for r in suite_results if r.ok)
        suite_summaries[suite] = {
            "cases": len(suite_results),
            "passed": passed,
            "failed": len(suite_results) - passed,
            "labels": label_counts.get(suite, {}),
            "metrics": label_metrics,
        }

    failures = [
        {
            "id": r.id,
            "suite": r.suite,
            "label": r.label,
            "text": r.text,
            "expected": r.expected,
            "actual": r.actual,
            "confidence": r.confidence,
            "block_reason": r.block_reason,
            "meta": r.meta,
        }
        for r in results
        if not r.ok
    ]

    total = len(results)
    passed = sum(1 for r in results if r.ok)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gateway_url": gateway_url,
        "workers": workers,
        "elapsed_sec": round(elapsed_sec, 2),
        "cases_per_sec": round(total / elapsed_sec, 2) if elapsed_sec > 0 else 0.0,
        "totals": {"cases": total, "passed": passed, "failed": total - passed},
        "suites": suite_summaries,
        "failures": failures,
    }
