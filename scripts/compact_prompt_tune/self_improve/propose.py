"""Four-phase Groq propose pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compact_prompt_tune.self_improve.context import (
    build_bench_summary,
    build_context_xml,
    build_existing_case_ids,
    build_still_failing,
    build_target_failures,
    get_section_content,
    load_best_report,
    load_integrations,
    load_previous_delta,
    load_previous_handoff,
    load_recent_reject_history,
    resolve_failure_report_path,
)
from compact_prompt_tune.self_improve.groq_client import (
    groq_thread_turn,
    load_messages,
    save_messages,
)
from compact_prompt_tune.self_improve.prompts import (
    PHASE_MAX_COMPLETION_TOKENS,
    PHASE_SCHEMAS,
    PHASE_TEMPERATURE,
    SYSTEM_PROMPT,
    patch_schema_for_section,
    user_turn_bench_backfill,
    user_turn_bench_curation,
    user_turn_bench_curation_retry,
    user_turn_diagnose,
    user_turn_patch,
    user_turn_plan,
)
from compact_prompt_tune.self_improve.log import info
from compact_prompt_tune.self_improve.state import iter_dir, load_meta, load_prompts


def run_propose_phases(
    *,
    run_id: str,
    iteration: int,
    base_iter: int,
    iter_path: Path,
    phases: list[str] | None = None,
) -> dict[str, Any]:
    meta = load_meta(run_id)
    base_iter_path = iter_dir(run_id, base_iter)
    failure_report_path = resolve_failure_report_path(run_id, iteration, base_iter)
    failure_iter = iteration - 1 if iteration > 0 else base_iter
    previous_delta = load_previous_delta(run_id, iteration)
    recent_rejects = load_recent_reject_history(run_id, iteration)
    prior_integrations = load_integrations(run_id)
    previous_handoff = load_previous_handoff(run_id, iteration)
    prior_report = None
    if base_iter != iteration:
        prior_report_path = iter_dir(run_id, base_iter) / "report.json"
        if prior_report_path.is_file():
            prior_report = json.loads(prior_report_path.read_text(encoding="utf-8"))
    best_report = load_best_report(run_id, meta)

    reject_iters = [int(r["iteration"]) for r in recent_rejects]
    info(
        "iter %d: failure analysis from iter-%d (accepted baseline iter-%d; recent rejects %s)",
        iteration,
        failure_iter,
        base_iter,
        reject_iters or "none",
    )

    context_xml = build_context_xml(
        run_id=run_id,
        iteration=iteration,
        base_iter_path=base_iter_path,
        failure_report_path=failure_report_path,
        prior_integrations=prior_integrations,
        previous_handoff=previous_handoff,
        prior_report=prior_report,
        best_report=best_report,
        previous_delta=previous_delta,
        recent_rejects=recent_rejects,
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    results: dict[str, Any] = {}
    selected = phases or ["diagnose", "plan", "patch", "bench_curation"]

    if "diagnose" in selected:
        info("iter %d: phase 1 DIAGNOSE", iteration)
        user_msg = user_turn_diagnose(context_xml)
        messages.append({"role": "user", "content": user_msg})
        _, diagnosis, messages = groq_thread_turn(
            messages=messages,
            response_schema=PHASE_SCHEMAS["diagnose"],
            schema_name="diagnosis",
            max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["diagnose"],
            temperature=PHASE_TEMPERATURE["diagnose"],
        )
        results["diagnosis"] = diagnosis
        (iter_path / "diagnosis.json").write_text(
            json.dumps(diagnosis, indent=2) + "\n", encoding="utf-8"
        )
        save_messages(iter_path / "messages.jsonl", messages)
        info(
            "iter %d: diagnosis top_pattern=%r focus=%r",
            iteration,
            diagnosis.get("top_pattern"),
            diagnosis.get("recommended_focus"),
        )

    diagnosis = results.get("diagnosis") or json.loads(
        (iter_path / "diagnosis.json").read_text(encoding="utf-8")
    )

    if "plan" in selected:
        info("iter %d: phase 2 PLAN", iteration)
        messages.append({"role": "user", "content": user_turn_plan()})
        _, plan, messages = groq_thread_turn(
            messages=messages,
            response_schema=PHASE_SCHEMAS["plan"],
            schema_name="plan",
            max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["plan"],
            temperature=PHASE_TEMPERATURE["plan"],
        )
        results["plan"] = plan
        (iter_path / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        save_messages(iter_path / "messages.jsonl", messages)
        info(
            "iter %d: plan target_section=%r strategy=%r",
            iteration,
            plan.get("target_section"),
            (str(plan.get("strategy", ""))[:80]),
        )

    plan = results.get("plan") or json.loads((iter_path / "plan.json").read_text(encoding="utf-8"))
    target_section = str(plan.get("target_section", diagnosis.get("recommended_focus", "")))

    if "patch" in selected:
        info("iter %d: phase 3 PATCH section=%s", iteration, target_section)
        rules, overlay = load_prompts(base_iter_path)
        section_content = get_section_content(rules, overlay, target_section)
        target_failures = build_target_failures(
            failure_report_path,
            top_pattern=str(diagnosis.get("top_pattern", "")),
        )
        user_msg = user_turn_patch(
            json.dumps(plan),
            target_section,
            section_content,
            target_failures,
        )
        messages.append({"role": "user", "content": user_msg})
        schema = patch_schema_for_section(target_section)
        _, patch, messages = groq_thread_turn(
            messages=messages,
            response_schema=schema,
            schema_name=f"patch_{target_section.replace('.', '_')}",
            max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["patch"],
            temperature=PHASE_TEMPERATURE["patch"],
        )
        patch["target_section"] = target_section
        results["patch"] = patch
        (iter_path / "patch.json").write_text(json.dumps(patch, indent=2) + "\n", encoding="utf-8")
        save_messages(iter_path / "messages.jsonl", messages)
        info("iter %d: patch operation=%r", iteration, patch.get("operation"))

    if "bench_curation" in selected:
        info("iter %d: phase 4 CURATE_BENCH", iteration)
        bench_summary = build_bench_summary(base_iter_path / "bench")
        still_failing = build_still_failing(failure_report_path)
        existing_ids = build_existing_case_ids(base_iter_path / "bench")
        messages.append(
            {
                "role": "user",
                "content": user_turn_bench_curation(
                    bench_summary,
                    still_failing,
                    iteration=iteration,
                    existing_case_ids=existing_ids,
                ),
            }
        )
        _, curation, messages = groq_thread_turn(
            messages=messages,
            response_schema=PHASE_SCHEMAS["bench_curation"],
            schema_name="bench_curation",
            max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["bench_curation"],
            temperature=PHASE_TEMPERATURE["bench_curation"],
        )
        results["bench_curation"] = curation
        (iter_path / "bench_curation.json").write_text(
            json.dumps(curation, indent=2) + "\n", encoding="utf-8"
        )
        save_messages(iter_path / "messages.jsonl", messages)
        info(
            "iter %d: bench curation +%d -%d",
            iteration,
            len(curation.get("add") or []),
            len(curation.get("remove") or []),
        )

    return results


def run_bench_curation_retry(
    *,
    iteration: int,
    iter_path: Path,
    skipped_adds: list[dict[str, str]],
    proposed_count: int,
) -> dict[str, Any]:
    """Groq retry when all proposed bench adds were skipped."""
    messages = load_messages(iter_path / "messages.jsonl")
    bench_summary = build_bench_summary(iter_path / "bench")
    existing_ids = build_existing_case_ids(iter_path / "bench")
    user_msg = user_turn_bench_curation_retry(
        bench_summary,
        skipped_adds=skipped_adds,
        iteration=iteration,
        existing_case_ids=existing_ids,
        proposed_count=proposed_count,
    )
    messages.append({"role": "user", "content": user_msg})
    info(
        "iter %d: bench curation retry (%d proposed, %d skipped)",
        iteration,
        proposed_count,
        len(skipped_adds),
    )
    _, curation, messages = groq_thread_turn(
        messages=messages,
        response_schema=PHASE_SCHEMAS["bench_curation"],
        schema_name="bench_curation",
        max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["bench_curation"],
        temperature=PHASE_TEMPERATURE["bench_curation"],
    )
    curation["remove"] = list(curation.get("remove") or [])
    artifact = iter_path / "bench_curation-retry.json"
    artifact.write_text(json.dumps(curation, indent=2) + "\n", encoding="utf-8")
    save_messages(iter_path / "messages.jsonl", messages)
    info(
        "iter %d: curation retry proposed +%d -%d",
        iteration,
        len(curation.get("add") or []),
        len(curation.get("remove") or []),
    )
    return curation


def run_bench_backfill(
    *,
    iteration: int,
    iter_path: Path,
    round_num: int,
    deficits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Groq add-only pass after removes dropped a label below minimum."""
    messages = load_messages(iter_path / "messages.jsonl")
    bench_summary = build_bench_summary(iter_path / "bench")
    existing_ids = build_existing_case_ids(iter_path / "bench")
    user_msg = user_turn_bench_backfill(
        bench_summary,
        deficits,
        round_num=round_num,
        iteration=iteration,
        existing_case_ids=existing_ids,
    )
    messages.append({"role": "user", "content": user_msg})
    info(
        "iter %d: bench backfill round %d (need %d cases toward target across %d labels)",
        iteration,
        round_num,
        sum(int(d.get("need", 0)) for d in deficits),
        len(deficits),
    )
    _, curation, messages = groq_thread_turn(
        messages=messages,
        response_schema=PHASE_SCHEMAS["bench_backfill"],
        schema_name="bench_backfill",
        max_completion_tokens=PHASE_MAX_COMPLETION_TOKENS["bench_backfill"],
        temperature=PHASE_TEMPERATURE["bench_backfill"],
    )
    curation["remove"] = []
    artifact = iter_path / f"bench_backfill-{round_num}.json"
    artifact.write_text(json.dumps(curation, indent=2) + "\n", encoding="utf-8")
    save_messages(iter_path / "messages.jsonl", messages)
    info(
        "iter %d: backfill round %d proposed +%d cases",
        iteration,
        round_num,
        len(curation.get("add") or []),
    )
    return curation
