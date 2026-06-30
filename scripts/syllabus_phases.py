"""Shared grade/phase mapping for syllabus scripts."""

from __future__ import annotations

from typing import Literal

Phase = Literal["foundation", "intermediate", "senior", "fet"]

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


def grade_to_phase(grade: int) -> Phase:
    if grade < 1 or grade > 12:
        raise ValueError(f"Grade must be 1–12, got {grade}")
    if grade <= 3:
        return "foundation"
    if grade <= 6:
        return "intermediate"
    if grade <= 9:
        return "senior"
    return "fet"


def phase_for_grade(grade: int) -> Phase:
    return grade_to_phase(grade)
