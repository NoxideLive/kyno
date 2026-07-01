"""Sync run-scoped prompts to gateway test files and run bench."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from classifier_bench.load import load_bench_config, load_suites
from classifier_bench.runner import run_bench
from compact_prompt_tune.reload import check_health, reload_prompts
from compact_prompt_tune.self_improve.log import info

RULES_TEST_PATH = ROOT / "data" / "domain" / "compact_prompt_rules_test.json"
OVERLAY_TEST_PATH = ROOT / "data" / "domain" / "compact_prompt_overlay_test.json"


def default_gateway_url() -> str:
    return os.environ.get("PHI_GATEWAY_URL", "http://localhost:8090").strip().rstrip("/")


def sync_prompts_to_test_files(rules: dict, overlay: dict) -> None:
    RULES_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_TEST_PATH.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
    OVERLAY_TEST_PATH.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")


def run_iteration_bench(
    iter_path: Path,
    *,
    gateway_url: str | None = None,
    workers: int = 0,
) -> dict:
    url = (gateway_url or default_gateway_url()).rstrip("/")
    bench_dir = iter_path / "bench"
    rules = json.loads((iter_path / "prompts" / "rules.json").read_text(encoding="utf-8"))
    overlay = json.loads((iter_path / "prompts" / "overlay.json").read_text(encoding="utf-8"))

    check_health(expect_profile="small")
    info("Syncing prompts to gateway test files (compact_test)")
    sync_prompts_to_test_files(rules, overlay)
    reload_prompts(compact_test=True)
    info("Running classifier bench against %s", url)
    try:
        config = load_bench_config(bench_dir)
        suites = load_suites(bench_dir)
        return run_bench(
            gateway_url=url,
            suites=suites,
            workers=workers,
            bench_config=config,
            fail_fast=False,
        )
    finally:
        reload_prompts(compact_test=False)
        info("Restored gateway to production prompt mode")


def write_report(iter_path: Path, report: dict) -> Path:
    path = iter_path / "report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path
