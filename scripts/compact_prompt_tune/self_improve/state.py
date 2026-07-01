"""Run-scoped state, registry, and immutable iteration paths."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compact_prompt_tune.self_improve import ROOT, SELF_IMPROVE_ROOT

RUNS_INDEX_PATH = SELF_IMPROVE_ROOT / "runs.jsonl"
ACTIVE_RUN_PATH = SELF_IMPROVE_ROOT / "active_run.json"
PROD_BENCH_DIR = ROOT / "data" / "domain" / "bench"

RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
BENCH_SUITE_FILES = ("jailbreak.json", "domain.json", "switch.json")


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(
            f"Invalid run id {run_id!r}; use slug [a-z0-9][a-z0-9_-]{{0,63}}"
        )


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def run_dir(run_id: str) -> Path:
    validate_run_id(run_id)
    return SELF_IMPROVE_ROOT / "runs" / run_id


def iter_dir(run_id: str, iteration: int) -> Path:
    return run_dir(run_id) / f"iter-{iteration}"


def resolve_run_id(explicit: str | None) -> str:
    if explicit:
        validate_run_id(explicit)
        return explicit
    if not ACTIVE_RUN_PATH.is_file():
        raise RuntimeError(
            "No active run. Run `init` first or pass --run-id."
        )
    payload = json.loads(ACTIVE_RUN_PATH.read_text(encoding="utf-8"))
    run_id = str(payload.get("run_id", "")).strip()
    if not run_id:
        raise RuntimeError("active_run.json missing run_id")
    validate_run_id(run_id)
    return run_id


def set_active_run(run_id: str) -> None:
    validate_run_id(run_id)
    SELF_IMPROVE_ROOT.mkdir(parents=True, exist_ok=True)
    ACTIVE_RUN_PATH.write_text(
        json.dumps({"run_id": run_id}, indent=2) + "\n",
        encoding="utf-8",
    )


def load_meta(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "meta.json"
    if not path.is_file():
        raise FileNotFoundError(f"Run not found: {run_id} ({path})")
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(run_id: str, meta: dict[str, Any]) -> None:
    path = run_dir(run_id) / "meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def register_run(
    run_id: str,
    *,
    seed_run_id: str | None = None,
    status: str = "active",
) -> None:
    SELF_IMPROVE_ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "seed_run_id": seed_run_id,
    }
    existing = load_jsonl(RUNS_INDEX_PATH)
    filtered = [r for r in existing if r.get("run_id") != run_id]
    filtered.append(record)
    RUNS_INDEX_PATH.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in filtered) + "\n",
        encoding="utf-8",
    )


def update_run_registry(run_id: str, **fields: Any) -> None:
    rows = load_jsonl(RUNS_INDEX_PATH)
    updated = False
    for row in rows:
        if row.get("run_id") == run_id:
            row.update(fields)
            updated = True
            break
    if not updated:
        register_run(run_id)
        rows = load_jsonl(RUNS_INDEX_PATH)
        for row in rows:
            if row.get("run_id") == run_id:
                row.update(fields)
    RUNS_INDEX_PATH.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
        encoding="utf-8",
    )


def list_runs() -> list[dict[str, Any]]:
    return load_jsonl(RUNS_INDEX_PATH)


def empty_rules() -> dict[str, Any]:
    return {
        "version": 1,
        "notes": ["Cold-start baseline for self-improve bench."],
        "domain": {
            "compact_rules": (
                "Classify the latest user message only: on_topic or off_topic."
            ),
        },
        "jailbreak": {
            "compact_rules": (
                "Classify the latest user message: safe or jailbreak_attempted."
            ),
        },
    }


def empty_overlay() -> dict[str, Any]:
    return {
        "version": 1,
        "notes": ["Cold-start baseline for self-improve bench."],
        "domain": {
            "on_topic": [],
            "off_topic": [],
            "conversation_examples": [],
        },
        "jailbreak": {
            "safe": [],
            "jailbreak_attempted": [],
            "conversation_examples": [],
        },
    }


def write_prompts(iter_path: Path, rules: dict[str, Any], overlay: dict[str, Any]) -> None:
    prompts_dir = iter_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "rules.json").write_text(
        json.dumps(rules, indent=2) + "\n", encoding="utf-8"
    )
    (prompts_dir / "overlay.json").write_text(
        json.dumps(overlay, indent=2) + "\n", encoding="utf-8"
    )
    manifest = prompt_manifest(rules, overlay)
    (prompts_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def prompt_manifest(rules: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    domain_rules = str(rules.get("domain", {}).get("compact_rules", ""))
    jailbreak_rules = str(rules.get("jailbreak", {}).get("compact_rules", ""))
    domain_overlay = overlay.get("domain", {})
    jailbreak_overlay = overlay.get("jailbreak", {})
    return {
        "domain_compact_rules_chars": len(domain_rules),
        "jailbreak_compact_rules_chars": len(jailbreak_rules),
        "total_prompt_chars": len(domain_rules) + len(jailbreak_rules),
        "overlay_counts": {
            "domain.on_topic": len(domain_overlay.get("on_topic") or []),
            "domain.off_topic": len(domain_overlay.get("off_topic") or []),
            "domain.conversation_examples": len(
                domain_overlay.get("conversation_examples") or []
            ),
            "jailbreak.safe": len(jailbreak_overlay.get("safe") or []),
            "jailbreak.jailbreak_attempted": len(
                jailbreak_overlay.get("jailbreak_attempted") or []
            ),
            "jailbreak.conversation_examples": len(
                jailbreak_overlay.get("conversation_examples") or []
            ),
        },
    }


def copy_prod_bench(dest_bench_dir: Path) -> int:
    dest_bench_dir.mkdir(parents=True, exist_ok=True)
    config_src = PROD_BENCH_DIR / "bench.config.json"
    if config_src.is_file():
        shutil.copy2(config_src, dest_bench_dir / "bench.config.json")
    total = 0
    for name in BENCH_SUITE_FILES:
        src = PROD_BENCH_DIR / name
        if not src.is_file():
            raise FileNotFoundError(f"Missing prod bench fixture: {src}")
        shutil.copy2(src, dest_bench_dir / name)
        payload = json.loads(src.read_text(encoding="utf-8"))
        total += len(payload.get("cases", []))
    return total


def count_bench_cases(bench_dir: Path) -> int:
    total = 0
    for name in BENCH_SUITE_FILES:
        path = bench_dir / name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            total += len(payload.get("cases", []))
    return total


def load_prompts(iter_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    rules = json.loads((iter_path / "prompts" / "rules.json").read_text(encoding="utf-8"))
    overlay = json.loads((iter_path / "prompts" / "overlay.json").read_text(encoding="utf-8"))
    return rules, overlay


def copy_iter_snapshot(source_iter: Path, dest_iter: Path) -> None:
    if dest_iter.exists():
        raise FileExistsError(f"Destination exists: {dest_iter}")
    dest_iter.mkdir(parents=True)
    for sub in ("prompts", "bench"):
        src = source_iter / sub
        if src.is_dir():
            shutil.copytree(src, dest_iter / sub)
    for name in ("manifest.json", "report.json"):
        src = source_iter / name
        if src.is_file():
            shutil.copy2(src, dest_iter / name)


def write_iter_manifest(
    iter_path: Path,
    *,
    iteration: int,
    accepted: bool,
    verdict: str,
    parent_iter: int,
    bench_cases: int,
    prompt_chars: int,
) -> None:
    manifest = {
        "iter": iteration,
        "accepted": accepted,
        "verdict": verdict,
        "parent_iter": parent_iter,
        "prompt_chars": prompt_chars,
        "bench_cases": bench_cases,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (iter_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
