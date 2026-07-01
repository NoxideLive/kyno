#!/usr/bin/env python3
"""Trigger domain data pipeline rebuild on the running phi-gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_api_key() -> str:
    key = os.environ.get("PHI_GATEWAY_API_KEY", "").strip()
    if key:
        return key
    for env_path in (Path(".env.local"), Path(".env")):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PHI_GATEWAY_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError("PHI_GATEWAY_API_KEY not set")


def gateway_url() -> str:
    url = os.environ.get("PHI_GATEWAY_URL", "").strip()
    if not url:
        raise RuntimeError("PHI_GATEWAY_URL not set")
    return url.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CAPS domain pipeline on phi-gateway (requires running server)",
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=["foundation", "intermediate", "senior", "fet"],
        help="Limit to phase(s); default all",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="HTTP timeout seconds (default 1800)",
    )
    args = parser.parse_args()

    body: dict = {}
    if args.phase:
        body["phases"] = args.phase

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{gateway_url()}/pipeline/rebuild",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {load_api_key()}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            report = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(report, indent=2))
            return 0 if report.get("ok") else 1
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc.reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
