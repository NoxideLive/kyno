"""Deprecated POC — use scripts/run_self_improve_bench.py instead."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "self_improve.py is deprecated.\n"
        "Use: python3 scripts/run_self_improve_bench.py init|run|iteration|finalize|status",
        file=sys.stderr,
    )
    print("See docs/self-improve-bench.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
