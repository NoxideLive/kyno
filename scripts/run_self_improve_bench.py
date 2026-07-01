#!/usr/bin/env -S python3 -u
"""CLI for the self-improve compact prompt bench runner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from classifier_bench.io import configure_unbuffered_output

configure_unbuffered_output()

from compact_prompt_tune.reload import load_api_key_from_env_file
from compact_prompt_tune.self_improve.groq_client import load_groq_key_from_env_file
from compact_prompt_tune.self_improve.log import configure_logging
from compact_prompt_tune.self_improve.runner import (
    context_for_iteration,
    finalize_run,
    init_run,
    run_iterations,
    run_single_iteration,
    status_run,
)
from compact_prompt_tune.self_improve.state import (
    list_runs,
    resolve_run_id,
    set_active_run,
)


def cmd_init(args: argparse.Namespace) -> int:
    load_api_key_from_env_file(str(ROOT / ".env.local"))
    load_groq_key_from_env_file(str(ROOT / ".env.local"))
    run_id = init_run(
        run_id=args.run_id,
        seed_run_id=args.seed_run,
        force=args.force,
        gateway_url=args.gateway_url,
    )
    print(f"Initialized run {run_id}", flush=True)
    print(f"Active run set to {run_id}", flush=True)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    load_api_key_from_env_file(str(ROOT / ".env.local"))
    load_groq_key_from_env_file(str(ROOT / ".env.local"))
    run_id = resolve_run_id(args.run_id)
    results = run_iterations(
        run_id,
        max_iterations=args.max_iterations,
        gateway_url=args.gateway_url,
        force=args.force,
    )
    print(json.dumps(results, indent=2), flush=True)
    return 0


def cmd_iteration(args: argparse.Namespace) -> int:
    load_api_key_from_env_file(str(ROOT / ".env.local"))
    load_groq_key_from_env_file(str(ROOT / ".env.local"))
    run_id = resolve_run_id(args.run_id)
    result = run_single_iteration(
        run_id,
        iteration=args.number,
        force=args.force,
        gateway_url=args.gateway_url,
    )
    print(json.dumps(result, indent=2), flush=True)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    run_id = resolve_run_id(args.run_id)
    payload = status_run(run_id)
    print(json.dumps(payload, indent=2), flush=True)
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    run_id = resolve_run_id(args.run_id)
    xml = context_for_iteration(run_id, args.iteration)
    print(xml, flush=True)
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    run_id = resolve_run_id(args.run_id)
    final_dir = finalize_run(run_id, iteration=args.iteration)
    print(f"Exported final bundle to {final_dir}", flush=True)
    return 0


def cmd_runs_list(_args: argparse.Namespace) -> int:
    rows = list_runs()
    print(json.dumps(rows, indent=2), flush=True)
    return 0


def cmd_runs_use(args: argparse.Namespace) -> int:
    set_active_run(args.run_id)
    print(f"Active run set to {args.run_id}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Self-improve bench runner for compact classification prompts",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging (Groq token usage, etc.)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a new self-improve run")
    init_p.add_argument("--run-id", type=str, default=None)
    init_p.add_argument("--seed-run", type=str, default=None, dest="seed_run")
    init_p.add_argument("--force", action="store_true")
    init_p.add_argument("--gateway-url", type=str, default=None)
    init_p.set_defaults(func=cmd_init)

    run_p = sub.add_parser("run", help="Continue run for up to N iterations")
    run_p.add_argument("--run-id", type=str, default=None)
    run_p.add_argument("--max-iterations", type=int, default=5)
    run_p.add_argument("--force", action="store_true", help="Re-run if next iter dir already exists")
    run_p.add_argument("--gateway-url", type=str, default=None)
    run_p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    run_p.set_defaults(func=cmd_run)

    iter_p = sub.add_parser("iteration", help="Run a single iteration")
    iter_p.add_argument("--run-id", type=str, default=None)
    iter_p.add_argument("--number", type=int, required=True)
    iter_p.add_argument("--force", action="store_true")
    iter_p.add_argument("--gateway-url", type=str, default=None)
    iter_p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    iter_p.set_defaults(func=cmd_iteration)

    status_p = sub.add_parser("status", help="Show run status and lineage")
    status_p.add_argument("--run-id", type=str, default=None)
    status_p.set_defaults(func=cmd_status)

    context_p = sub.add_parser("context", help="Print improver context for an iteration")
    context_p.add_argument("--run-id", type=str, default=None)
    context_p.add_argument("--iteration", type=int, required=True)
    context_p.set_defaults(func=cmd_context)

    finalize_p = sub.add_parser("finalize", help="Export best_iter bundle for prod promotion")
    finalize_p.add_argument("--run-id", type=str, default=None)
    finalize_p.add_argument("--iteration", type=int, default=None)
    finalize_p.set_defaults(func=cmd_finalize)

    runs_p = sub.add_parser("runs", help="Manage run registry")
    runs_sub = runs_p.add_subparsers(dest="runs_command", required=True)

    runs_list = runs_sub.add_parser("list", help="List all runs")
    runs_list.set_defaults(func=cmd_runs_list)

    runs_use = runs_sub.add_parser("use", help="Set active run")
    runs_use.add_argument("--run-id", type=str, required=True)
    runs_use.set_defaults(func=cmd_runs_use)

    args = parser.parse_args()
    configure_logging(verbose=getattr(args, "verbose", False))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
