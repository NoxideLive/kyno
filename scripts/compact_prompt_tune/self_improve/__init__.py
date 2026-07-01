"""Self-improve bench runner for compact prompt tuning."""

from __future__ import annotations

__all__ = ["ROOT", "SELF_IMPROVE_ROOT"]

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SELF_IMPROVE_ROOT = ROOT / "data" / "domain" / "bench" / "self-improve"
