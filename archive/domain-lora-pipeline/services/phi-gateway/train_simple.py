#!/usr/bin/env python3
"""Train domain classifier without external ML deps.

Saves token log-odds weights to models/token_weights.json.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = ROOT / "training" / "domain"
MODEL_DIR = Path(__file__).resolve().parent / "models"

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_token_weights(train_rows: list[dict], val_rows: list[dict]) -> dict:
    on_counts: Counter[str] = Counter()
    off_counts: Counter[str] = Counter()
    on_total = 0
    off_total = 0

    for row in train_rows:
        tokens = tokenize(row["text"])
        if row["label"] == "on_topic":
            on_counts.update(tokens)
            on_total += len(tokens)
        else:
            off_counts.update(tokens)
            off_total += len(tokens)

    vocab = set(on_counts) | set(off_counts)
    weights: dict[str, float] = {}
    smoothing = 1.0
    on_vocab = len(vocab) + smoothing * 2
    off_vocab = on_vocab

    for token in vocab:
        on_prob = (on_counts[token] + smoothing) / (on_total + smoothing * on_vocab)
        off_prob = (off_counts[token] + smoothing) / (off_total + smoothing * off_vocab)
        weights[token] = math.log(on_prob / off_prob)

    bias_on = math.log(
        (sum(1 for r in train_rows if r["label"] == "on_topic") + 1)
        / (sum(1 for r in train_rows if r["label"] == "off_topic") + 1)
    )

    metrics = evaluate(weights, bias_on, val_rows) if val_rows else {}

    return {
        "weights": weights,
        "bias_on": bias_on,
        "metrics": metrics,
        "backend": "token_log_odds",
    }


def score(text: str, model: dict) -> tuple[str, float]:
    tokens = tokenize(text)
    weights = model["weights"]
    score_on = model["bias_on"]
    for token in tokens:
        score_on += weights.get(token, 0.0)

    # Sigmoid
    confidence_on = 1.0 / (1.0 + math.exp(-score_on))
    if confidence_on >= 0.5:
        return "on_topic", confidence_on
    return "off_topic", 1.0 - confidence_on


def evaluate(model_weights: dict, bias_on: float, rows: list[dict]) -> dict:
    model = {"weights": model_weights, "bias_on": bias_on}
    correct = 0
    for row in rows:
        pred, _ = score(row["text"], model)
        if pred == row["label"]:
            correct += 1
    accuracy = correct / len(rows) if rows else 0.0
    return {"val_accuracy": round(accuracy, 4), "val_size": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-dir", type=Path, default=TRAINING_DIR)
    args = parser.parse_args()

    train_path = args.training_dir / "train.jsonl"
    val_path = args.training_dir / "val.jsonl"
    if not train_path.is_file():
        print(f"Missing {train_path}", file=sys.stderr)
        return 1

    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path) if val_path.is_file() else []

    model = train_token_weights(train_rows, val_rows)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MODEL_DIR / "token_weights.json"
    out_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"Model saved → {out_path}")
    if model.get("metrics"):
        print(f"Validation accuracy: {model['metrics'].get('val_accuracy')}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
