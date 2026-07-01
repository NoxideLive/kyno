"""Phi JSON extraction of CAPS Mathematics structure from PDF text."""

from __future__ import annotations

import json
import re
from typing import Any

from gateway_inference import generate_text
from pipeline.phases import PHASE_GRADES, Phase

EXTRACT_SYSTEM = """\
You extract structured CAPS Mathematics curriculum data from South African DBE policy PDF text.
Reply with a single JSON object only — no markdown fences, no commentary.
Use English content area names exactly as in the document when possible.
Do not invent topics not supported by the source text.

Schema:
{
  "phase": "<phase>",
  "overview": "<2-4 sentence English summary>",
  "content_area_names": ["..."],
  "grades": {
    "<grade>": {
      "content_area_names": ["..."],
      "topic_phrases": ["short English topic phrases"]
    }
  }
}
"""

MAX_INPUT_CHARS = 18_000


def _select_pdf_excerpt(full_text: str) -> str:
    if len(full_text) <= MAX_INPUT_CHARS:
        return full_text
    markers = [
        "SECTION 3",
        "Section 3",
        "CONTENT",
        "Content areas",
        "Clarification of Grade",
        "Clarification of content",
    ]
    start = 0
    for marker in markers:
        pos = full_text.find(marker)
        if pos >= 0:
            start = max(0, pos - 500)
            break
    excerpt = full_text[start : start + MAX_INPUT_CHARS]
    if len(excerpt) < MAX_INPUT_CHARS // 2:
        excerpt = full_text[:MAX_INPUT_CHARS]
    return excerpt


def _parse_json_response(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in model response: {raw[:200]!r}")
    return json.loads(stripped[start : end + 1])


def _validate_phase_payload(data: dict[str, Any], phase: Phase) -> dict[str, Any]:
    if not data.get("content_area_names"):
        raise ValueError(f"Phase {phase}: empty content_area_names")

    grades: dict[str, Any] = {}
    expected = {str(g) for g in PHASE_GRADES[phase]}
    raw_grades = data.get("grades") or {}
    for grade_key, grade_data in raw_grades.items():
        if str(grade_key) not in expected:
            continue
        if not isinstance(grade_data, dict):
            continue
        grades[str(grade_key)] = {
            "content_area_names": list(grade_data.get("content_area_names") or []),
            "topic_phrases": list(grade_data.get("topic_phrases") or []),
        }

    for grade in expected:
        grades.setdefault(str(grade), {"content_area_names": [], "topic_phrases": []})

    return {
        "schema_version": 2,
        "phase": phase,
        "overview": str(data.get("overview") or "").strip(),
        "content_area_names": list(data["content_area_names"]),
        "grades": grades,
    }


def extract_phase_from_text(
    phase: Phase,
    pdf_text: str,
    *,
    caps_pdf: str,
) -> dict[str, Any]:
    excerpt = _select_pdf_excerpt(pdf_text)
    user = (
        f"Phase: {phase}\n"
        f"Grades in this phase: {', '.join(str(g) for g in PHASE_GRADES[phase])}\n\n"
        f"CAPS Mathematics PDF text excerpt:\n{excerpt}"
    )
    raw = generate_text(
        system=EXTRACT_SYSTEM,
        user=user,
        max_new_tokens=2048,
        temperature=0.1,
    )
    parsed = _parse_json_response(raw)
    parsed["phase"] = phase
    validated = _validate_phase_payload(parsed, phase)
    validated["caps_pdf"] = caps_pdf
    validated["loaded"] = True
    return validated
