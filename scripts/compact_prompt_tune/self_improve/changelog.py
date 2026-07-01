"""Changelog and handoff artifacts per iteration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_handoff(
    *,
    iteration: int,
    accepted: bool,
    verdict: str,
    target_section: str,
    patch_summary: str,
    bench_diff: dict[str, Any],
    delta: dict[str, Any],
    verdict_reason: str,
    patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pattern_deltas = delta.get("pattern_deltas", {})
    improved_patterns = {k: v for k, v in pattern_deltas.items() if v < 0}
    regressed_patterns = {k: v for k, v in pattern_deltas.items() if v > 0}

    do_not_repeat: list[str] = []
    if not accepted or verdict in ("not_improved", "rejected"):
        do_not_repeat.append(patch_summary or f"Unchanged retry of {target_section}")

    lessons = patch.get("rationale", "") if patch else ""
    if regressed_patterns:
        lessons = (
            f"{lessons} Pair {target_section} changes with recovery examples when switch regresses."
        ).strip()

    return {
        "from_iter": iteration,
        "accepted": accepted,
        "verdict": verdict,
        "what_changed": {
            "prompt_section": target_section,
            "prompt_summary": patch_summary,
            "bench_added": len(bench_diff.get("added_ids", [])),
            "bench_removed": len(bench_diff.get("removed_ids", [])),
            "bench_summary": bench_diff.get("summary", ""),
        },
        "what_improved": {
            "patterns": improved_patterns,
            "sample_fixed_ids": delta.get("sample_fixed_ids", []),
            "key_metrics_delta": delta.get("key_metrics_delta", {}),
        },
        "what_regressed": {
            "patterns": regressed_patterns,
            "sample_regressed_ids": delta.get("sample_regressed_ids", []),
            "key_metrics_delta": delta.get("key_metrics_delta", {}),
        },
        "overall_delta": {
            "passed": delta.get("passed_delta", 0),
            "cases": delta.get("cases_delta", 0),
        },
        "verdict_reason": verdict_reason,
        "do_not_repeat": do_not_repeat,
        "lessons_for_next_iter": lessons,
    }


def write_handoff(iter_path: Path, handoff: dict[str, Any]) -> Path:
    path = iter_path / "handoff.json"
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    return path


def write_changelog(
    iter_path: Path,
    *,
    handoff: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> Path:
    path = iter_path / "changelog.md"
    lines = [
        f"# Iteration {handoff.get('from_iter')} changelog",
        "",
        f"**Verdict:** {handoff.get('verdict')} ({'accepted' if handoff.get('accepted') else 'rejected'})",
        "",
        "## What changed",
        "",
        f"- Section: `{handoff.get('what_changed', {}).get('prompt_section')}`",
        f"- {handoff.get('what_changed', {}).get('prompt_summary')}",
        f"- Bench: +{handoff.get('what_changed', {}).get('bench_added')} "
        f"/ −{handoff.get('what_changed', {}).get('bench_removed')}",
        "",
        "## Overall delta",
        "",
        f"- Passed delta: {handoff.get('overall_delta', {}).get('passed'):+d}",
        f"- Reason: {handoff.get('verdict_reason')}",
        "",
    ]

    improved = handoff.get("what_improved", {}).get("patterns", {})
    if improved:
        lines.extend(["## Improvements", ""])
        for pattern, count in improved.items():
            lines.append(f"- {pattern}: {count}")

    regressed = handoff.get("what_regressed", {}).get("patterns", {})
    if regressed:
        lines.extend(["", "## Regressions", ""])
        for pattern, count in regressed.items():
            lines.append(f"- {pattern}: +{count}")

    if handoff.get("do_not_repeat"):
        lines.extend(["", "## Do not repeat", ""])
        for item in handoff["do_not_repeat"]:
            lines.append(f"- {item}")

    if diagnosis:
        lines.extend(["", "## Diagnosis focus", "", f"- Top pattern: {diagnosis.get('top_pattern')}"])
    if plan:
        lines.extend(["", "## Plan", "", f"- Strategy: {plan.get('strategy')}"])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_lineage_summary(run_id: str, lineage: list[dict[str, Any]]) -> str:
    lines = [f"# Run {run_id} lineage", ""]
    for entry in lineage:
        lines.append(
            f"- iter {entry.get('iter')}: {entry.get('verdict')} "
            f"({entry.get('passed')}/{entry.get('bench_cases', '?')}) "
            f"section={entry.get('target_section', 'baseline')}"
        )
    return "\n".join(lines) + "\n"
