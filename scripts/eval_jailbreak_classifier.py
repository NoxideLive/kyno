#!/usr/bin/env python3
"""Evaluate jailbreak classifier — delegates to the unified bench runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "run_classifier_bench.py"),
        "--suite",
        "jailbreak",
        *sys.argv[1:],
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
