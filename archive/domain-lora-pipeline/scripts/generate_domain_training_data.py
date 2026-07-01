#!/usr/bin/env python3
"""Generate on_topic / off_topic training data for CAPS Mathematics domain classifier.

Template-based fallback. For coupled LLM pipeline use build_domain_training_data.py.

Example:
  python3 scripts/generate_domain_training_data.py
  python3 scripts/generate_domain_training_data.py --total 1200 --config training/domain/pipeline.config.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from domain_pipeline_config import load_pipeline_config  # noqa: E402
from training_dedupe import dedupe_training_rows  # noqa: E402
from training_io import load_jsonl, to_training_rows, write_splits  # noqa: E402

ON_TOPIC_TEMPLATES = [
    "What does Grade {grade} CAPS Mathematics cover in Term {term}?",
    "Explain {topic} for Grade {grade} CAPS Maths.",
    "What is in the ATP week {week} for Grade {grade} Mathematics?",
    "How do I teach {topic} according to CAPS Grade {grade}?",
    "What are the assessment requirements for {topic} in Grade {grade} Maths?",
    "Help me understand {topic} for my Grade {grade} CAPS exam.",
    "What prior knowledge is needed for {topic} in Grade {grade}?",
    "Summarize the CAPS content for {topic} Grade {grade}.",
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
]

SHORT_ON_TOPIC = [
    "{topic}",
    "{topic}?",
    "Grade {grade} {topic}",
    "help with {topic}",
    "what about {topic}",
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
                    if len(clean) > 8:
                        short = clean.split(":")[0].split("—")[0].strip()[:40]
                        rows.append(
                            {
                                "grade": grade,
                                "term": term,
                                "week": week,
                                "topic": clean[:120],
                                "short_topic": short,
                            }
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
    templates = ON_TOPIC_TEMPLATES + SHORT_ON_TOPIC
    while len(examples) < target:
        row = topic_rows[i % len(topic_rows)]
        tmpl = templates[i % len(templates)]
        topic_key = "topic" if "{topic}" in tmpl else "short_topic"
        fmt = {**row, "topic": row.get(topic_key, row["topic"])}
        examples.append(
            {
                "text": tmpl.format(**fmt),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=1200)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pipeline config (default: training/domain/pipeline.config.json)",
    )
    args = parser.parse_args()

    try:
        config = load_pipeline_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    random.seed(config.seed)
    topic_rows = load_topics(config.syllabus_root)

    on_ratio = 1.0 - config.target_off_ratio
    on_target = int(args.total * on_ratio)
    off_target = args.total - on_target

    curated_raw = load_jsonl(config.curated_path)
    curated_rows = to_training_rows(curated_raw)

    generated: list[dict] = []
    generated.extend(generate_on_topic(topic_rows, on_target))
    generated.extend(generate_off_topic(off_target))

    if config.dedupe_enabled:
        generated, stats = dedupe_training_rows(
            generated,
            threshold=config.dedupe_threshold,
        )
        print(
            f"Dedupe: {stats['input']} → {stats['output']} "
            f"(exact -{stats['exact_removed']}, lexical -{stats['lexical_removed']})"
        )

    write_splits(
        generated,
        config.output_dir,
        seed=config.seed,
        curated_rows=curated_rows,
    )

    all_rows = generated + curated_rows
    on_count = sum(1 for r in all_rows if r["label"] == "on_topic")
    print(f"Total: {len(all_rows)} ({on_count} on_topic, {len(all_rows) - on_count} off_topic)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
