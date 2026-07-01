"""Load and validate bench JSON fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH_DIR = ROOT / "data" / "domain" / "bench"


@dataclass(frozen=True)
class BenchCase:
    id: str
    suite: str
    label: str
    text: str
    history: list[dict[str, str]] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BenchSuite:
    name: str
    labels: tuple[str, ...]
    endpoint: str
    cases: tuple[BenchCase, ...]


SUITE_ENDPOINTS = {
    "jailbreak": "/classify/jailbreak",
    "domain": "/classify/domain",
    "switch": "/classify/message",
}


def load_bench_config(bench_dir: Path | None = None) -> dict:
    directory = bench_dir or DEFAULT_BENCH_DIR
    path = directory / "bench.config.json"
    if not path.is_file():
        raise FileNotFoundError(f"Bench config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_counts(suite_name: str, labels: list[str], cases: list[BenchCase], min_per_label: int) -> dict[str, int]:
    counts = {label: 0 for label in labels}
    for case in cases:
        if case.label not in counts:
            raise ValueError(f"{suite_name}: unknown label {case.label!r}")
        counts[case.label] += 1
    for label, count in counts.items():
        if count < min_per_label:
            raise ValueError(
                f"{suite_name}: {label} has {count}, need >= {min_per_label}"
            )
    return counts


def load_suite_file(path: Path, *, min_per_label: int) -> BenchSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    suite_name = str(payload["suite"])
    labels = [str(label) for label in payload["labels"]]
    endpoint = SUITE_ENDPOINTS.get(suite_name)
    if endpoint is None:
        raise ValueError(f"Unknown suite: {suite_name}")

    cases: list[BenchCase] = []
    for raw in payload.get("cases", []):
        cases.append(
            BenchCase(
                id=str(raw["id"]),
                suite=suite_name,
                label=str(raw["label"]),
                text=str(raw["text"]),
                history=list(raw.get("history") or []),
                meta=dict(raw.get("meta") or {}),
            )
        )

    counts = _validate_counts(suite_name, labels, cases, min_per_label)
    print(
        f"Loaded {suite_name}: {len(cases)} cases "
        + ", ".join(f"{label}={counts[label]}" for label in labels),
        flush=True,
    )
    return BenchSuite(
        name=suite_name,
        labels=tuple(labels),
        endpoint=endpoint,
        cases=tuple(cases),
    )


def load_suites(
    bench_dir: Path | None = None,
    *,
    suite_names: list[str] | None = None,
) -> list[BenchSuite]:
    directory = bench_dir or DEFAULT_BENCH_DIR
    config = load_bench_config(directory)
    min_per_label = int(config.get("min_per_label", 100))
    suite_files: dict[str, str] = config.get("suites", {})
    selected = suite_names or list(suite_files.keys())

    suites: list[BenchSuite] = []
    for name in selected:
        rel = suite_files.get(name)
        if not rel:
            raise ValueError(f"Suite not configured: {name}")
        path = directory / rel
        suites.append(load_suite_file(path, min_per_label=min_per_label))
    return suites
