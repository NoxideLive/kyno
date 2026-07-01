"""Locate CAPS PDFs per phase."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.phases import REPRESENTATIVE_GRADE, Phase
from pipeline.repo_paths import syllabus_root


def find_caps_pdf(grade_dir: Path) -> Path | None:
    manifest_path = grade_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for doc in manifest.get("documents", []):
                if doc.get("doc_type") == "caps":
                    path = Path(doc.get("local_path", ""))
                    if path.is_file():
                        return path
        except json.JSONDecodeError:
            pass
    matches = sorted(grade_dir.glob("caps-*.pdf"))
    return matches[0] if matches else None


def phase_caps_pdf(phase: Phase) -> Path | None:
    grade = REPRESENTATIVE_GRADE[phase]
    grade_dir = syllabus_root() / f"grade-{grade}" / "mathematics"
    return find_caps_pdf(grade_dir)


def phase_sections_path(phase: Phase) -> Path:
    return (
        syllabus_root()
        / "phases"
        / phase
        / "mathematics"
        / "caps-sections.json"
    )
