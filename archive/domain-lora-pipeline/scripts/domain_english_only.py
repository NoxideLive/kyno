"""Helpers and migration for English-only domain classification."""

from __future__ import annotations

import json
import re
from pathlib import Path

# Afrikaans / non-English user messages are off_topic for English-only scope.
NON_ENGLISH_PATTERN = re.compile(
    r"(?i)"
    r"(\bwat dek graad\b"
    r"|\bwat is caps wiskunde\b"
    r"|\bgraad\s+\d{1,2}\b.*\bwiskunde\b"
    r"|\bwiskunde\b.*\bgraad\s+\d{1,2}\b"
    r"|\bgraad\s+\d{1,2}\s+breuk\b"
    r"|\bwat is die weer\b"
    r"|\bwat dek\b.*\bwiskunde\b)"
)


def is_non_english_message(text: str) -> bool:
    return bool(NON_ENGLISH_PATTERN.search(text.strip()))


def english_equivalent(text: str) -> str | None:
    """Map Afrikaans on-topic phrasing to English for eval rows."""
    stripped = text.strip()
    match = re.match(
        r"(?i)Wat dek Graad \d+ CAPS Wiskunde vir (.+)\?",
        stripped,
    )
    if match:
        topic = match.group(1).strip()
        return f"What does CAPS cover for {topic}?"
    if re.match(r"(?i)Wat is CAPS Wiskunde\?", stripped):
        return "What is CAPS Mathematics?"
    return None


def normalize_jsonl_row(row: dict, *, eval_split: bool) -> dict:
    text = str(row["text"])
    label = str(row["label"])

    if is_non_english_message(text):
        if label == "on_topic" and eval_split:
            replacement = english_equivalent(text)
            if replacement:
                return {"text": replacement, "label": "on_topic"}
        return {"text": text, "label": "off_topic"}

    return {"text": text, "label": label}


def normalize_jsonl_file(path: Path, *, eval_split: bool) -> int:
    if not path.is_file():
        return 0
    changed = 0
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        original = json.loads(line)
        updated = normalize_jsonl_row(original, eval_split=eval_split)
        if updated != original:
            changed += 1
        rows.append(updated)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return changed


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "training" / "domain"
    eval_files = ["test.jsonl", "val.jsonl"]
    train_files = ["train.jsonl", "data.jsonl", "curated.jsonl", "regression.jsonl"]

    total = 0
    for name in eval_files:
        total += normalize_jsonl_file(root / name, eval_split=True)
    for name in train_files:
        total += normalize_jsonl_file(root / name, eval_split=False)
    print(f"Updated {total} rows across {len(eval_files) + len(train_files)} files")
