"""Self-improve bench orchestration."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compact_prompt_tune.self_improve.apply import (
    apply_bench_curation,
    apply_patch,
    bench_label_backfill_needs,
    bench_label_deficits,
    bench_label_surplus,
    load_bench_label_bounds,
    merge_bench_diffs,
    write_bench_diff,
    write_prompt_diff,
)
from compact_prompt_tune.self_improve.bench import run_iteration_bench, write_report
from compact_prompt_tune.self_improve.changelog import (
    build_handoff,
    build_lineage_summary,
    write_changelog,
    write_handoff,
)
from compact_prompt_tune.self_improve.context import (
    build_context_xml,
    load_integrations,
    load_previous_delta,
    load_recent_reject_history,
    resolve_failure_report_path,
)
from compact_prompt_tune.self_improve.delta import (
    compute_composite_score,
    compute_delta,
    compute_verdict,
    evaluate_accept,
)
from compact_prompt_tune.self_improve.groq_client import load_groq_key_from_env_file
from compact_prompt_tune.self_improve.log import info, warn
from compact_prompt_tune.self_improve.propose import (
    run_bench_backfill,
    run_bench_curation_retry,
    run_propose_phases,
)
from compact_prompt_tune.self_improve.state import (
    SELF_IMPROVE_ROOT,
    append_jsonl,
    copy_iter_snapshot,
    copy_prod_bench,
    count_bench_cases,
    empty_overlay,
    empty_rules,
    iter_dir,
    load_jsonl,
    load_meta,
    load_prompts,
    new_run_id,
    prompt_manifest,
    register_run,
    run_dir,
    save_meta,
    set_active_run,
    update_run_registry,
    validate_run_id,
    write_iter_manifest,
    write_prompts,
)
from compact_prompt_tune.state import extract_key_metrics


MAX_PROMPT_CHARS = 8000
DEFAULT_MAX_ITERATIONS = 5
MAX_CONSECUTIVE_REJECTS = 3


def _resolve_best_passes_iter(meta: dict[str, Any]) -> int:
    return int(meta.get("best_passes_iter", meta.get("best_iter", 0)))


def _resolve_promotion_iter(meta: dict[str, Any]) -> int:
    return int(meta.get("promotion_iter", meta.get("latest_accepted_iter", 0)))


def _update_iteration_ranking(
    meta: dict[str, Any],
    *,
    run_id: str,
    iteration: int,
    report: dict[str, Any],
    accepted: bool,
) -> None:
    composite_scores: dict[str, float] = dict(meta.get("composite_scores") or {})
    score = compute_composite_score(report)
    composite_scores[str(iteration)] = score
    meta["composite_scores"] = composite_scores

    current_passed = int(report.get("totals", {}).get("passed", 0))
    best_passes_iter = _resolve_best_passes_iter(meta)
    best_report_path = iter_dir(run_id, best_passes_iter) / "report.json"
    best_passed = 0
    if best_report_path.is_file():
        best_report = json.loads(best_report_path.read_text(encoding="utf-8"))
        best_passed = int(best_report.get("totals", {}).get("passed", 0))
    if current_passed > best_passed:
        meta["best_passes_iter"] = iteration
        meta["best_iter"] = iteration

    if accepted:
        promo_iter = _resolve_promotion_iter(meta)
        promo_score = float(composite_scores.get(str(promo_iter), 0.0))
        if score >= promo_score:
            meta["promotion_iter"] = iteration


def _patch_summary(patch: dict[str, Any]) -> str:
    section = patch.get("target_section", "")
    if patch.get("operation") == "replace":
        return f"Replaced {section} compact_rules"
    add_count = len(patch.get("add") or [])
    return f"Prepended {add_count} items to {section}"


def init_run(
    *,
    run_id: str | None = None,
    seed_run_id: str | None = None,
    force: bool = False,
    gateway_url: str | None = None,
) -> str:
    rid = run_id or new_run_id()
    validate_run_id(rid)
    info("init run %s%s", rid, f" (seed={seed_run_id})" if seed_run_id else " (cold start)")
    path = run_dir(rid)
    if path.exists() and not force:
        raise FileExistsError(f"Run already exists: {rid} (use --force to overwrite)")

    if path.exists() and force:
        shutil.rmtree(path)

    path.mkdir(parents=True)
    iter0 = iter_dir(rid, 0)

    imported_history = False
    if seed_run_id:
        source_path = run_dir(seed_run_id)
        if not source_path.is_dir():
            raise FileNotFoundError(f"Seed run not found: {seed_run_id}")
        source_meta = load_meta(seed_run_id)
        source_accepted = int(source_meta.get("latest_accepted_iter", 0))
        source_iter = iter_dir(seed_run_id, source_accepted)
        if not source_iter.is_dir():
            raise FileNotFoundError(
                f"Seed run {seed_run_id} missing iter-{source_accepted}/"
            )
        copy_iter_snapshot(source_iter, iter0)
        for name in ("integration_history.jsonl",):
            src = source_path / name
            if src.is_file():
                shutil.copy2(src, path / name)
                imported_history = True
    else:
        iter0.mkdir(parents=True)
        rules = empty_rules()
        overlay = empty_overlay()
        write_prompts(iter0, rules, overlay)
        copy_prod_bench(iter0 / "bench")

    load_groq_key_from_env_file()
    info("iter 0: baseline bench")
    report = run_iteration_bench(iter0, gateway_url=gateway_url)
    write_report(iter0, report)

    bench_cases = count_bench_cases(iter0 / "bench")
    rules, overlay = load_prompts(iter0)
    manifest = prompt_manifest(rules, overlay)
    write_iter_manifest(
        iter0,
        iteration=0,
        accepted=True,
        verdict="baseline",
        parent_iter=-1,
        bench_cases=bench_cases,
        prompt_chars=int(manifest.get("total_prompt_chars", 0)),
    )

    baseline_score = compute_composite_score(report)
    meta = {
        "run_id": rid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "latest_iter": 0,
        "latest_accepted_iter": 0,
        "best_iter": 0,
        "best_passes_iter": 0,
        "promotion_iter": 0,
        "composite_scores": {"0": baseline_score},
        "seed_run_id": seed_run_id,
        "imported_history": imported_history,
        "consecutive_rejects": 0,
    }
    save_meta(rid, meta)

    totals = report.get("totals", {})
    append_jsonl(
        path / "lineage.jsonl",
        {
            "iter": 0,
            "parent_iter": -1,
            "parent_accepted_iter": -1,
            "accepted": True,
            "verdict": "baseline",
            "snapshot": f"runs/{rid}/iter-0/",
            "bench_cases": bench_cases,
            "passed": totals.get("passed", 0),
            "key_metrics": extract_key_metrics(report),
            "target_section": "baseline",
        },
    )
    append_jsonl(
        path / "summary.jsonl",
        {
            "iter": 0,
            "passed": totals.get("passed", 0),
            "total": totals.get("cases", 0),
            "key_metrics": extract_key_metrics(report),
            "accepted": True,
            "verdict": "baseline",
        },
    )

    register_run(rid, seed_run_id=seed_run_id)
    update_run_registry(
        rid,
        best_passed=totals.get("passed", 0),
        status="active",
    )
    set_active_run(rid)
    totals = report.get("totals", {})
    info(
        "init complete: %s iter-0 baseline %d/%d passed",
        rid,
        totals.get("passed", 0),
        totals.get("cases", 0),
    )
    return rid


MAX_BENCH_BACKFILL_ROUNDS = int(os.environ.get("SELF_IMPROVE_BENCH_BACKFILL_ROUNDS", "12"))


def apply_curation_with_backfill(
    *,
    run_id: str,
    iteration: int,
    iter_path: Path,
    curation: dict[str, Any],
    skip_propose: bool,
) -> dict[str, Any]:
    """Apply curation; Groq backfill rebalances removed labels up to target (midpoint)."""
    bench_dir = iter_path / "bench"
    _, _, target_per_label = load_bench_label_bounds(bench_dir)
    bench_diff = apply_bench_curation(bench_dir, curation, iteration=iteration)

    proposed_adds = len(curation.get("add") or [])
    if (
        proposed_adds > 0
        and len(bench_diff.get("added_ids", [])) == 0
        and bench_diff.get("skipped_adds")
        and not skip_propose
    ):
        info(
            "run %s iter %d: bench curation retry — 0/%d adds applied",
            run_id,
            iteration,
            proposed_adds,
        )
        retry_curation = run_bench_curation_retry(
            iteration=iteration,
            iter_path=iter_path,
            skipped_adds=bench_diff.get("skipped_adds", []),
            proposed_count=proposed_adds,
        )
        partial = apply_bench_curation(
            bench_dir, retry_curation, remove_cap=0, iteration=iteration
        )
        bench_diff = merge_bench_diffs(bench_diff, partial)

    backfill_rounds: list[dict[str, Any]] = []

    rebalance_keys = {
        (str(d["suite"]), str(d["label"])) for d in bench_label_deficits(bench_dir)
    }

    round_num = 0
    while rebalance_keys:
        needs = bench_label_backfill_needs(bench_dir, rebalance_keys)
        if not needs:
            break
        round_num += 1
        if round_num > MAX_BENCH_BACKFILL_ROUNDS:
            below_min = [n for n in needs if int(n["current"]) < int(n["min"])]
            if below_min:
                raise RuntimeError(
                    f"bench labels still below minimum after {MAX_BENCH_BACKFILL_ROUNDS} "
                    f"backfill rounds: {below_min}"
                )
            warn(
                "run %s iter %d: backfill stopped below target after %d rounds: %s",
                run_id,
                iteration,
                MAX_BENCH_BACKFILL_ROUNDS,
                needs,
            )
            break
        if skip_propose:
            raise RuntimeError(
                f"bench needs backfill after curation but --skip-propose is set: {needs}"
            )

        info(
            "run %s iter %d: bench backfill round %d — %s",
            run_id,
            iteration,
            round_num,
            ", ".join(
                f"{n['suite']}.{n['label']}={n['current']}/target={n['target']}"
                for n in needs
            ),
        )
        backfill = run_bench_backfill(
            iteration=iteration,
            iter_path=iter_path,
            round_num=round_num,
            deficits=needs,
        )
        partial = apply_bench_curation(bench_dir, backfill, remove_cap=0, iteration=iteration)
        backfill_rounds.append(
            {
                "round": round_num,
                "needs_before": needs,
                "proposed_adds": len(backfill.get("add") or []),
                "applied_adds": len(partial.get("added_ids", [])),
                "skipped_adds": partial.get("skipped_adds", []),
            }
        )
        bench_diff = merge_bench_diffs(bench_diff, partial)

    still_below_min = bench_label_deficits(bench_dir)
    if still_below_min:
        raise RuntimeError(f"bench labels below minimum after curation: {still_below_min}")

    below_target = bench_label_backfill_needs(bench_dir, rebalance_keys) if rebalance_keys else []
    if below_target:
        warn(
            "run %s iter %d: rebalanced labels still below target %d: %s",
            run_id,
            iteration,
            target_per_label,
            below_target,
        )

    surplus = bench_label_surplus(bench_dir)
    if surplus:
        raise RuntimeError(
            f"bench labels above maximum after curation: {surplus}"
        )

    bench_diff["backfill_rounds"] = backfill_rounds
    bench_diff["deficits"] = []
    bench_diff["surplus"] = []
    return bench_diff


def run_single_iteration(
    run_id: str,
    *,
    iteration: int | None = None,
    force: bool = False,
    gateway_url: str | None = None,
    skip_propose: bool = False,
) -> dict[str, Any]:
    meta = load_meta(run_id)
    base_iter = int(meta.get("latest_accepted_iter", 0))
    next_iter = iteration if iteration is not None else int(meta.get("latest_iter", 0)) + 1

    if next_iter <= 0:
        raise ValueError("Use init for iter-0; run iteration >= 1")

    info(
        "run %s iter %d: starting from accepted iter-%d",
        run_id,
        next_iter,
        base_iter,
    )

    iter_path = iter_dir(run_id, next_iter)
    if iter_path.exists():
        if not force:
            raise FileExistsError(
                f"iter-{next_iter}/ already exists (use --force to re-run)"
            )
        backup = iter_dir(run_id, next_iter).with_name(
            f"iter-{next_iter}.retry-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )
        warn("iter-%d exists; backing up to %s", next_iter, backup.name)
        iter_path.rename(backup)
        iter_path = iter_dir(run_id, next_iter)

    iter_path.mkdir(parents=True)
    base_path = iter_dir(run_id, base_iter)

    # Start from accepted snapshot
    shutil.copytree(base_path / "prompts", iter_path / "prompts")
    shutil.copytree(base_path / "bench", iter_path / "bench")

    prior_report = json.loads((base_path / "report.json").read_text(encoding="utf-8"))

    if not skip_propose:
        load_groq_key_from_env_file()
        info("run %s iter %d: Groq propose pipeline", run_id, next_iter)
        propose_results = run_propose_phases(
            run_id=run_id,
            iteration=next_iter,
            base_iter=base_iter,
            iter_path=iter_path,
        )
    else:
        propose_results = {
            "diagnosis": json.loads((iter_path / "diagnosis.json").read_text(encoding="utf-8")),
            "plan": json.loads((iter_path / "plan.json").read_text(encoding="utf-8")),
            "patch": json.loads((iter_path / "patch.json").read_text(encoding="utf-8")),
            "bench_curation": json.loads(
                (iter_path / "bench_curation.json").read_text(encoding="utf-8")
            ),
        }

    diagnosis = propose_results["diagnosis"]
    plan = propose_results["plan"]
    patch = propose_results["patch"]
    curation = propose_results["bench_curation"]

    rules, overlay = load_prompts(iter_path)
    info("run %s iter %d: applying prompt patch", run_id, next_iter)
    new_rules, new_overlay, prompt_diff = apply_patch(rules, overlay, patch)
    write_prompt_diff(iter_path / "prompt_diff.json", prompt_diff)
    write_prompts(iter_path, new_rules, new_overlay)

    bench_diff = apply_curation_with_backfill(
        run_id=run_id,
        iteration=next_iter,
        iter_path=iter_path,
        curation=curation,
        skip_propose=skip_propose,
    )
    write_bench_diff(iter_path / "bench_diff.json", bench_diff)
    info(
        "run %s iter %d: bench curation applied (+%d -%d cases; backfill rounds=%d; skipped adds=%d)",
        run_id,
        next_iter,
        len(bench_diff.get("added_ids", [])),
        len(bench_diff.get("removed_ids", [])),
        len(bench_diff.get("backfill_rounds", [])),
        len(bench_diff.get("skipped_adds", [])),
    )

    manifest = prompt_manifest(new_rules, new_overlay)
    if int(manifest.get("total_prompt_chars", 0)) > MAX_PROMPT_CHARS:
        raise RuntimeError(
            f"Prompt size {manifest['total_prompt_chars']} exceeds {MAX_PROMPT_CHARS} char limit"
        )

    info("run %s iter %d: classifier bench", run_id, next_iter)
    report = run_iteration_bench(iter_path, gateway_url=gateway_url)
    write_report(iter_path, report)

    delta = compute_delta(prior_report, report)
    (iter_path / "delta.json").write_text(json.dumps(delta, indent=2) + "\n", encoding="utf-8")

    target_pattern = str(diagnosis.get("top_pattern", ""))
    target_section = str(plan.get("target_section", patch.get("target_section", "")))
    accepted, verdict_reason = evaluate_accept(
        delta,
        target_section=target_section,
        target_pattern=target_pattern,
    )
    verdict = compute_verdict(
        accepted=accepted,
        delta=delta,
        target_pattern=target_pattern,
    )

    if not accepted:
        warn("run %s iter %d: rejected — rolling back prompts/bench", run_id, next_iter)
        # Roll back working prompts to base (snapshot still has attempted state)
        shutil.rmtree(iter_path / "prompts")
        shutil.rmtree(iter_path / "bench")
        shutil.copytree(base_path / "prompts", iter_path / "prompts")
        shutil.copytree(base_path / "bench", iter_path / "bench")

    bench_cases = count_bench_cases(iter_path / "bench")
    write_iter_manifest(
        iter_path,
        iteration=next_iter,
        accepted=accepted,
        verdict=verdict,
        parent_iter=base_iter,
        bench_cases=bench_cases,
        prompt_chars=int(manifest.get("total_prompt_chars", 0)),
    )

    patch_summary = _patch_summary(patch)
    integration = {
        "run_id": run_id,
        "iteration": next_iter,
        "accepted": accepted,
        "verdict": verdict,
        "target_section": target_section,
        "patch_summary": patch_summary,
        "rationale": str(patch.get("rationale", "")),
        "diff": prompt_diff,
        "bench_diff": bench_diff,
        "scores": {
            "before": delta.get("before", {}),
            "after": delta.get("after", {}),
        },
        "delta": delta,
        "verdict_reason": verdict_reason,
    }
    (iter_path / "integration.json").write_text(
        json.dumps(integration, indent=2) + "\n", encoding="utf-8"
    )

    handoff = build_handoff(
        iteration=next_iter,
        accepted=accepted,
        verdict=verdict,
        target_section=target_section,
        patch_summary=patch_summary,
        bench_diff=bench_diff,
        delta=delta,
        verdict_reason=verdict_reason,
        patch=patch,
    )
    write_handoff(iter_path, handoff)
    write_changelog(iter_path, handoff=handoff, diagnosis=diagnosis, plan=plan)

    meta["latest_iter"] = next_iter
    _update_iteration_ranking(
        meta,
        run_id=run_id,
        iteration=next_iter,
        report=report,
        accepted=accepted,
    )
    if accepted:
        meta["latest_accepted_iter"] = next_iter
        meta["consecutive_rejects"] = 0
    else:
        meta["consecutive_rejects"] = int(meta.get("consecutive_rejects", 0)) + 1

    save_meta(run_id, meta)

    totals = report.get("totals", {})
    prior_passed = prior_report.get("totals", {}).get("passed", 0)
    info(
        "run %s iter %d: %s — %d/%d passed (%+d) [%s] %s",
        run_id,
        next_iter,
        "ACCEPTED" if accepted else "REJECTED",
        totals.get("passed", 0),
        totals.get("cases", 0),
        int(totals.get("passed", 0)) - int(prior_passed),
        verdict,
        verdict_reason,
    )
    append_jsonl(
        run_dir(run_id) / "lineage.jsonl",
        {
            "iter": next_iter,
            "parent_iter": base_iter,
            "parent_accepted_iter": base_iter,
            "accepted": accepted,
            "verdict": verdict,
            "snapshot": f"runs/{run_id}/iter-{next_iter}/",
            "prompt_diff": f"iter-{next_iter}/prompt_diff.json",
            "bench_cases": bench_cases,
            "passed": totals.get("passed", 0),
            "key_metrics": extract_key_metrics(report),
            "target_section": target_section,
            "integration_path": f"iter-{next_iter}/integration.json",
        },
    )
    append_jsonl(
        run_dir(run_id) / "integration_history.jsonl",
        integration,
    )
    append_jsonl(
        run_dir(run_id) / "summary.jsonl",
        {
            "iter": next_iter,
            "passed": totals.get("passed", 0),
            "total": totals.get("cases", 0),
            "key_metrics": extract_key_metrics(report),
            "accepted": accepted,
            "verdict": verdict,
        },
    )
    update_run_registry(
        run_id,
        best_passed=totals.get("passed", 0) if accepted else meta.get("best_passed"),
        latest_iter=next_iter,
        status="active",
    )

    return {
        "iteration": next_iter,
        "accepted": accepted,
        "verdict": verdict,
        "passed": totals.get("passed", 0),
        "verdict_reason": verdict_reason,
    }


def run_iterations(
    run_id: str,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    gateway_url: str | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    info("run %s: up to %d improvement iteration(s)", run_id, max_iterations)
    for i in range(max_iterations):
        meta = load_meta(run_id)
        if int(meta.get("consecutive_rejects", 0)) >= MAX_CONSECUTIVE_REJECTS:
            warn(
                "run %s: stopping after %d consecutive rejects",
                run_id,
                MAX_CONSECUTIVE_REJECTS,
            )
            break
        info("run %s: iteration %d/%d", run_id, i + 1, max_iterations)
        result = run_single_iteration(run_id, gateway_url=gateway_url, force=force)
        results.append(result)
        force = False
    info("run %s: finished %d iteration(s)", run_id, len(results))
    return results


def finalize_run(
    run_id: str,
    *,
    iteration: int | None = None,
    best_passes: bool = False,
) -> Path:
    meta = load_meta(run_id)
    if iteration is not None:
        export_iter = iteration
    elif best_passes:
        export_iter = _resolve_best_passes_iter(meta)
    else:
        export_iter = _resolve_promotion_iter(meta)
    source = iter_dir(run_id, export_iter)
    if not source.is_dir():
        raise FileNotFoundError(f"iter-{export_iter}/ not found for run {run_id}")

    final_dir = run_dir(run_id) / "final"
    if final_dir.exists():
        shutil.rmtree(final_dir)
    final_dir.mkdir(parents=True)

    shutil.copytree(source / "prompts", final_dir / "prompts")
    shutil.copytree(source / "bench", final_dir / "bench")

    report_path = source / "report.json"
    if report_path.is_file():
        shutil.copy2(report_path, final_dir / "report.json")

    handoff_path = source / "handoff.json"
    if handoff_path.is_file():
        shutil.copy2(handoff_path, final_dir / "handoff.json")

    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    composite_scores = meta.get("composite_scores") or {}
    manifest = {
        "run_id": run_id,
        "export_iter": export_iter,
        "promotion_iter": _resolve_promotion_iter(meta),
        "best_passes_iter": _resolve_best_passes_iter(meta),
        "latest_accepted_iter": int(meta.get("latest_accepted_iter", 0)),
        "composite_score": composite_scores.get(str(export_iter)),
        "passed": report.get("totals", {}).get("passed", 0),
        "cases": report.get("totals", {}).get("cases", 0),
        "key_metrics": extract_key_metrics(report),
        "promotion_checklist": [
            "Copy final/prompts/rules.json → compact_prompt_rules.json (or prod overlay path)",
            "Copy final/prompts/overlay.json → compact_prompt_overlay.json",
            "Review final/bench/ before merging into data/domain/bench/",
            "Reload gateway prompts and run prod bench",
        ],
    }
    (final_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    lineage = load_jsonl(run_dir(run_id) / "lineage.jsonl")
    (final_dir / "lineage_summary.md").write_text(
        build_lineage_summary(run_id, lineage), encoding="utf-8"
    )

    meta["status"] = "finalized"
    save_meta(run_id, meta)
    update_run_registry(run_id, status="finalized")
    info("finalized run %s from iter-%d → %s", run_id, export_iter, final_dir)
    return final_dir


def status_run(run_id: str) -> dict[str, Any]:
    meta = load_meta(run_id)
    lineage = load_jsonl(run_dir(run_id) / "lineage.jsonl")
    composite_scores = meta.get("composite_scores") or {}
    return {
        "meta": meta,
        "lineage": lineage,
        "ranking": {
            "latest_accepted_iter": int(meta.get("latest_accepted_iter", 0)),
            "best_passes_iter": _resolve_best_passes_iter(meta),
            "promotion_iter": _resolve_promotion_iter(meta),
            "composite_scores": composite_scores,
        },
    }


def context_for_iteration(run_id: str, iteration: int) -> str:
    meta = load_meta(run_id)
    base_iter = int(meta.get("latest_accepted_iter", 0))
    base_path = iter_dir(run_id, base_iter)
    failure_report_path = resolve_failure_report_path(run_id, iteration, base_iter)
    prior_report = None
    if base_iter >= 0:
        prior_path = iter_dir(run_id, base_iter) / "report.json"
        if prior_path.is_file():
            prior_report = json.loads(prior_path.read_text(encoding="utf-8"))
    from compact_prompt_tune.self_improve.context import (
        load_best_report,
        load_previous_handoff,
        load_recent_accepted_tradeoffs,
    )

    return build_context_xml(
        run_id=run_id,
        iteration=iteration,
        base_iter_path=base_path,
        failure_report_path=failure_report_path,
        prior_integrations=load_integrations(run_id),
        previous_handoff=load_previous_handoff(run_id, iteration),
        prior_report=prior_report,
        best_report=load_best_report(run_id, meta),
        previous_delta=load_previous_delta(run_id, iteration),
        recent_rejects=load_recent_reject_history(run_id, iteration),
        recent_accepted_tradeoffs=load_recent_accepted_tradeoffs(run_id, iteration),
    )
