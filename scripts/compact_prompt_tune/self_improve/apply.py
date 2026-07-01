"""Apply prompt patches and bench curation."""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from compact_prompt_tune.self_improve.log import info, warn
from compact_prompt_tune.self_improve.prompts import OVERLAY_SECTIONS, RULES_SECTIONS

MAX_OVERLAY_ITEMS = 8
MAX_RULES_CHARS = 1800

SUITE_LABELS: dict[str, frozenset[str]] = {
    "jailbreak": frozenset({"safe", "jailbreak_attempted"}),
    "domain": frozenset({"on_topic", "off_topic"}),
    "switch": frozenset({"allowed", "blocked"}),
}


def _looks_afrikaans(text: str) -> bool:
    lowered = text.lower()
    markers = ("wat dek", "graad ", "wiskunde", " vir ", "vir algebra", "vir fractions")
    return any(marker in lowered for marker in markers)


def _sanitize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        texts = [
            str(item.get("text", "")),
            str(item.get("prior", "")),
            str(item.get("latest", "")),
        ]
        if any(_looks_afrikaans(t) for t in texts if t):
            continue
        kept.append(item)
    return kept


def _overlay_key(section: str) -> tuple[str, str]:
    parts = section.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid overlay section: {section}")
    return parts[0], parts[1]


def _label_counts(cases: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(c.get("label", "")) for c in cases)


def _normalize_bench_label(suite: str, raw_label: str) -> str | None:
    label = raw_label.strip().lower().replace("-", "_").replace(" ", "_")
    allowed = SUITE_LABELS.get(suite, frozenset())
    if label in allowed:
        return label
    # e.g. "jailbreak_safe" -> "safe"
    for candidate in allowed:
        if label == candidate or label.endswith(f"_{candidate}") or label.endswith(candidate):
            return candidate
    return None


def _load_min_per_label(bench_dir: Path) -> int:
    config_path = bench_dir / "bench.config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return int(config.get("min_per_label", 100))
    return 100


def load_bench_label_bounds(bench_dir: Path) -> tuple[int, int, int]:
    """Return (min_per_label, max_per_label, target_per_label).

    target is the midpoint (min + max) // 2 — the desired average count per label.
    """
    min_per_label = _load_min_per_label(bench_dir)
    max_per_label = min_per_label * 2
    target_per_label = (min_per_label + max_per_label) // 2
    return min_per_label, max_per_label, target_per_label


def bench_label_deficits(bench_dir: Path) -> list[dict[str, Any]]:
    """Return suite/label rows below min_per_label (hard floor)."""
    min_per_label, max_per_label, target_per_label = load_bench_label_bounds(bench_dir)
    deficits: list[dict[str, Any]] = []
    for suite, labels in SUITE_LABELS.items():
        path = bench_dir / f"{suite}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = _label_counts(payload.get("cases", []))
        for label in sorted(labels):
            current = counts[label]
            if current < min_per_label:
                deficits.append(
                    _label_balance_row(
                        suite=suite,
                        label=label,
                        current=current,
                        min_per_label=min_per_label,
                        max_per_label=max_per_label,
                        target_per_label=target_per_label,
                    )
                )
    return deficits


