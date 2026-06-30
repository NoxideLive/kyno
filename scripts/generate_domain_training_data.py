#!/usr/bin/env python3
"""Generate on_topic / off_topic training data for CAPS Mathematics domain classifier.

Output: training/domain/data.jsonl (and train/val/test splits)

Example:
  python3 generate_domain_training_data.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

SYLLABUS_ROOT = Path("data/syllabus")
OUTPUT_DIR = Path("training/domain")

ON_TOPIC_TEMPLATES = [
    "What does Grade {grade} CAPS Mathematics cover in Term {term}?",
    "Explain {topic} for Grade {grade} CAPS Maths.",
    "What is in the ATP week {week} for Grade {grade} Mathematics?",
    "How do I teach {topic} according to CAPS Grade {grade}?",
    "What are the assessment requirements for {topic} in Grade {grade} Maths?",
    "Help me understand {topic} for my Grade {grade} CAPS exam.",
    "What prior knowledge is needed for {topic} in Grade {grade}?",
    "Summarize the CAPS content for {topic} Grade {grade}.",
    "Wat dek Graad {grade} CAPS Wiskunde vir {topic}?",
    "Grade {grade} mathematics study help: {topic}",
    "What topics are in Term {term} of Grade {grade} CAPS Mathematics ATP?",
    "How is {topic} assessed in CAPS Grade {grade} Mathematics?",
]

OFF_TOPIC_TEMPLATES = [
    "What is the weather in Cape Town today?",
    "Write me a Python script to sort a list.",
    "Explain Grade {grade} Life Orientation assessment rubric.",
    "Help with Grade {grade} Mathematical Literacy interest rates.",
    "What are the causes of World War 2?",
    "How do I fix my car engine?",
    "Grade {grade} Natural Sciences photosynthesis lesson plan.",
    "IB Mathematics HL vectors question.",
    "Cambridge IGCSE Maths past paper help.",
    "Give me relationship advice.",
    "Grade {grade} English Home Language poetry analysis.",
    "What is the capital of France?",
    "Help with Grade {grade} History CAPS essay.",
    "Write a JavaScript React component.",
    "Grade {grade} Geography map work worksheet.",
]

META_ON_TOPIC = [
    "What is CAPS?",
    "What is an Annual Teaching Plan for Mathematics?",
    "How does DBE structure CAPS Mathematics assessments?",
    "What is the difference between CAPS Mathematics and Mathematical Literacy?",
    "Wat is CAPS Wiskunde?",
]


def load_topics(syllabus_root: Path) -> list[dict]:
    rows: list[dict] = []
    for grade in range(1, 13):
        topics_path = syllabus_root / f"grade-{grade}" / "mathematics" / "topics.json"
        if not topics_path.exists():
            continue
        data = json.loads(topics_path.read_text(encoding="utf-8"))
        for term_block in data.get("terms", []):
            term = term_block.get("term", 1)
            for week_block in term_block.get("weeks", []):
                week = week_block.get("week", 1)
                for topic in week_block.get("topics", [])[:8]:
                    clean = re.sub(r"\s+", " ", topic).strip()
                    if len(clean) > 15:
                        rows.append(
                            {"grade": grade, "term": term, "week": week, "topic": clean[:120]}
                        )
    return rows


def generate_on_topic(topic_rows: list[dict], target: int) -> list[dict]:
    examples: list[dict] = []
    if not topic_rows:
        for grade in range(1, 13):
            for tmpl in ON_TOPIC_TEMPLATES[:4]:
                examples.append(
                    {
                        "text": tmpl.format(
                            grade=grade, term=1, week=1, topic="whole numbers"
                        ),
                        "label": "on_topic",
                    }
                )
        return examples[:target]

    random.shuffle(topic_rows)
    i = 0
    while len(examples) < target:
        row = topic_rows[i % len(topic_rows)]
        tmpl = ON_TOPIC_TEMPLATES[i % len(ON_TOPIC_TEMPLATES)]
        examples.append(
            {
                "text": tmpl.format(**row),
                "label": "on_topic",
            }
        )
        i += 1

    for text in META_ON_TOPIC:
        examples.append({"text": text, "label": "on_topic"})

    return examples[:target]


def generate_off_topic(target: int) -> list[dict]:
    examples: list[dict] = []
    i = 0
    while len(examples) < target:
        grade = random.randint(1, 12)
        tmpl = OFF_TOPIC_TEMPLATES[i % len(OFF_TOPIC_TEMPLATES)]
        examples.append(
            {
                "text": tmpl.format(grade=grade, topic="algebra"),
                "label": "off_topic",
            }
        )
        i += 1
    return examples


def write_splits(rows: list[dict], output_dir: Path) -> None:
    random.shuffle(rows)
    n = len(rows)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)

    splits = {
        "data.jsonl": rows,
        "train.jsonl": rows[:train_end],
        "val.jsonl": rows[train_end:val_end],
        "test.jsonl": rows[val_end:],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows in splits.items():
        path = output_dir / name
        with path.open("w", encoding="utf-8") as handle:
            for row in split_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(split_rows)} rows → {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--syllabus-root", type=Path, default=SYLLABUS_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--total", type=int, default=700)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    topic_rows = load_topics(args.syllabus_root)

    on_target = int(args.total * 0.7)
    off_target = args.total - on_target

    rows = generate_on_topic(topic_rows, on_target) + generate_off_topic(off_target)
    random.shuffle(rows)
    write_splits(rows, args.output)

    on_count = sum(1 for r in rows if r["label"] == "on_topic")
    print(f"Total: {len(rows)} ({on_count} on_topic, {len(rows) - on_count} off_topic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
