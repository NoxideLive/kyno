#!/usr/bin/env -S python3 -u
"""CLI for compact prompt tuning workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from classifier_bench.io import configure_unbuffered_output

configure_unbuffered_output()

from compact_prompt_tune.analyze import analyze_report, format_analysis
from compact_prompt_tune.bench import run_iteration_bench
from compact_prompt_tune.reload import main_reload
from compact_prompt_tune.state import iter_report_path, load_state


def cmd_bench(args: argparse.Namespace) -> int:
    output = run_iteration_bench(args.iteration, gateway_url=args.gateway_url)
    print(f"Wrote {output}", flush=True)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = (ROOT / report_path).resolve()
    summary = analyze_report(report_path, top_n=args.top)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_analysis(summary))
    return 0


def cmd_reload(_args: argparse.Namespace) -> int:
    return main_reload()


def cmd_status(_args: argparse.Namespace) -> int:
    state = load_state()
    print(json.dumps(state, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact prompt tuning CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="Run bench for iteration N")
    bench.add_argument("--iteration", type=int, required=True)
    bench.add_argument("--gateway-url", type=str, default=None)
    bench.set_defaults(func=cmd_bench)

    analyze = sub.add_parser("analyze", help="Analyze a bench report")
    analyze.add_argument("--report", type=str, required=True)
    analyze.add_argument("--top", type=int, default=15)
    analyze.add_argument("--json", action="store_true")
    analyze.set_defaults(func=cmd_analyze)

    reload_cmd = sub.add_parser("reload", help="Reload gateway prompts")
    reload_cmd.set_defaults(func=cmd_reload)

    status = sub.add_parser("status", help="Show tuning state.json")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
