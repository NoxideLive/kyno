"""Unbuffered stdout/stderr for live bench progress."""

from __future__ import annotations

import os
import sys


def configure_unbuffered_output() -> None:
    """Line-buffer stdout/stderr; set PYTHONUNBUFFERED for child processes."""
    os.environ["PYTHONUNBUFFERED"] = "1"
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(line_buffering=True)
            except (ValueError, OSError):
                pass
