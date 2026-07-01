"""Plan vs diagnosis alignment checks."""

from __future__ import annotations

from typing import Any


def is_plan_section_allowed(diagnosis: dict[str, Any], plan: dict[str, Any]) -> bool:
    """True when plan.target_section matches recommended_focus or a valid override."""
    recommended = str(diagnosis.get("recommended_focus", "")).strip()
    target = str(plan.get("target_section", "")).strip()
    if not recommended or target == recommended:
        return True

    top_pattern = str(diagnosis.get("top_pattern", "")).lower()

    if target == "jailbreak.conversation_examples":
        return "switch" in top_pattern and "jailbreak" in top_pattern

    if target == "domain.conversation_examples":
        return "switch" in top_pattern

    return False


def plan_alignment_message(diagnosis: dict[str, Any], plan: dict[str, Any]) -> str:
    recommended = str(diagnosis.get("recommended_focus", "")).strip()
    target = str(plan.get("target_section", "")).strip()
    return (
        f"recommended_focus was {recommended!r}; your plan chose {target!r}. "
        f"target_section MUST equal recommended_focus unless top_pattern is switch-specific "
        f"and you target jailbreak.conversation_examples (jailbreak block) or "
        f"domain.conversation_examples (off_topic block). Explain override in strategy if used."
    )