def bench_label_backfill_needs(
    bench_dir: Path,
    rebalance_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Return rows for labels being rebalanced that are still below target."""
    min_per_label, max_per_label, target_per_label = load_bench_label_bounds(bench_dir)
    needs: list[dict[str, Any]] = []
    for suite, label in sorted(rebalance_keys):
        path = bench_dir / f"{suite}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = _label_counts(payload.get("cases", []))
        current = counts.get(label, 0)
        if current >= target_per_label:
            continue
        needs.append(
            _label_balance_row(
                suite=suite,
                label=label,
                current=current,
                min_per_label=min_per_label,
                max_per_label=max_per_label,
                target_per_label=target_per_label,
            )
        )
    return needs


def _label_balance_row(
    *,
    suite: str,
    label: str,
    current: int,
    min_per_label: int,
    max_per_label: int,
    target_per_label: int,
) -> dict[str, Any]:
    return {
        "suite": suite,
        "label": label,
        "current": current,
        "min": min_per_label,
        "max": max_per_label,
        "target": target_per_label,
        "need": target_per_label - current,
        "room": max(0, max_per_label - current),
    }


def bench_label_surplus(bench_dir: Path) -> list[dict[str, Any]]:
    """Return suite/label rows above max_per_label."""
    min_per_label, max_per_label, target_per_label = load_bench_label_bounds(bench_dir)
    surplus: list[dict[str, Any]] = []
    for suite, labels in SUITE_LABELS.items():
        path = bench_dir / f"{suite}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = _label_counts(payload.get("cases", []))
        for label in sorted(labels):
            current = counts[label]
            if current > max_per_label:
                surplus.append(
                    {
                        "suite": suite,
                        "label": label,
                        "current": current,
                        "min": min_per_label,
                        "max": max_per_label,
                        "excess": current - max_per_label,
                    }
                )
    return surplus


def apply_patch(
    rules: dict[str, Any],
    overlay: dict[str, Any],
    patch: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (new_rules, new_overlay, diff)."""
    new_rules = copy.deepcopy(rules)
    new_overlay = copy.deepcopy(overlay)
    section = str(patch.get("target_section", ""))
    diff: dict[str, Any] = {"target_section": section, "before": {}, "after": {}}

    if section in RULES_SECTIONS:
        classifier, _ = section.split(".", 1)
        before = str(new_rules.get(classifier, {}).get("compact_rules", ""))
        content = str(patch.get("content", ""))
        if len(content) > MAX_RULES_CHARS:
            content = content[:MAX_RULES_CHARS]
        new_rules.setdefault(classifier, {})["compact_rules"] = content
        diff["before"] = {"compact_rules": before}
        diff["after"] = {"compact_rules": content}
        diff["operation"] = "replace"
        return new_rules, new_overlay, diff

    if section not in OVERLAY_SECTIONS:
        raise ValueError(f"Unknown patch section: {section}")

    classifier, key = _overlay_key(section)
    before_list = list(new_overlay.get(classifier, {}).get(key) or [])
    diff["before"] = {key: copy.deepcopy(before_list)}

    add_items = _sanitize_items(list(patch.get("add") or []))[:MAX_OVERLAY_ITEMS]
    remove_texts = {str(t) for t in (patch.get("remove_texts") or [])}

    after_list = list(before_list)
    if remove_texts:
        after_list = [
            item
            for item in after_list
            if str(item.get("text", item.get("latest", ""))) not in remove_texts
        ]

    operation = str(patch.get("operation", "prepend"))
    if operation == "prepend" and add_items:
        after_list = add_items + after_list
    elif operation == "replace":
        after_list = add_items
    else:
        after_list.extend(add_items)

    after_list = after_list[:MAX_OVERLAY_ITEMS * 3]
    new_overlay.setdefault(classifier, {})[key] = after_list
    diff["after"] = {key: copy.deepcopy(after_list)}
    diff["operation"] = operation
    diff["added_count"] = len(add_items)
    diff["removed_count"] = len(before_list) - len(after_list) + len(add_items)
    return new_rules, new_overlay, diff


SUITE_ID_PREFIX: dict[str, str] = {
    "jailbreak": "jb",
    "domain": "dom",
    "switch": "sw",
}


def _remap_case_id(suite: str, iteration: int, seq: int) -> str:
    prefix = SUITE_ID_PREFIX.get(suite, suite[:3])
    return f"{prefix}-si-{iteration}-{seq:03d}"


def apply_bench_curation(
    bench_dir: Path,
    curation: dict[str, Any],
    *,
    add_cap: int = 8,
    remove_cap: int = 5,
    iteration: int | None = None,
) -> dict[str, Any]:
    """Apply bench add/remove to run-scoped fixtures. Returns bench_diff."""
    min_per_label, max_per_label, target_per_label = load_bench_label_bounds(bench_dir)
    suite_files = {
        "jailbreak": bench_dir / "jailbreak.json",
        "domain": bench_dir / "domain.json",
        "switch": bench_dir / "switch.json",
    }
    payloads: dict[str, dict[str, Any]] = {}
    for suite, path in suite_files.items():
        payloads[suite] = json.loads(path.read_text(encoding="utf-8"))

    id_to_suite: dict[str, str] = {}
    id_to_case: dict[str, dict[str, Any]] = {}
    for suite, payload in payloads.items():
        for case in payload.get("cases", []):
            case_id = str(case["id"])
            id_to_suite[case_id] = suite
            id_to_case[case_id] = case

    added: list[str] = []
    removed: list[str] = []
    skipped_adds: list[dict[str, str]] = []
    remapped_ids: list[dict[str, str]] = []
    remap_seq = 0

    for raw_remove in (curation.get("remove") or [])[:remove_cap]:
        case_id = str(raw_remove.get("id", ""))
        suite = id_to_suite.get(case_id)
        if not suite:
            warn("bench curation: skip remove %s — unknown id", case_id)
            continue
        payloads[suite]["cases"] = [
            c for c in payloads[suite]["cases"] if str(c.get("id")) != case_id
        ]
        removed.append(case_id)
        del id_to_suite[case_id]
        del id_to_case[case_id]

    for raw_add in (curation.get("add") or [])[:add_cap]:
        if not isinstance(raw_add, dict) or not raw_add.get("id"):
            skipped_adds.append({"id": "", "reason": "empty or invalid add item"})
            continue
        suite = str(raw_add.get("suite", "")).strip().lower()
        case_id = str(raw_add.get("id", "")).strip()
        if suite not in payloads:
            skipped_adds.append({"id": case_id, "reason": f"unknown suite {suite!r}"})
            continue
        if case_id in id_to_suite:
            if iteration is not None:
                remap_seq += 1
                original_id = case_id
                case_id = _remap_case_id(suite, iteration, remap_seq)
                while case_id in id_to_suite:
                    remap_seq += 1
                    case_id = _remap_case_id(suite, iteration, remap_seq)
                remapped_ids.append({"from": original_id, "to": case_id})
                info("bench curation: remap duplicate id %s → %s", original_id, case_id)
            else:
                skipped_adds.append({"id": case_id, "reason": "duplicate id"})
                continue
        label = _normalize_bench_label(suite, str(raw_add.get("label", "")))
        if label is None:
            skipped_adds.append(
                {
                    "id": case_id,
                    "reason": f"invalid label for {suite}: {raw_add.get('label')!r}",
                }
            )
            warn(
                "bench curation: skip add %s — invalid label %r for suite %s",
                case_id,
                raw_add.get("label"),
                suite,
            )
            continue
        counts = _label_counts(payloads[suite]["cases"])
        if counts[label] >= max_per_label:
            skipped_adds.append(
                {
                    "id": case_id,
                    "reason": (
                        f"{suite}.{label} at max ({counts[label]} >= {max_per_label})"
                    ),
                }
            )
            warn(
                "bench curation: skip add %s — %s.%s at max (%d)",
                case_id,
                suite,
                label,
                counts[label],
            )
            continue
        case: dict[str, Any] = {
            "id": case_id,
            "label": label,
            "text": str(raw_add.get("text", "")),
        }
        history = raw_add.get("history")
        if history:
            case["history"] = history
        meta_json = raw_add.get("meta_json") or raw_add.get("meta")
        if meta_json:
            if isinstance(meta_json, str) and meta_json.strip() not in ("", "{}"):
                try:
                    case["meta"] = json.loads(meta_json)
                except json.JSONDecodeError:
                    case["meta"] = {"note": meta_json}
            elif isinstance(meta_json, dict):
                case["meta"] = meta_json
        payloads[suite]["cases"].append(case)
        id_to_suite[case_id] = suite
        id_to_case[case_id] = case
        added.append(case_id)

    for suite, path in suite_files.items():
        path.write_text(json.dumps(payloads[suite], indent=2) + "\n", encoding="utf-8")

    deficits = bench_label_deficits(bench_dir)
    surplus = bench_label_surplus(bench_dir)

    if skipped_adds:
        info(
            "bench curation: applied +%d -%d; skipped adds=%d",
            len(added),
            len(removed),
            len(skipped_adds),
        )

    return {
        "added_ids": added,
        "removed_ids": removed,
        "skipped_adds": skipped_adds,
        "remapped_ids": remapped_ids,
        "deficits": deficits,
        "surplus": surplus,
        "label_bounds": {
            "min": min_per_label,
            "max": max_per_label,
            "target": target_per_label,
        },
        "summary": str(curation.get("summary", "")),
    }


def merge_bench_diffs(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Accumulate ids/skips from successive curation passes."""
    return {
        "added_ids": list(base.get("added_ids", [])) + list(extra.get("added_ids", [])),
        "removed_ids": list(base.get("removed_ids", [])) + list(extra.get("removed_ids", [])),
        "skipped_adds": list(base.get("skipped_adds", [])) + list(extra.get("skipped_adds", [])),
        "remapped_ids": list(base.get("remapped_ids", [])) + list(extra.get("remapped_ids", [])),
        "deficits": extra.get("deficits", []),
        "surplus": extra.get("surplus", []),
        "label_bounds": extra.get("label_bounds") or base.get("label_bounds"),
        "summary": base.get("summary", ""),
        "backfill_rounds": list(base.get("backfill_rounds", []))
        + list(extra.get("backfill_rounds", [])),
    }


def write_prompt_diff(path: Path, diff: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")


def write_bench_diff(path: Path, diff: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")
