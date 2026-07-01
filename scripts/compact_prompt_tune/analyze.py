"""Analyze bench failures for compact prompt tuning."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "data" / "domain" / "bench"


def _load_switch_cases() -> dict[str, dict[str, Any]]:
    path = BENCH_DIR / "switch.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {case["id"]: case for case in data.get("cases", [])}


def _failure_pattern(failure: dict[str, Any]) -> str:
    suite = failure.get("suite", "")
    expected = failure.get("expected", "")
    actual = failure.get("actual", "")
    block_reason = failure.get("block_reason")
    meta = failure.get("meta") or {}

    if suite == "switch":
        direction = meta.get("direction", "unknown")
        return f"switch {direction} expected={expected} got={actual} block={block_reason}"
    if suite == "jailbreak" and expected == "safe" and actual == "jailbreak_attempted":
        return "jailbreak safe FP"
    if suite == "jailbreak" and expected == "jailbreak_attempted" and actual == "safe":
        return "jailbreak FN"
    if suite == "domain" and expected == "off_topic" and actual == "on_topic":
        return "domain off_topic FN"
    if suite == "domain" and expected == "on_topic" and actual == "off_topic":
        return "domain on_topic FN"
    return f"{suite} {expected}→{actual}"


def analyze_report(report_path: Path, *, top_n: int = 15) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures = report.get("failures", [])
    switch_cases = _load_switch_cases()

    patterns: Counter[str] = Counter()
    by_suite: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        pattern = _failure_pattern(failure)
        patterns[pattern] += 1
        enriched = dict(failure)
        if failure.get("suite") == "switch" and failure.get("id") in switch_cases:
            case = switch_cases[failure["id"]]
            enriched["history"] = case.get("history", [])
            enriched["meta"] = case.get("meta", {})
        by_suite[failure.get("suite", "unknown")].append(enriched)

    high_conf = sorted(
        failures,
        key=lambda f: f.get("confidence") or 0.0,
        reverse=True,
    )[:top_n]

    totals = report.get("totals", {})
    suites = report.get("suites", {})
    key_metrics = {
        "off_topic_recall": suites.get("domain", {}).get("metrics", {}).get("off_topic", {}).get("recall"),
        "jailbreak_recall": suites.get("jailbreak", {}).get("metrics", {}).get("jailbreak_attempted", {}).get("recall"),
        "switch_allowed_recall": suites.get("switch", {}).get("metrics", {}).get("allowed", {}).get("recall"),
    }

    return {
        "report_path": str(report_path),
        "passed": totals.get("passed", 0),
        "total": totals.get("cases", 0),
        "suites": {k: v.get("passed", 0) for k, v in suites.items()},
        "key_metrics": key_metrics,
        "failure_count": len(failures),
        "top_failure_patterns": patterns.most_common(top_n),
        "high_confidence_failures": high_conf,
        "failures_by_suite": dict(by_suite),
    }


def format_analysis(summary: dict[str, Any]) -> str:
    lines = [
        f"Report: {summary['report_path']}",
        f"Overall: {summary['passed']}/{summary['total']} passed",
        f"Suites: {summary['suites']}",
        f"Key metrics: {summary['key_metrics']}",
        "",
        "Top failure patterns:",
    ]
    for pattern, count in summary["top_failure_patterns"]:
        lines.append(f"  {count}x {pattern}")

    lines.append("")
    lines.append("High-confidence failures:")
    for failure in summary["high_confidence_failures"][:10]:
        lines.append(
            f"  [{failure.get('id')}] {failure.get('suite')} "
            f"expected={failure.get('expected')} actual={failure.get('actual')} "
            f"conf={failure.get('confidence')} block={failure.get('block_reason')}"
        )
        text = str(failure.get("text", ""))[:120]
        lines.append(f"    text: {text}")

    switch_failures = summary["failures_by_suite"].get("switch", [])
    off_to_on = [
        f for f in switch_failures
        if (f.get("meta") or {}).get("direction") == "off_to_on" and f.get("expected") == "allowed"
    ]
    if off_to_on:
        lines.append("")
        lines.append(f"Switch off→on allowed failures ({len(off_to_on)}):")
        for failure in off_to_on[:8]:
            lines.append(f"  [{failure.get('id')}] block={failure.get('block_reason')} text={failure.get('text')!r}")
            history = failure.get("history") or []
            for turn in history[-2:]:
                lines.append(f"    {turn.get('role')}: {str(turn.get('content', ''))[:80]}")

    return "\n".join(lines)
