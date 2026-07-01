"""Load and merge compact-prompt overlay examples for tuning."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pipeline.repo_paths import domain_dir

_COMPACT_TEST_MODE: bool | None = None


def _env_compact_test() -> bool:
    return os.environ.get("PHI_GATEWAY_COMPACT_TEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def is_compact_test_mode() -> bool:
    if _COMPACT_TEST_MODE is not None:
        return _COMPACT_TEST_MODE
    return _env_compact_test()


def set_compact_test_mode(enabled: bool | None) -> None:
    """Toggle in-memory test overlay/rules (None = follow env)."""
    global _COMPACT_TEST_MODE
    _COMPACT_TEST_MODE = enabled
    invalidate_overlay_cache()


def overlay_path() -> Path:
    if is_compact_test_mode():
        return domain_dir() / "compact_prompt_overlay_test.json"
    return domain_dir() / "compact_prompt_overlay.json"


def compact_rules_path() -> Path:
    return domain_dir() / "compact_prompt_rules_test.json"


def _empty_overlay() -> dict:
    return {
        "version": 1,
        "domain": {"on_topic": [], "off_topic": [], "conversation_examples": []},
        "jailbreak": {"safe": [], "jailbreak_attempted": [], "conversation_examples": []},
        "notes": [],
    }


@lru_cache(maxsize=1)
def load_overlay() -> dict:
    path = overlay_path()
    if not path.is_file():
        return _empty_overlay()
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("domain", "jailbreak"):
        section = data.setdefault(key, {})
        section.setdefault("on_topic", section.get("on_topic", []))
        section.setdefault("off_topic", section.get("off_topic", []))
        section.setdefault("safe", section.get("safe", []))
        section.setdefault("jailbreak_attempted", section.get("jailbreak_attempted", []))
        section.setdefault("conversation_examples", [])
    data.setdefault("notes", [])
    return data


def invalidate_overlay_cache() -> None:
    load_overlay.cache_clear()


def merge_compact_examples(base: dict, overlay: dict, *, section: str) -> dict:
    """Prepend overlay examples so tuning wins over base truncation."""
    overlay_section = overlay.get(section, {})
    base_section = dict(base)
    merged = dict(base_section)

    for list_key in ("on_topic", "off_topic", "safe", "jailbreak_attempted"):
        if list_key not in base_section and list_key not in overlay_section:
            continue
        base_items = list(base_section.get(list_key, []))
        overlay_items = list(overlay_section.get(list_key, []))
        merged[list_key] = overlay_items + base_items

    base_conv = list(base_section.get("conversation_examples", []))
    overlay_conv = list(overlay_section.get("conversation_examples", []))
    merged["conversation_examples"] = overlay_conv + base_conv
    return merged
