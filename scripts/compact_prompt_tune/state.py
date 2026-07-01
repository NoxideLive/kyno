"""Tuning workspace paths and state management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TUNING_DIR = ROOT / "data" / "domain" / "bench" / "tuning"
STATE_PATH = TUNING_DIR / "state.json"
SUMMARY_PATH = TUNING_DIR / "summary.jsonl"


def iter_report_path(iteration: int) -> Path:
    return TUNING_DIR / f"iter-{iteration}-report.json"


def iter_changelog_path(iteration: int) -> Path:
    return TUNING_DIR / f"iter-{iteration}-changelog.md"


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"iteration": 0, "cycles": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    TUNING_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def extract_key_metrics(report: dict[str, Any]) -> dict[str, float]:
    suites = report.get("suites", {})
    domain = suites.get("domain", {}).get("metrics", {})
    jailbreak = suites.get("jailbreak", {}).get("metrics", {})
    switch = suites.get("switch", {}).get("metrics", {})
    return {
        "off_topic_recall": domain.get("off_topic", {}).get("recall", 0.0),
        "on_topic_recall": domain.get("on_topic", {}).get("recall", 0.0),
        "jailbreak_recall": jailbreak.get("jailbreak_attempted", {}).get("recall", 0.0),
        "switch_allowed_recall": switch.get("allowed", {}).get("recall", 0.0),
    }


def extract_suite_passes(report: dict[str, Any]) -> dict[str, int]:
    return {
        suite: summary.get("passed", 0)
        for suite, summary in report.get("suites", {}).items()
    }


def append_cycle(
    *,
    iteration: int,
    report_path: Path,
    report: dict[str, Any],
    changelog_path: Path | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    state = load_state()
    totals = report.get("totals", {})
    cycle: dict[str, Any] = {
        "iteration": iteration,
        "report_path": str(report_path.relative_to(ROOT)),
        "passed": totals.get("passed", 0),
        "total": totals.get("cases", 0),
        "suites": extract_suite_passes(report),
        "key_metrics": extract_key_metrics(report),
    }
    if changelog_path is not None:
        cycle["changelog_path"] = str(changelog_path.relative_to(ROOT))
    if notes:
        cycle["notes"] = notes

    cycles = [c for c in state.get("cycles", []) if c.get("iteration") != iteration]
    cycles.append(cycle)
    cycles.sort(key=lambda c: c.get("iteration", 0))
    state["iteration"] = iteration
    state["cycles"] = cycles
    save_state(state)

    summary_line = {
        "iteration": iteration,
        "passed": cycle["passed"],
        "total": cycle["total"],
        "suites": cycle["suites"],
        "key_metrics": cycle["key_metrics"],
    }
    _append_summary_line(summary_line)
    return cycle


def _append_summary_line(line: dict[str, Any]) -> None:
    TUNING_DIR.mkdir(parents=True, exist_ok=True)
    existing = ""
    if SUMMARY_PATH.is_file():
        existing = SUMMARY_PATH.read_text(encoding="utf-8")
    filtered = [
        ln
        for ln in existing.splitlines()
        if ln.strip() and json.loads(ln).get("iteration") != line.get("iteration")
    ]
    filtered.append(json.dumps(line, sort_keys=True))
    SUMMARY_PATH.write_text("\n".join(filtered) + "\n", encoding="utf-8")
