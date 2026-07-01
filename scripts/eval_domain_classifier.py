#!/usr/bin/env python3
"""Evaluate domain classifier on test + regression sets with threshold sweep."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_CONFIG = ROOT / "data" / "domain" / "eval" / "eval.config.json"


@dataclass
class RowResult:
    text: str
    label: str
    pred: str
    confidence: float
    blocked: bool


@dataclass
class CachedClassification:
    text: str
    label: str
    pred: str
    confidence: float


def log(message: str) -> None:
    print(message, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_eval_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Eval config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root / p).resolve()


def default_gateway_url() -> str | None:
    url = os.environ.get("PHI_GATEWAY_URL", "").strip()
    return url or None


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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def preclassify_rows(
    rows: list[dict],
    *,
    classify_fn,
    label: str,
) -> list[CachedClassification]:
    cached: list[CachedClassification] = []
    total = len(rows)
    log(f"Classifying {total} {label} rows...")
    for index, row in enumerate(rows, start=1):
        text = str(row["text"])
        raw = classify_fn(text)
        pred = str(raw["label"])
        confidence = float(raw["confidence"])
        cached.append(
            CachedClassification(
                text=text,
                label=str(row["label"]),
                pred=pred,
                confidence=confidence,
            )
        )
        log(f"  [{index}/{total}] {pred} ({confidence:.3f}) {text[:60]}")
    return cached


def should_block(label: str, confidence: float, threshold: float) -> bool:
    if label == "off_topic":
        return True
    return label == "on_topic" and confidence < threshold


def evaluate_cached(
    cached: list[CachedClassification],
    *,
    threshold: float,
) -> tuple[list[RowResult], dict[str, dict[str, int]]]:
    results: list[RowResult] = []
    buckets: dict[str, dict[str, int]] = {}

    for item in cached:
        blocked = should_block(item.pred, item.confidence, threshold)
        results.append(
            RowResult(
                text=item.text,
                label=item.label,
                pred=item.pred,
                confidence=item.confidence,
                blocked=blocked,
            )
        )
        bucket = word_bucket(item.text)
        stats = buckets.setdefault(
            bucket,
            {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        )
        expected_block = item.label == "off_topic"
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
    cached: list[CachedClassification],
    *,
    sweep_min: float,
    sweep_max: float,
    sweep_step: float,
) -> list[dict]:
    scores: list[dict] = []
    threshold = sweep_min
    while threshold <= sweep_max + 1e-9:
        _, buckets = evaluate_cached(cached, threshold=threshold)
        combined = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        for counts in buckets.values():
            for key in combined:
                combined[key] += counts[key]
        m = metrics_from_counts(combined)
        false_blocks_on = sum(
            1
            for item in cached
            if item.label == "on_topic"
            and should_block(item.pred, item.confidence, threshold)
        )
        missed_off = sum(
            1
            for item in cached
            if item.label == "off_topic"
            and not should_block(item.pred, item.confidence, threshold)
        )
        scores.append(
            {
                "threshold": round(threshold, 2),
                "metrics": m,
                "false_blocks_on_topic": false_blocks_on,
                "missed_off_topic": missed_off,
                "score": false_blocks_on * 2 + missed_off,
            }
        )
        threshold += sweep_step
    return scores


def pick_recommended_threshold(scores: list[dict]) -> float:
    if not scores:
        return 0.4
    best = min(scores, key=lambda s: (s["score"], -s["metrics"]["f1"]))
    return float(best["threshold"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate domain classifier via gateway")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_EVAL_CONFIG,
        help="Eval config JSON",
    )
    parser.add_argument(
        "--gateway-url",
        type=str,
        default=default_gateway_url(),
        help="Phi gateway URL (default PHI_GATEWAY_URL env)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output report path from config",
    )
    args = parser.parse_args()

    if not args.gateway_url:
        print("Set PHI_GATEWAY_URL or pass --gateway-url", file=sys.stderr, flush=True)
        return 1

    try:
        cfg = load_eval_config(args.config)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1

    paths = cfg.get("paths", {})
    test_path = resolve_path(ROOT, str(paths.get("test", "data/domain/eval/test.jsonl")))
    regression_path = resolve_path(
        ROOT, str(paths.get("regression", "data/domain/eval/regression.jsonl"))
    )
    report_path = resolve_path(
        ROOT, str(paths.get("output_report", "data/domain/eval/eval_report.json"))
    )
    if args.output is not None:
        report_path = args.output if args.output.is_absolute() else (ROOT / args.output).resolve()

    test_rows = load_jsonl(test_path)
    regression_rows = load_jsonl(regression_path)
    if not test_rows and not regression_rows:
        print("No evaluation rows found.", file=sys.stderr, flush=True)
        return 1

    gateway = args.gateway_url.rstrip("/")
    log(f"Gateway: {gateway}")

    def classify_fn(text: str) -> dict:
        return classify_http(gateway, text)

    unique_rows: list[dict] = []
    seen: set[str] = set()
    for row in [*regression_rows, *test_rows]:
        text = str(row["text"])
        if text not in seen:
            seen.add(text)
            unique_rows.append(row)

    cached_all = preclassify_rows(unique_rows, classify_fn=classify_fn, label="unique")
    cache_by_text = {item.text: item for item in cached_all}

    def cached_subset(rows: list[dict]) -> list[CachedClassification]:
        return [cache_by_text[str(row["text"])] for row in rows]

    sweep_cfg = cfg.get("threshold_sweep", {})
    sweep_min = float(sweep_cfg.get("min", 0.4))
    sweep_max = float(sweep_cfg.get("max", 0.7))
    sweep_step = float(sweep_cfg.get("step", 0.01))

    eval_cached = cached_subset(regression_rows if regression_rows else test_rows)
    log(f"Threshold sweep on {len(eval_cached)} rows...")
    sweep_scores = sweep_threshold(
        eval_cached,
        sweep_min=sweep_min,
        sweep_max=sweep_max,
        sweep_step=sweep_step,
    )
    recommended = pick_recommended_threshold(sweep_scores)
    log(f"Recommended threshold: {recommended}")

    test_results, test_buckets = evaluate_cached(
        cached_subset(test_rows), threshold=recommended
    )
    regression_results, regression_buckets = evaluate_cached(
        cached_subset(regression_rows), threshold=recommended
    )

    def summarize(buckets: dict[str, dict[str, int]]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for name, counts in buckets.items():
            out[name] = {**counts, **metrics_from_counts(counts)}
        return out

    report = {
        "recommended_threshold": recommended,
        "gateway_url": gateway,
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

    log(f"Regression failures: {len(report['regression']['failures'])}")
    log(f"Report → {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
