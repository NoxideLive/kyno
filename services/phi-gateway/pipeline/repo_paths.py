"""Repository path resolution for phi-gateway."""

from __future__ import annotations

import os
from pathlib import Path

_GATEWAY_DIR = Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    env = os.environ.get("KYNO_REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return _GATEWAY_DIR.parents[1]


def domain_dir() -> Path:
    return repo_root() / "data" / "domain"


def syllabus_root() -> Path:
    return repo_root() / "data" / "syllabus"
