"""Load and validate training/domain/pipeline.config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "training" / "domain" / "pipeline.config.json"


@dataclass(frozen=True)
class PipelineConfig:
    extract_model: str
    generate_model: str
    workers: int
    examples_per_week: int
    on_off_ratio: float
    min_short_per_chunk: int
    off_topic_per_grade: int
    hard_off_ratio: float
    target_off_ratio: float
    ground_threshold: float
    dedupe_enabled: bool
    dedupe_threshold: float
    syllabus_root: Path
    output_dir: Path
    curated_path: Path
    seed: int

    @property
    def config_dir(self) -> Path:
        return DEFAULT_CONFIG_PATH.parent


def _require(data: dict, key: str) -> dict:
    if key not in data or not isinstance(data[key], dict):
        raise ValueError(f"pipeline config missing object: {key}")
    return data[key]


def _float_range(value: float, name: str, low: float, high: float) -> float:
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def load_pipeline_config(path: Path | None = None) -> PipelineConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"Pipeline config not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    models = _require(raw, "models")
    parallelism = _require(raw, "parallelism")
    generation = _require(raw, "generation")
    dedupe = _require(raw, "dedupe")
    paths = _require(raw, "paths")

    config_dir = config_path.parent.resolve()
    root = config_dir.parents[1] if config_dir.name == "domain" else ROOT

    def resolve_path(value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (root / p).resolve()

    return PipelineConfig(
        extract_model=str(models["extract"]),
        generate_model=str(models["generate"]),
        workers=max(1, int(parallelism["workers"])),
        examples_per_week=max(1, int(generation["examples_per_week"])),
        on_off_ratio=_float_range(float(generation["on_off_ratio"]), "on_off_ratio", 0.1, 0.9),
        min_short_per_chunk=max(0, int(generation["min_short_per_chunk"])),
        off_topic_per_grade=max(0, int(generation["off_topic_per_grade"])),
        hard_off_ratio=_float_range(float(generation["hard_off_ratio"]), "hard_off_ratio", 0.0, 1.0),
        target_off_ratio=_float_range(float(generation["target_off_ratio"]), "target_off_ratio", 0.2, 0.8),
        ground_threshold=_float_range(float(generation["ground_threshold"]), "ground_threshold", 0.5, 1.0),
        dedupe_enabled=bool(dedupe.get("enabled", True)),
        dedupe_threshold=_float_range(float(dedupe.get("threshold", 0.88)), "dedupe.threshold", 0.5, 1.0),
        syllabus_root=resolve_path(str(paths["syllabus_root"])),
        output_dir=resolve_path(str(paths["output_dir"])),
        curated_path=resolve_path(str(paths["curated"])),
        seed=int(raw.get("seed", 42)),
    )
