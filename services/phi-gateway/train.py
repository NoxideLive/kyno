#!/usr/bin/env python3
"""Train sklearn domain classifier (CPU). For Phi QLoRA use train_phi.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = ROOT / "training" / "domain"
MODEL_DIR = Path(__file__).resolve().parent / "models"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_sklearn(train_path: Path, val_path: Path) -> Pipeline:
    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path) if val_path.is_file() else []

    texts = [r["text"] for r in train_rows]
    labels = [r["label"] for r in train_rows]

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=8000, min_df=1)),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )
    pipeline.fit(texts, labels)

    if val_rows:
        val_texts = [r["text"] for r in val_rows]
        val_labels = [r["label"] for r in val_rows]
        preds = pipeline.predict(val_texts)
        print(classification_report(val_labels, preds))

    return pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phi",
        action="store_true",
        help="Use train_phi.py for Phi-4-mini QLoRA (Microsoft sample_finetune.py)",
    )
    parser.add_argument("--training-dir", type=Path, default=TRAINING_DIR)
    args = parser.parse_args()

    if args.phi:
        print("Run: python train_phi.py  (or: accelerate launch train_phi.py)", file=sys.stderr)
        return 1

    train_path = args.training_dir / "train.jsonl"
    val_path = args.training_dir / "val.jsonl"

    if not train_path.is_file():
        print(f"Missing {train_path}. Run scripts/generate_domain_training_data.py first.", file=sys.stderr)
        return 1

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    pipeline = train_sklearn(train_path, val_path)
    out_path = MODEL_DIR / "domain_classifier.joblib"
    joblib.dump(pipeline, out_path)
    print(f"Sklearn model saved → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
