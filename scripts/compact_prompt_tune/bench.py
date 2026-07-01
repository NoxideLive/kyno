"""Run classifier bench for a tuning iteration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from classifier_bench.load import DEFAULT_BENCH_DIR, load_bench_config, load_suites
from classifier_bench.runner import run_bench

from compact_prompt_tune.state import TUNING_DIR, append_cycle, iter_report_path


def default_gateway_url() -> str:
    return os.environ.get("PHI_GATEWAY_URL", "http://localhost:8090").strip()


def run_iteration_bench(iteration: int, *, gateway_url: str | None = None) -> Path:
    url = (gateway_url or default_gateway_url()).rstrip("/")
    bench_dir = DEFAULT_BENCH_DIR if DEFAULT_BENCH_DIR.is_absolute() else (ROOT / DEFAULT_BENCH_DIR).resolve()
    config = load_bench_config(bench_dir)
    suites = load_suites(bench_dir)

    report = run_bench(
        gateway_url=url,
        suites=suites,
        workers=0,
        bench_config=config,
        fail_fast=False,
    )

    output_path = iter_report_path(iteration)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    append_cycle(iteration=iteration, report_path=output_path, report=report)
    return output_path
