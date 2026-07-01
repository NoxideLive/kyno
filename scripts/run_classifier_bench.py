#!/usr/bin/env -S python3 -u
"""Run classifier benchmark against phi-gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from classifier_bench.io import configure_unbuffered_output

configure_unbuffered_output()

from classifier_bench.load import DEFAULT_BENCH_DIR, load_bench_config, load_suites
from classifier_bench.runner import run_bench


def default_gateway_url() -> str | None:
    url = os.environ.get("PHI_GATEWAY_URL", "").strip()
    return url or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run classifier benchmark")
    parser.add_argument(
        "--bench-dir",
        type=Path,
        default=DEFAULT_BENCH_DIR,
        help="Bench fixture directory",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=["jailbreak", "domain", "switch"],
        help="Run only selected suite(s); repeatable",
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=default_gateway_url(),
        help="Phi gateway URL (default PHI_GATEWAY_URL env)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Parallel workers (0 = auto from bench.config.json, default 2)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report output path (default from bench.config.json)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    args = parser.parse_args()

    if not args.gateway_url:
        print("Set PHI_GATEWAY_URL or pass --gateway-url", file=sys.stderr, flush=True)
        return 1

    bench_dir = args.bench_dir if args.bench_dir.is_absolute() else (ROOT / args.bench_dir).resolve()
    config = load_bench_config(bench_dir)
    suites = load_suites(bench_dir, suite_names=args.suite)

    report = run_bench(
        gateway_url=args.gateway_url.rstrip("/"),
        suites=suites,
        workers=args.workers,
        bench_config=config,
        fail_fast=args.fail_fast,
    )

    output_rel = config.get("output_report", "report.json")
    output_path = args.output or (bench_dir / output_rel)
    if not output_path.is_absolute():
        output_path = (ROOT / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    totals = report["totals"]
    print(
        f"Done: {totals['passed']}/{totals['cases']} passed "
        f"in {report['elapsed_sec']}s ({report['cases_per_sec']}/s)",
        flush=True,
    )
    print(f"Report → {output_path}", flush=True)
    for suite, summary in report["suites"].items():
        print(f"  {suite}: {summary['passed']}/{summary['cases']} passed", flush=True)
    if totals["failed"]:
        print(f"Failures: {totals['failed']}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
