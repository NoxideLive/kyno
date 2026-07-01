"""Build improver context XML for Groq phase 1."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from compact_prompt_tune.analyze import _failure_pattern, analyze_report
from compact_prompt_tune.self_improve.apply import load_bench_label_bounds
from compact_prompt_tune.self_improve.state import (
    iter_dir,
    load_jsonl,
    load_prompts,
    prompt_manifest,
    run_dir,
)


def _subgroup_root_cause(text: str, pattern: str) -> str:
    lowered = text.lower()
    if "math lit" in lowered or "mathematical literacy" in lowered:
        return "Math Lit"
    if "ib " in lowered or "international baccalaureate" in lowered:
        return "IB"
    if any(m in lowered for m in ("wat ", "graad ", "wiskunde", "afrikaans")):
        return "non-English"
    if pattern.startswith("switch"):
        return "switch"
    if "summarize" in lowered or "atp" in lowered:
        return "template"
    return "other"


def resolve_failure_report_path(run_id: str, iteration: int, base_iter: int) -> Path:
    """Report for failure analysis: previous iteration when available, else accepted baseline."""
    if iteration > 0:
        prev = iter_dir(run_id, iteration - 1) / "report.json"
        if prev.is_file():
            return prev
    return iter_dir(run_id, base_iter) / "report.json"


def failure_report_iter_from_path(run_id: str, report_path: Path) -> int:
    """Parse iter-N from a report path under run_dir."""
    name = report_path.parent.name
    if name.startswith("iter-"):
        try:
            return int(name.split("-", 1)[1])
        except ValueError:
            pass
    meta_path = run_dir(run_id) / "meta.json"
    if meta_path.is_file():
        return int(json.loads(meta_path.read_text(encoding="utf-8")).get("latest_accepted_iter", 0))
    return 0


def load_previous_delta(run_id: str, iteration: int) -> dict[str, Any] | None:
    if iteration <= 0:
        return None
    path = iter_dir(run_id, iteration - 1) / "delta.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_recent_reject_history(
    run_id: str,
    iteration: int,
    *,
    max_rejects: int = 3,
) -> list[dict[str, Any]]:
    """Last N rejected iterations (most recent first), each with handoff + delta."""
    rejects: list[dict[str, Any]] = []
    for prev in range(iteration - 1, -1, -1):
        if len(rejects) >= max_rejects:
            break
        iter_path = iter_dir(run_id, prev)
        handoff_path = iter_path / "handoff.json"
        if not handoff_path.is_file():
            continue
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        if handoff.get("accepted", True):
            continue
        delta_path = iter_path / "delta.json"
        delta = (
            json.loads(delta_path.read_text(encoding="utf-8"))
            if delta_path.is_file()
            else {}
        )
        rejects.append({"iteration": prev, "handoff": handoff, "delta": delta})
    return rejects


def _failures_by_id(report_path: Path) -> dict[str, dict[str, Any]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {str(f["id"]): f for f in report.get("failures", [])}


def build_regression_focus(
    report_path: Path,
    delta: dict[str, Any],
    *,
    limit: int = 20,
) -> str:
    """Highlight patterns and cases that regressed in the last attempt."""
    pattern_deltas = delta.get("pattern_deltas") or {}
    worsened = sorted(
        ((p, int(d)) for p, d in pattern_deltas.items() if int(d) > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    if not worsened and not delta.get("regressed_ids"):
        return ""

    failures = _failures_by_id(report_path)
    lines = [
        f"attempt_from: {report_path.parent.name}",
        f"passed_delta: {delta.get('passed_delta', 0):+d}",
        f"regressed_count: {delta.get('regressed_count', 0)}",
        "",
        "Worsened patterns:",
    ]
    for pattern, count in worsened[:8]:
        lines.append(f"- {pattern}: +{count}")

    lines.append("")
    lines.append("Regressed case samples:")
    for case_id in (delta.get("regressed_ids") or [])[:limit]:
        failure = failures.get(str(case_id))
        if failure is None:
            lines.append(f"- [{case_id}] (failure row not in report)")
            continue
        lines.append(
            f"- [{case_id}] {_failure_pattern(failure)} "
            f"expected={failure.get('expected')} actual={failure.get('actual')} "
            f"text={str(failure.get('text', ''))[:100]!r} block={failure.get('block_reason')}"
        )
    return "\n".join(lines)


def format_recent_reject_history(rejects: list[dict[str, Any]]) -> str:
    if not rejects:
        return "(none — no recent rejected iterations)"
    lines: list[str] = []
    for entry in rejects:
        iteration = entry.get("iteration")
        handoff = entry.get("handoff") or {}
        delta = entry.get("delta") or {}
        what_changed = handoff.get("what_changed") or {}
        what_regressed = handoff.get("what_regressed") or {}
        lines.append(f"## Reject iter-{iteration}")
        lines.append(f"section: {what_changed.get('prompt_section', '')}")
        lines.append(f"patch: {what_changed.get('prompt_summary', '')}")
        lines.append(
            f"passed_delta: {handoff.get('overall_delta', {}).get('passed', delta.get('passed_delta', 0)):+d}"
        )
        regressed_patterns = what_regressed.get("patterns") or {}
        if regressed_patterns:
            parts = [f"{p}: +{c}" for p, c in sorted(regressed_patterns.items(), key=lambda x: -x[1])]
            lines.append(f"regressed_patterns: {', '.join(parts[:6])}")
        if handoff.get("do_not_repeat"):
            lines.append(f"do_not_repeat: {'; '.join(handoff['do_not_repeat'])}")
        if handoff.get("lessons_for_next_iter"):
            lines.append(f"lesson: {handoff['lessons_for_next_iter']}")
        if handoff.get("verdict_reason"):
            lines.append(f"reason: {handoff['verdict_reason']}")
        lines.append("")
    return "\n".join(lines).strip()


def build_existing_case_ids(bench_dir: Path, *, max_samples: int = 12) -> str:
    """Compact existing id index for bench curation prompts."""
    lines: list[str] = []
    for name in ("jailbreak.json", "domain.json", "switch.json"):
        path = bench_dir / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        suite = payload.get("suite", name.replace(".json", ""))
        ids = [str(c.get("id", "")) for c in payload.get("cases", []) if c.get("id")]
        sample = ", ".join(ids[:max_samples])
        suffix = f" ... ({len(ids)} total)" if len(ids) > max_samples else ""
        lines.append(f"{suite}: {len(ids)} ids — samples: {sample}{suffix}")
    lines.append(
        "Use NEW ids only. Required format: {suite}-si-{iteration}-{seq} e.g. dom-si-3-001, jb-si-3-001, sw-si-3-001"
    )
    return "\n".join(lines)


def build_failure_clusters(
    report_path: Path,
    *,
    switch_cases: dict[str, dict[str, Any]] | None = None,
    max_samples_per_pattern: int = 25,
) -> str:
    analysis = analyze_report(report_path)
    failures = analysis.get("failures_by_suite", {})
    all_failures: list[dict[str, Any]] = []
    for suite_failures in failures.values():
        all_failures.extend(suite_failures)

    by_pattern: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for failure in all_failures:
        by_pattern[_failure_pattern(failure)].append(failure)

    top_patterns = sorted(
        by_pattern.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )[:5]

    lines: list[str] = []
    for pattern, cases in top_patterns:
        root_counts: Counter[str] = Counter()
        for case in cases:
            root_counts[_subgroup_root_cause(str(case.get("text", "")), pattern)] += 1
        roots = ", ".join(f"{k} ({v})" for k, v in root_counts.most_common(4))
        lines.append(f"## {pattern} ({len(cases)} cases)")
        lines.append(f"Root causes: {roots}")
        lines.append("Samples:")
        for case in sorted(cases, key=lambda c: c.get("confidence") or 0, reverse=True)[
            :max_samples_per_pattern
        ]:
            case_id = case.get("id")
            conf = case.get("confidence")
            text = str(case.get("text", ""))[:120]
            block = case.get("block_reason")
            line = f"- [{case_id}] conf={conf} text={text!r}"
            if block:
                line += f" block={block}"
            lines.append(line)
            if case.get("suite") == "switch" and switch_cases and case_id in switch_cases:
                for turn in (switch_cases[case_id].get("history") or [])[-2:]:
                    lines.append(
                        f"  {turn.get('role')}: {str(turn.get('content', ''))[:80]}"
                    )
        lines.append("")
    return "\n".join(lines).strip()


def format_prior_integrations(
    integrations: list[dict[str, Any]],
    *,
    max_items: int = 15,
) -> str:
    if not integrations:
        return "(none — first improvement iteration)"
    lines: list[str] = []
    for record in integrations[-max_items:]:
        iteration = record.get("iteration")
        verdict = str(record.get("verdict", "")).upper()
        section = record.get("target_section", "")
        lines.append(f"Integration {iteration} [{verdict}] {section}")
        lines.append(f"  Change: {record.get('patch_summary', '')}")
        lines.append(f"  Why: {record.get('rationale', '')}")
        scores = record.get("scores", {})
        delta = record.get("delta", {})
        before = scores.get("before", {})
        after = scores.get("after", {})
        lines.append(
            f"  Result: {before.get('passed')}→{after.get('passed')} passed "
            f"({delta.get('passed_delta', 0):+d}); "
            f"fixed={delta.get('fixed_count', 0)} regressed={delta.get('regressed_count', 0)}"
        )
        if verdict in ("REJECTED", "NOT_IMPROVED"):
            lines.append(
                f"  Do not repeat: {record.get('verdict_reason', record.get('patch_summary', ''))}"
            )
        lines.append("---")
    return "\n".join(lines)


def load_switch_cases(bench_dir: Path) -> dict[str, dict[str, Any]]:
    path = bench_dir / "switch.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {case["id"]: case for case in data.get("cases", [])}


def render_handoff(handoff: dict[str, Any]) -> str:
    return json.dumps(handoff, indent=2)


def build_scores_block(
    report: dict[str, Any],
    *,
    prior_report: dict[str, Any] | None = None,
    best_report: dict[str, Any] | None = None,
) -> str:
    totals = report.get("totals", {})
    suites = report.get("suites", {})
    off_topic = suites.get("domain", {}).get("metrics", {}).get("off_topic", {}).get("recall")
    jailbreak = (
        suites.get("jailbreak", {})
        .get("metrics", {})
        .get("jailbreak_attempted", {})
        .get("recall")
    )
    switch_allowed = (
        suites.get("switch", {}).get("metrics", {}).get("allowed", {}).get("recall")
    )

    lines = [
        f"passed: {totals.get('passed')}/{totals.get('cases')}",
        f"off_topic_recall: {off_topic:.0%}" if off_topic is not None else "off_topic_recall: n/a",
        f"jailbreak_recall: {jailbreak:.0%}" if jailbreak is not None else "jailbreak_recall: n/a",
        f"switch_allowed: {switch_allowed:.0%}"
        if switch_allowed is not None
        else "switch_allowed: n/a",
    ]
    if prior_report:
        prior_passed = prior_report.get("totals", {}).get("passed", 0)
        lines.append(f"vs_prior: {int(totals.get('passed', 0)) - int(prior_passed):+d} passed")
    if best_report:
        best_passed = best_report.get("totals", {}).get("passed", 0)
        lines.append(f"vs_best: {int(totals.get('passed', 0)) - int(best_passed):+d} passed")
    return "\n".join(lines)


def build_context_xml(
    *,
    run_id: str,
    iteration: int,
    base_iter_path: Path,
    failure_report_path: Path,
    prior_integrations: list[dict[str, Any]],
    previous_handoff: dict[str, Any] | None = None,
    prior_report: dict[str, Any] | None = None,
    best_report: dict[str, Any] | None = None,
    previous_delta: dict[str, Any] | None = None,
    recent_rejects: list[dict[str, Any]] | None = None,
) -> str:
    baseline_report_path = base_iter_path / "report.json"
    baseline_report = json.loads(baseline_report_path.read_text(encoding="utf-8"))
    failure_report = json.loads(failure_report_path.read_text(encoding="utf-8"))
    rules, overlay = load_prompts(base_iter_path)
    manifest = prompt_manifest(rules, overlay)
    switch_cases = load_switch_cases(base_iter_path / "bench")

    failure_iter = failure_report_iter_from_path(run_id, failure_report_path)
    baseline_iter = failure_report_iter_from_path(run_id, baseline_report_path)
    reject_iters = [int(r["iteration"]) for r in (recent_rejects or [])]

    blocks = [
        f"<run_id>{run_id}</run_id>",
        f"<iteration>{iteration}</iteration>",
        (
            "<context_sources>\n"
            f"accepted_baseline_iter: {baseline_iter}\n"
            f"failure_report_iter: {failure_iter}\n"
            f"recent_reject_iters: {reject_iters or []}\n"
            "</context_sources>"
        ),
    ]

    if previous_handoff:
        blocks.append(
            f"<previous_iteration_report>\n{render_handoff(previous_handoff)}\n</previous_iteration_report>"
        )

    recent_reject_block = format_recent_reject_history(recent_rejects or [])
    if recent_rejects:
        blocks.append(
            f"<recent_reject_history>\n{recent_reject_block}\n</recent_reject_history>"
        )

    blocks.append(
        f"<scores accepted_baseline>\n{build_scores_block(baseline_report, prior_report=prior_report, best_report=best_report)}\n</scores>"
    )
    if failure_report_path.resolve() != baseline_report_path.resolve():
        blocks.append(
            f"<last_attempt_scores iter=\"{failure_iter}\">\n"
            f"{build_scores_block(failure_report)}\n</last_attempt_scores>"
        )

    if previous_delta and previous_handoff and not previous_handoff.get("accepted", True):
        regression = build_regression_focus(failure_report_path, previous_delta)
        if regression:
            blocks.append(f"<regression_focus>\n{regression}\n</regression_focus>")

    blocks.append(
        f"<failure_clusters source_iter=\"{failure_iter}\">\n"
        f"{build_failure_clusters(failure_report_path, switch_cases=switch_cases)}\n</failure_clusters>"
    )
    blocks.append(
        f"<prior_integrations>\n{format_prior_integrations(prior_integrations)}\n</prior_integrations>"
    )
    counts = manifest.get("overlay_counts", {})
    blocks.append(
        "<current_prompt_summary>\n"
        + "\n".join(f"{k}: {v}" for k, v in counts.items())
        + f"\ndomain_compact_rules_chars: {manifest.get('domain_compact_rules_chars')}"
        + f"\njailbreak_compact_rules_chars: {manifest.get('jailbreak_compact_rules_chars')}"
        + "\n</current_prompt_summary>"
    )
    return "\n".join(blocks)


def get_section_content(
    rules: dict[str, Any],
    overlay: dict[str, Any],
    section: str,
) -> str:
    if section == "domain.compact_rules":
        return json.dumps({"compact_rules": rules.get("domain", {}).get("compact_rules", "")}, indent=2)
    if section == "jailbreak.compact_rules":
        return json.dumps(
            {"compact_rules": rules.get("jailbreak", {}).get("compact_rules", "")},
            indent=2,
        )
    classifier, key = section.split(".", 1)
    items = overlay.get(classifier, {}).get(key, [])
    return json.dumps(items, indent=2)


def build_target_failures(
    report_path: Path,
    *,
    top_pattern: str,
    limit: int = 12,
) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for failure in report.get("failures", []):
        if _failure_pattern(failure) != top_pattern:
            continue
        lines.append(
            f"[{failure.get('id')}] {failure.get('suite')} "
            f"expected={failure.get('expected')} actual={failure.get('actual')} "
            f"text={failure.get('text')!r} block={failure.get('block_reason')}"
        )
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "(no matching failures)"


def build_bench_summary(bench_dir: Path) -> str:
    min_per_label, max_per_label, target_per_label = load_bench_label_bounds(bench_dir)
    lines: list[str] = []
    for name in ("jailbreak.json", "domain.json", "switch.json"):
        path = bench_dir / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        suite = payload.get("suite", name.replace(".json", ""))
        labels: Counter[str] = Counter()
        for case in payload.get("cases", []):
            labels[str(case.get("label", ""))] += 1
        label_parts: list[str] = []
        for label, count in sorted(labels.items()):
            label_parts.append(
                f"{label}={count} [min={min_per_label} target={target_per_label} max={max_per_label}]"
            )
        label_str = ", ".join(label_parts)
        lines.append(f"{suite}: {len(payload.get('cases', []))} cases ({label_str})")
    return "\n".join(lines)


def build_still_failing(report_path: Path, *, limit: int = 20) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for failure in report.get("failures", [])[:limit]:
        lines.append(
            f"[{failure.get('id')}] {_failure_pattern(failure)} text={str(failure.get('text', ''))[:80]!r}"
        )
    return "\n".join(lines)


def load_previous_handoff(run_id: str, iteration: int) -> dict[str, Any] | None:
    if iteration <= 0:
        return None
    path = iter_dir(run_id, iteration - 1) / "handoff.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_integrations(run_id: str) -> list[dict[str, Any]]:
    return load_jsonl(run_dir(run_id) / "integration_history.jsonl")


def load_best_report(run_id: str, meta: dict[str, Any]) -> dict[str, Any] | None:
    best_iter = meta.get("best_iter")
    if best_iter is None:
        return None
    path = iter_dir(run_id, int(best_iter)) / "report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
