"""Case-level deltas, pattern counts, and accept/reject gates."""

from __future__ import annotations

from collections import Counter
from typing import Any

from compact_prompt_tune.analyze import _failure_pattern
from compact_prompt_tune.state import extract_key_metrics


def failure_ids(report: dict[str, Any]) -> set[str]:
    return {str(f["id"]) for f in report.get("failures", [])}


def pattern_counts(report: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for failure in report.get("failures", []):
        counts[_failure_pattern(failure)] += 1
    return counts


def compute_delta(
    prior_report: dict[str, Any],
    current_report: dict[str, Any],
) -> dict[str, Any]:
    prior_failures = {str(f["id"]): f for f in prior_report.get("failures", [])}
    current_failures = {str(f["id"]): f for f in current_report.get("failures", [])}

    prior_ids = set(prior_failures)
    current_ids = set(current_failures)

    fixed_ids = sorted(prior_ids - current_ids)
    regressed_ids = sorted(current_ids - prior_ids)
    still_failing_ids = sorted(prior_ids & current_ids)

    prior_patterns = pattern_counts(prior_report)
    current_patterns = pattern_counts(current_report)
    all_patterns = set(prior_patterns) | set(current_patterns)
    pattern_deltas = {
        p: current_patterns.get(p, 0) - prior_patterns.get(p, 0)
        for p in sorted(all_patterns)
    }

    prior_totals = prior_report.get("totals", {})
    current_totals = current_report.get("totals", {})

    prior_metrics = extract_key_metrics(prior_report)
    current_metrics = extract_key_metrics(current_report)
    key_metrics_delta = {
        k: round((current_metrics.get(k) or 0.0) - (prior_metrics.get(k) or 0.0), 4)
        for k in ("off_topic_recall", "jailbreak_recall", "switch_allowed_recall")
    }

    return {
        "passed_delta": int(current_totals.get("passed", 0)) - int(prior_totals.get("passed", 0)),
        "cases_delta": int(current_totals.get("cases", 0)) - int(prior_totals.get("cases", 0)),
        "fixed_ids": fixed_ids,
        "regressed_ids": regressed_ids,
        "still_failing_ids": still_failing_ids,
        "fixed_count": len(fixed_ids),
        "regressed_count": len(regressed_ids),
        "still_failing_count": len(still_failing_ids),
        "sample_fixed_ids": fixed_ids[:10],
        "sample_regressed_ids": regressed_ids[:10],
        "pattern_deltas": pattern_deltas,
        "key_metrics_delta": key_metrics_delta,
        "before": {
            "passed": prior_totals.get("passed", 0),
            "cases": prior_totals.get("cases", 0),
            "key_metrics": prior_metrics,
        },
        "after": {
            "passed": current_totals.get("passed", 0),
            "cases": current_totals.get("cases", 0),
            "key_metrics": current_metrics,
        },
    }


def metric_for_section(section: str) -> str | None:
    if section.startswith("domain.off_topic") or section == "domain.compact_rules":
        return "off_topic_recall"
    if section.startswith("jailbreak"):
        return "jailbreak_recall"
    if "conversation" in section or section.startswith("domain"):
        return "switch_allowed_recall"
    return None


def evaluate_accept(
    delta: dict[str, Any],
    *,
    target_section: str,
    target_pattern: str,
) -> tuple[bool, str]:
    """Pattern-primary accept gate. Returns (accepted, reason)."""
    passed_delta = int(delta.get("passed_delta", 0))
    pattern_deltas: dict[str, int] = delta.get("pattern_deltas", {})

    target_pattern_delta = pattern_deltas.get(target_pattern, 0)
    if target_pattern_delta <= -5:
        return True, f"Target pattern {target_pattern!r} decreased by {abs(target_pattern_delta)} cases"

    metric_key = metric_for_section(target_section)
    if metric_key:
        metric_delta = float(delta.get("key_metrics_delta", {}).get(metric_key, 0.0))
        if metric_delta >= 0.03:
            return True, f"{metric_key} improved by {metric_delta:.2%}"

    if passed_delta >= 3:
        worst_regression = max(pattern_deltas.values()) if pattern_deltas else 0
        if worst_regression <= 3:
            return True, f"Overall +{passed_delta} with no pattern regression >3"

    if passed_delta >= -2 and passed_delta <= 2 and target_pattern_delta < 0:
        return False, "Flat overall pass with only minor target pattern change"

    return False, "Did not meet pattern-primary accept criteria"


def compute_verdict(
    *,
    accepted: bool,
    delta: dict[str, Any],
    target_pattern: str,
) -> str:
    if not accepted:
        return "rejected"

    passed_delta = int(delta.get("passed_delta", 0))
    target_pattern_delta = int(delta.get("pattern_deltas", {}).get(target_pattern, 0))

    if passed_delta >= 3 or target_pattern_delta <= -5:
        return "improved"
    if passed_delta < 0 or target_pattern_delta > 0:
        return "not_improved"
    if passed_delta >= -2 and target_pattern_delta < 0:
        return "mixed"
    return "not_improved"
