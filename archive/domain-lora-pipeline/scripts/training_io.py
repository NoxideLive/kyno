"""JSONL I/O and train/val/test splits for domain training data."""

from __future__ import annotations

import json
import random
from pathlib import Path

from training_dedupe import normalize_text


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _dedupe_key(row: dict) -> tuple[str, str]:
    return (str(row.get("label", "")), normalize_text(str(row.get("text", ""))))


def write_splits(
    rows: list[dict],
    output_dir: Path,
    *,
    seed: int = 42,
    write_data: bool = True,
    curated_rows: list[dict] | None = None,
) -> dict[str, list[dict]]:
    curated = list(curated_rows or [])
    curated_keys = {_dedupe_key(row) for row in curated}

    pool: list[dict] = []
    for row in rows:
        key = _dedupe_key(row)
        if key in curated_keys:
            continue
        pool.append(row)

    shuffled = list(pool)
    random.Random(seed).shuffle(shuffled)
    n = len(shuffled)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)

    train_rows = shuffled[:train_end] + curated
    val_rows = shuffled[train_end:val_end]
    test_rows = shuffled[val_end:]
    all_rows = shuffled + curated

    splits = {
        "train.jsonl": train_rows,
        "val.jsonl": val_rows,
        "test.jsonl": test_rows,
    }
    if write_data:
        splits = {"data.jsonl": all_rows, **splits}

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows in splits.items():
        path = output_dir / name
        write_jsonl(path, split_rows)
        print(f"Wrote {len(split_rows)} rows → {path}")

    return splits


def to_training_rows(rows: list[dict]) -> list[dict]:
    """Strip generation metadata; keep only text + label for Phi/sklearn."""
    out: list[dict] = []
    for row in rows:
        text = str(row.get("text", "")).strip()
        label = row.get("label")
        if text and label in ("on_topic", "off_topic"):
            out.append({"text": text, "label": label})
    return out
