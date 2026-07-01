"""Grade/phase mapping for CAPS pipeline."""

from __future__ import annotations

from typing import Literal

Phase = Literal["foundation", "intermediate", "senior", "fet"]

ALL_PHASES: tuple[Phase, ...] = ("foundation", "intermediate", "senior", "fet")

PHASE_GRADES: dict[Phase, tuple[int, ...]] = {
    "foundation": (1, 2, 3),
    "intermediate": (4, 5, 6),
    "senior": (7, 8, 9),
    "fet": (10, 11, 12),
}

REPRESENTATIVE_GRADE: dict[Phase, int] = {
    "foundation": 1,
    "intermediate": 4,
    "senior": 7,
    "fet": 10,
}
