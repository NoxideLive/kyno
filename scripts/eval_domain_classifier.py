#!/usr/bin/env python3
"""Evaluate domain classifier on test + regression sets with threshold sweep."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
GATEWAY_DIR = ROOT / "services" / "phi-gateway"
DEFAULT_EVAL_CONFIG = ROOT / "training" / "domain" / "eval.config.json"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from training_io import load_jsonl  # noqa: E402


@dataclass
class RowResult:
    text: str
    label: str
    pred: str
    confidence: float
    blocked: bool


def load_eval_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Eval config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p).resolve()


def word_bucket(text: str) -> str:
    n = len(text.split())
    if n <= 3:
        return "short"
    if n <= 12:
        return "medium"
    return "long"


def classify_http(gateway_url: str, text: str) -> dict:
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{gateway_url.rstrip('/')}/classify/domain",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def classify_local(text: str) -> dict:
    from classifier import DomainClassifier

    return DomainClassifier().classify(text)


def should_block(label: str, confidence: float, threshold: float) -> bool:
    if label == "off_topic":
        return True
    return label == "on_topic" and confidence < threshold


def evaluate_rows(
    rows: list[dict],
    *,
    classify_fn,
    threshold: float,
) -> tuple[list[RowResult], dict[str, dict[str, int]]]:
    results: list[RowResult] = []
    buckets: dict[str, dict[str, int]] = {}

    for row in rows:
        text = str(row["text"])
        label = str(row["label"])
        raw = classify_fn(text)
        pred = str(raw["label"])
        confidence = float(raw["confidence"])
        blocked = should_block(pred, confidence, threshold)
        results.append(
            RowResult(text=text, label=label, pred=pred, confidence=confidence, blocked=blocked)
        )
        bucket = word_bucket(text)
        stats = buckets.setdefault(
            bucket,
            {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        )
        expected_block = label == "off_topic"
        if expected_block and blocked:
            stats["tp"] += 1
        elif expected_block and not blocked:
            stats["fn"] += 1
        elif not expected_block and blocked:
            stats["fp"] += 1
        else:
            stats["tn"] += 1

    return results, buckets


def metrics_from_counts(counts: dict[str, int]) -> dict[str, float]:
    tp, fp, tn, fn = counts["tp"], counts["fp"], counts["tn"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def sweep_threshold(
    rows: list[dict],
    *,
    classify_fn,
    sweep_min: float,
    sweep_max: float,
    sweep_step: float,
) -> list[dict]:
    scores: list[dict] = []
    step = sweep_step
    threshold = sweep_min
    while threshold <= sweep_max + 1e-9:
        _, buckets = evaluate_rows(rows, classify_fn=classify_fn, threshold=threshold)
        combined = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        for counts in buckets.values():
            for key in combined:
                combined[key] += counts[key]
        m = metrics_from_counts(combined)
        regression_on = [r for r in rows if r["label"] == "on_topic"]
        regression_off = [r for r in rows if r["label"] == "off_topic"]
        false_blocks_on = 0
        missed_off = 0
        for row in regression_on:
            raw = classify_fn(str(row["text"]))
            if should_block(str(raw["label"]), float(raw["confidence"]), threshold):
                false_blocks_on += 1
        for row in regression_off:
            raw = classify_fn(str(row["text"]))
            if not should_block(str(raw["label"]), float(raw["confidence"]), threshold):
                missed_off += 1
        scores.append(
            {
                "threshold": round(threshold, 2),
                "metrics": m,
                "false_blocks_on_topic": false_blocks_on,
                "missed_off_topic": missed_off,
                "score": false_blocks_on * 2 + missed_off,
            }
        )
        threshold += step
    return scores


def pick_recommended_threshold(scores: list[dict]) -> float:
    if not scores:
        return 0.55
    best = min(scores, key=lambda s: (s["score"], -s["metrics"]["f1"]))
    return float(best["threshold"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate domain classifier")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_EVAL_CONFIG,
        help="Eval config JSON",
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=None,
        help="Use HTTP gateway instead of local classifier",
    )
    args = parser.parse_args()

    try:
        cfg = load_eval_config(args.config)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    paths = cfg.get("paths", {})
    test_path = resolve_path(ROOT, str(paths.get("test", "training/domain/test.jsonl")))
    regression_path = resolve_path(
        ROOT, str(paths.get("regression", "training/domain/regression.jsonl"))
    )
    report_path = resolve_path(
        ROOT, str(paths.get("output_report", "training/domain/eval_report.json"))
    )

    test_rows = load_jsonl(test_path)
    regression_rows = load_jsonl(regression_path)
    if not test_rows and not regression_rows:
        print("No evaluation rows found.", file=sys.stderr)
        return 1

    if args.gateway_url:

        def classify_fn(text: str) -> dict:
            return classify_http(args.gateway_url, text)

    else:

        def classify_fn(text: str) -> dict:
            return classify_local(text)

    sweep_cfg = cfg.get("threshold_sweep", {})
    sweep_min = float(sweep_cfg.get("min", 0.4))
    sweep_max = float(sweep_cfg.get("max", 0.7))
    sweep_step = float(sweep_cfg.get("step", 0.01))

    eval_rows = regression_rows if regression_rows else test_rows
    sweep_scores = sweep_threshold(
        eval_rows,
        classify_fn=classify_fn,
        sweep_min=sweep_min,
        sweep_max=sweep_max,
        sweep_step=sweep_step,
    )
    recommended = pick_recommended_threshold(sweep_scores)

    test_results, test_buckets = evaluate_rows(
        test_rows, classify_fn=classify_fn, threshold=recommended
    )
    regression_results, regression_buckets = evaluate_rows(
        regression_rows, classify_fn=classify_fn, threshold=recommended
    )

    def summarize(buckets: dict[str, dict[str, int]]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for name, counts in buckets.items():
            out[name] = {**counts, **metrics_from_counts(counts)}
        return out

    report = {
        "recommended_threshold": recommended,
        "test": {
            "rows": len(test_rows),
            "buckets": summarize(test_buckets),
        },
        "regression": {
            "rows": len(regression_rows),
            "buckets": summarize(regression_buckets),
            "failures": [
                {
                    "text": r.text,
                    "label": r.label,
                    "pred": r.pred,
                    "confidence": r.confidence,
                    "blocked": r.blocked,
                }
                for r in regression_results
                if (r.label == "on_topic" and r.blocked)
                or (r.label == "off_topic" and not r.blocked)
            ],
        },
        "threshold_sweep": sweep_scores,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Recommended threshold: {recommended}")
    print(f"Regression failures: {len(report['regression']['failures'])}")
    print(f"Report → {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
