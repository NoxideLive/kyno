"""Aggregate CAPS section JSON into domain topic list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.phases import ALL_PHASES
from pipeline.repo_paths import domain_dir, syllabus_root

FET_FALLBACK_TOPICS = [
    "Functions",
    "Algebra",
    "Trigonometry",
    "Analytical Geometry",
    "Euclidean Geometry",
    "Statistics",
    "Calculus",
    "Probability",
]

META_TOPICS = [
    "Annual Teaching Plans (ATP)",
    "Syllabus and curriculum",
    "Assessments and exams",
    "Exam preparation",
]


def normalize_topic(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:]


def load_phase_sections(phase: str) -> dict[str, Any] | None:
    path = (
        syllabus_root()
        / "phases"
        / phase
        / "mathematics"
        / "caps-sections.json"
    )
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate_topics() -> list[str]:
    seen: set[str] = set()
    topics: list[str] = []

    def add(name: str) -> None:
        normalized = normalize_topic(name)
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            topics.append(normalized)

    for phase in ALL_PHASES:
        data = load_phase_sections(phase)
        if not data:
            continue
        for name in data.get("content_area_names", []):
            add(str(name))
        for grade_data in data.get("grades", {}).values():
            for name in grade_data.get("content_area_names", []):
                add(str(name))
            for phrase in grade_data.get("topic_phrases", []):
                add(str(phrase))

    for name in FET_FALLBACK_TOPICS:
        add(name)
    for name in META_TOPICS:
        add(name)

    return topics


def write_topic_list() -> dict[str, Any]:
    topics = aggregate_topics()
    payload = {
        "subject": "mathematics",
        "curriculum": "CAPS",
        "language": "en",
        "topics": topics,
    }
    out_path = domain_dir() / "caps_topic_list.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(out_path), "topic_count": len(topics)}
