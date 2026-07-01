#!/usr/bin/env python3
"""Extract high-level CAPS Mathematics topics and prompt examples for domain classification."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = ROOT / "data" / "syllabus" / "phases"
OUTPUT_DIR = ROOT / "training" / "domain"

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

ON_TOPIC_EXAMPLES = [
    {"text": "fractions", "label": "on_topic"},
    {"text": "What is CAPS?", "label": "on_topic"},
    {"text": "trigonometry", "label": "on_topic"},
    {"text": "calculus", "label": "on_topic"},
    {"text": "algebra", "label": "on_topic"},
    {"text": "whole numbers and place value", "label": "on_topic"},
    {"text": "geometry and shapes", "label": "on_topic"},
    {"text": "data handling graphs", "label": "on_topic"},
    {"text": "measurement and units", "label": "on_topic"},
    {"text": "ATP teaching plan for fractions", "label": "on_topic"},
]

OFF_TOPIC_EXAMPLES = [
    {"text": "Caps", "label": "off_topic"},
    {"text": "write in caps", "label": "off_topic"},
    {"text": "peanuts in CAPS", "label": "off_topic"},
    {"text": "Mathematical Literacy interest rates", "label": "off_topic"},
    {"text": "Natural Sciences photosynthesis", "label": "off_topic"},
    {"text": "Write me a Python script", "label": "off_topic"},
    {"text": "What's the weather in Cape Town?", "label": "off_topic"},
    {"text": "IB Mathematics vectors", "label": "off_topic"},
    {"text": "Life Orientation assessment rubric", "label": "off_topic"},
    {"text": "Wat dek Graad 6 CAPS Wiskunde vir fractions?", "label": "off_topic"},
]


def normalize_topic(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:]


def collect_content_areas() -> list[str]:
    seen: set[str] = set()
    topics: list[str] = []

    for caps_path in sorted(PHASES_DIR.glob("*/mathematics/caps-sections.json")):
        data = json.loads(caps_path.read_text(encoding="utf-8"))
        for grade_data in data.get("grades", {}).values():
            for name in grade_data.get("content_area_names", []):
                normalized = normalize_topic(name)
                key = normalized.lower()
                if normalized and key not in seen:
                    seen.add(key)
                    topics.append(normalized)

    for name in FET_FALLBACK_TOPICS:
        normalized = normalize_topic(name)
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            topics.append(normalized)

    for name in META_TOPICS:
        normalized = normalize_topic(name)
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            topics.append(normalized)

    return topics


def main() -> None:
    topics = collect_content_areas()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    topic_payload = {
        "subject": "mathematics",
        "curriculum": "CAPS",
        "language": "en",
        "topics": topics,
    }
    (OUTPUT_DIR / "caps_topic_list.json").write_text(
        json.dumps(topic_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    examples_payload = {
        "language": "en",
        "on_topic": ON_TOPIC_EXAMPLES,
        "off_topic": OFF_TOPIC_EXAMPLES,
    }
    (OUTPUT_DIR / "prompt_examples.json").write_text(
        json.dumps(examples_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(topics)} topics to {OUTPUT_DIR / 'caps_topic_list.json'}")
    print(f"Wrote {len(ON_TOPIC_EXAMPLES)} on + {len(OFF_TOPIC_EXAMPLES)} off examples")


if __name__ == "__main__":
    main()
