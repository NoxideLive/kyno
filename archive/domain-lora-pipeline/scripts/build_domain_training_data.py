#!/usr/bin/env python3
"""Coupled syllabus → training data pipeline.

Pass 1: ATP chunk text → grounded topics/skills (topics.json) via extract model
Pass 2: same chunk + CAPS context → labeled examples via generate model

Tuning lives in training/domain/pipeline.config.json.

Example:
  python3 scripts/build_domain_training_data.py --grade 6
  python3 scripts/build_domain_training_data.py --all-grades
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from caps_chunker import (  # noqa: E402
    find_caps_pdf,
    grade_caps_summary,
    load_phase_caps_sections,
)
from chunk_pipeline import ChunkWorkContext, process_single_chunk  # noqa: E402
from domain_generation import generate_grade_off_topic  # noqa: E402
from domain_pipeline_config import PipelineConfig, load_pipeline_config  # noqa: E402
from groq_rate_limiter import get_rate_limiter  # noqa: E402
from pipeline_timing import GradeProgress, TimingTracker  # noqa: E402
from syllabus_chunker import load_grade_chunks  # noqa: E402
from syllabus_phases import grade_to_phase  # noqa: E402
from training_balance import label_counts, top_up_off_topic  # noqa: E402
from training_dedupe import dedupe_training_rows  # noqa: E402
from training_io import load_jsonl, to_training_rows, write_splits  # noqa: E402

DOMAIN_SPEC_PATH = ROOT / "docs" / "domain-spec.md"


def load_domain_spec() -> str:
    if DOMAIN_SPEC_PATH.is_file():
        return DOMAIN_SPEC_PATH.read_text(encoding="utf-8")
    return "CAPS Mathematics Grades 1–12 only."


def merge_weeks_into_topics(
    grade: int,
    atp_pdf: Path,
    weeks: list[dict[str, Any]],
    *,
    caps_pdf: Path | None = None,
    caps_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    terms_map: dict[int, dict[int, dict]] = {}
    for week_row in weeks:
        term = int(week_row.get("term", 1))
        week = int(week_row.get("week", 1))
        terms_map.setdefault(term, {})[week] = {
            "week": week,
            "topics": week_row.get("topics", []),
            "skills": week_row.get("skills", []),
            "content_area": week_row.get("content_area", ""),
            "short_phrases": week_row.get("short_phrases", []),
            "caps_excerpt": week_row.get("caps_excerpt", ""),
            "assessment_notes": week_row.get("assessment_notes", []),
        }

    terms: list[dict] = []
    for term_num in sorted(terms_map):
        weeks_list = [terms_map[term_num][w] for w in sorted(terms_map[term_num])]
        terms.append({"term": term_num, "weeks": weeks_list})

    return {
        "grade": grade,
        "phase": grade_to_phase(grade),
        "subject": "mathematics",
        "curriculum": "CAPS",
        "sources": {
            "atp_pdf": str(atp_pdf.resolve()),
            "caps_pdf": str(caps_pdf.resolve()) if caps_pdf else "",
        },
        "caps_summary": caps_summary or {
            "overview_excerpt": "",
            "aims_excerpt": "",
            "assessment_excerpt": "",
            "content_area_names": [],
        },
        "terms": terms,
        "term_count": len(terms),
        "week_count": sum(len(t["weeks"]) for t in terms),
    }


def process_grade(
    grade: int,
    *,
    config: PipelineConfig,
    dry_run: bool,
    timing: TimingTracker,
) -> tuple[list[dict], dict[str, Any]]:
    domain_spec = load_domain_spec()
    limiter = get_rate_limiter()
    grade_start_stats = limiter.all_stats()

    report: dict[str, Any] = {
        "grade": grade,
        "chunks": 0,
        "extracted_weeks": 0,
        "examples_kept": 0,
        "examples_dropped": [],
        "caps_sections_loaded": False,
        "weeks_with_caps_match": 0,
        "extract_errors": [],
        "generate_errors": [],
        "short_stats": {
            "requested": 0,
            "kept": 0,
            "chunks_met_quota": 0,
            "chunks_processed": 0,
        },
        "models": {
            "extract": config.extract_model,
            "generate": config.generate_model,
        },
    }

    grade_dir = config.syllabus_root / f"grade-{grade}" / "mathematics"
    caps_pdf = find_caps_pdf(grade_dir)
    phase = grade_to_phase(grade)
    phase_sections = load_phase_caps_sections(config.syllabus_root, phase)
    caps_summary = grade_caps_summary(phase_sections, grade)
    report["caps_sections_loaded"] = bool(phase_sections.get("loaded"))

    atp_pdf, chunks = load_grade_chunks(grade, config.syllabus_root)
    report["chunks"] = len(chunks)
    if dry_run:
        print(f"Grade {grade}: {len(chunks)} chunks (dry run)")
        return [], report

    ctx = ChunkWorkContext(
        grade=grade,
        extract_model=config.extract_model,
        generate_model=config.generate_model,
        domain_spec=domain_spec,
        phase_sections=phase_sections,
        caps_summary=caps_summary,
        examples_per_week=config.examples_per_week,
        on_off_ratio=config.on_off_ratio,
        min_short_per_chunk=config.min_short_per_chunk,
        ground_threshold=config.ground_threshold,
        hard_off_ratio=config.hard_off_ratio,
    )

    progress = GradeProgress(grade, len(chunks))
    chunk_results: list[Any] = []

    timing.start_phase(f"grade_{grade}_chunks")
    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        futures = {
            pool.submit(process_single_chunk, i, chunk, ctx): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            result = future.result()
            chunk_results.append(result)
            progress.tick()
            if result.extract_error:
                report["extract_errors"].append(
                    {
                        "term": result.week_data.get("term"),
                        "week": result.week_data.get("week"),
                        "error": result.extract_error[:500],
                    }
                )
                print(
                    f"  Grade {grade} term {result.week_data.get('term')} "
                    f"week {result.week_data.get('week')}: extract failed"
                )
            if result.generate_error:
                report["generate_errors"].append(
                    {
                        "term": result.week_data.get("term"),
                        "week": result.week_data.get("week"),
                        "error": result.generate_error[:500],
                    }
                )
                print(
                    f"  Grade {grade} term {result.week_data.get('term')} "
                    f"week {result.week_data.get('week')}: generate failed"
                )
            print(progress.format_line(limiter.all_stats()))

    chunk_pool_ms = timing.end_phase(f"grade_{grade}_chunks")
    chunk_results.sort(key=lambda r: r.chunk_index)

    extracted_weeks: list[dict[str, Any]] = []
    training_rows: list[dict] = []

    for result in chunk_results:
        extracted_weeks.append(result.week_data)
        training_rows.extend(result.training_rows)
        report["examples_dropped"].extend(result.dropped)
        report["short_stats"]["requested"] += result.short_stats.get("short_requested", 0)
        report["short_stats"]["kept"] += result.short_stats.get("short_kept", 0)
        report["short_stats"]["chunks_processed"] += result.short_stats.get(
            "chunks_processed", 0
        )
        if result.short_stats.get("short_quota_met"):
            report["short_stats"]["chunks_met_quota"] += 1
        if result.caps_matched:
            report["weeks_with_caps_match"] += 1
        for key, ms in result.timing.items():
            timing.record(f"grade_{grade}_{key}", ms)

    report["extracted_weeks"] = sum(
        1 for w in extracted_weeks if w.get("topics") or w.get("skills")
    )

    topics_doc = merge_weeks_into_topics(
        grade,
        atp_pdf,
        extracted_weeks,
        caps_pdf=caps_pdf,
        caps_summary=caps_summary,
    )
    out_path = config.syllabus_root / f"grade-{grade}" / "mathematics" / "topics.json"
    out_path.write_text(json.dumps(topics_doc, indent=2), encoding="utf-8")
    print(
        f"  Grade {grade}: {topics_doc['term_count']} terms, "
        f"{topics_doc['week_count']} weeks → {out_path}"
    )

    timing.start_phase(f"grade_{grade}_off_topic")
    try:
        off_topic_extra = generate_grade_off_topic(
            grade,
            model=config.generate_model,
            count=config.off_topic_per_grade,
            domain_spec=domain_spec,
            hard_off_ratio=config.hard_off_ratio,
        )
        training_rows.extend(off_topic_extra)
        report["grade_off_topic"] = len(off_topic_extra)
    except RuntimeError as exc:
        print(f"  Grade {grade}: grade-level off_topic generation failed: {exc}")
        report["grade_off_topic"] = 0
    off_topic_ms = timing.end_phase(f"grade_{grade}_off_topic")

    grade_end_stats = limiter.all_stats()
    report["timing"] = {
        "chunk_pool_ms": round(chunk_pool_ms, 1),
        "off_topic_ms": round(off_topic_ms, 1),
        "chunks": len(chunks),
        "workers": config.workers,
    }
    report["rate_limits"] = {
        model: {
            "requests": grade_end_stats.get(model, {}).get("requests", 0)
            - grade_start_stats.get(model, {}).get("requests", 0),
            "wait_ms": round(
                grade_end_stats.get(model, {}).get("wait_ms", 0)
                - grade_start_stats.get(model, {}).get("wait_ms", 0),
                1,
            ),
            "retries": grade_end_stats.get(model, {}).get("retries", 0)
            - grade_start_stats.get(model, {}).get("retries", 0),
            "rate_limit_429": grade_end_stats.get(model, {}).get("rate_limit_429", 0)
            - grade_start_stats.get(model, {}).get("rate_limit_429", 0),
        }
        for model in {config.extract_model, config.generate_model}
    }

    report["examples_kept"] = len(training_rows)
    return training_rows, report


def aggregate_short_stats(reports: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"requested": 0, "kept": 0, "chunks_met_quota": 0, "chunks_processed": 0}
    for report in reports:
        stats = report.get("short_stats", {})
        for key in totals:
            totals[key] += int(stats.get(key, 0))
    return totals


def aggregate_rate_limits(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for report in reports:
        for model, stats in report.get("rate_limits", {}).items():
            bucket = merged.setdefault(
                model,
                {"requests": 0, "wait_ms": 0.0, "retries": 0, "rate_limit_429": 0},
            )
            bucket["requests"] += stats.get("requests", 0)
            bucket["wait_ms"] = round(bucket["wait_ms"] + stats.get("wait_ms", 0), 1)
            bucket["retries"] += stats.get("retries", 0)
            bucket["rate_limit_429"] += stats.get("rate_limit_429", 0)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Build domain training data from ATP PDFs")
    parser.add_argument("--grade", type=int, help="Grade 1–12")
    parser.add_argument("--all-grades", action="store_true")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pipeline config (default: training/domain/pipeline.config.json)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = load_pipeline_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    grades = list(range(1, 13)) if args.all_grades else [args.grade]
    if not args.all_grades and args.grade is None:
        parser.error("Specify --grade or --all-grades")

    timing = TimingTracker()
    generated_rows: list[dict] = []
    reports: list[dict] = []
    domain_spec = load_domain_spec()

    curated_raw = load_jsonl(config.curated_path)
    curated_rows = to_training_rows(curated_raw)
    if curated_rows:
        print(f"Loaded {len(curated_rows)} curated rows from {config.curated_path}")

    print(
        f"Config: {args.config or 'training/domain/pipeline.config.json'} | "
        f"extract={config.extract_model} generate={config.generate_model} "
        f"workers={config.workers}"
    )

    for grade in grades:
        print(f"Processing grade {grade}…")
        try:
            rows, report = process_grade(
                grade,
                config=config,
                dry_run=args.dry_run,
                timing=timing,
            )
            generated_rows.extend(rows)
            reports.append(report)
        except FileNotFoundError as exc:
            print(f"  Skip grade {grade}: {exc}", file=sys.stderr)

    if args.dry_run:
        return 0

    if not generated_rows and not curated_rows:
        print("No training rows generated.", file=sys.stderr)
        return 1

    training_rows = to_training_rows(generated_rows)
    pre_dedupe_counts = label_counts(training_rows)
    print(
        f"Pre-dedupe generated: {pre_dedupe_counts['on_topic']} on_topic, "
        f"{pre_dedupe_counts['off_topic']} off_topic "
        f"(+ {len(curated_rows)} curated pinned to train)"
    )

    topup_info: dict[str, Any] = {}
    timing.start_phase("global_topup")
    try:
        training_rows, topup_info = top_up_off_topic(
            training_rows,
            model=config.generate_model,
            domain_spec=domain_spec,
            target_ratio=config.target_off_ratio,
            hard_off_ratio=config.hard_off_ratio,
        )
        if topup_info.get("global_off_topup", 0):
            after = topup_info.get("label_counts_after_topup", {})
            print(
                f"Global off_topic top-up: +{topup_info['global_off_topup']} "
                f"({after.get('on_topic', 0)} on, {after.get('off_topic', 0)} off)"
            )
    except RuntimeError as exc:
        print(f"Global off_topic top-up failed: {exc}", file=sys.stderr)
        topup_info = {"global_off_topup": 0, "error": str(exc)}
    timing.end_phase("global_topup")

    pre_dedupe_counts = label_counts(training_rows)

    dedupe_stats: dict[str, Any] = {}
    timing.start_phase("dedupe")
    if config.dedupe_enabled:
        training_rows, dedupe_stats = dedupe_training_rows(
            training_rows,
            threshold=config.dedupe_threshold,
        )
        print(
            f"Dedupe: {dedupe_stats['input']} → {dedupe_stats['output']} "
            f"(exact -{dedupe_stats['exact_removed']}, lexical -{dedupe_stats['lexical_removed']})"
        )
    timing.end_phase("dedupe")

    post_dedupe_counts = label_counts(training_rows)
    total_post = post_dedupe_counts["on_topic"] + post_dedupe_counts["off_topic"]
    off_pct = (
        post_dedupe_counts["off_topic"] / total_post * 100 if total_post else 0.0
    )
    print(
        f"Post-dedupe labels: {post_dedupe_counts['on_topic']} on_topic, "
        f"{post_dedupe_counts['off_topic']} off_topic ({off_pct:.1f}% off)"
    )

    balance_warning = None
    if total_post and off_pct < 45:
        balance_warning = (
            f"off_topic ratio {off_pct:.1f}% below 45% after dedupe; "
            "raise generation.off_topic_per_grade or generation.target_off_ratio in config"
        )
        print(f"Warning: {balance_warning}", file=sys.stderr)

    write_splits(
        training_rows,
        config.output_dir,
        seed=config.seed,
        curated_rows=curated_rows,
    )

    short_stats = aggregate_short_stats(reports)
    rate_limits = aggregate_rate_limits(reports)
    rate_limits.update(get_rate_limiter().all_stats())

    report_path = config.output_dir / "generation_report.json"
    report_path.write_text(
        json.dumps(
            {
                "config": str(args.config or "training/domain/pipeline.config.json"),
                "models": {
                    "extract": config.extract_model,
                    "generate": config.generate_model,
                },
                "parallelism": {"workers": config.workers},
                "grades": reports,
                "total_rows": len(training_rows),
                "curated_rows": len(curated_rows),
                "label_counts_pre_dedupe": pre_dedupe_counts,
                "label_counts_post_dedupe": post_dedupe_counts,
                "short_stats": short_stats,
                "global_off_topup": topup_info.get("global_off_topup", 0),
                "topup_info": topup_info,
                "dedupe_stats": dedupe_stats,
                "balance_warning": balance_warning,
                "timing": timing.summary(),
                "rate_limits": rate_limits,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Report → {report_path}")
    print(f"Total wall time: {timing.summary()['total_wall_ms'] / 1000:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
