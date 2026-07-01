"""Orchestrate CAPS PDF → sections JSON → topic list."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from domain_prompt import invalidate_prompt_cache
from jailbreak_prompt import invalidate_jailbreak_prompt_cache
from pipeline.caps_extract import extract_phase_from_text
from pipeline.caps_paths import phase_caps_pdf, phase_sections_path
from pipeline.pdf_text import pdf_to_text
from pipeline.phases import ALL_PHASES, Phase
from pipeline.repo_paths import domain_dir
from pipeline.topic_aggregate import write_topic_list


def rebuild(phases: list[Phase] | None = None) -> dict[str, Any]:
    selected = list(phases or ALL_PHASES)
    started = datetime.now(timezone.utc).isoformat()
    phase_reports: list[dict[str, Any]] = []
    warnings: list[str] = []

    for phase in selected:
        pdf_path = phase_caps_pdf(phase)
        if pdf_path is None:
            msg = f"No CAPS PDF found for phase {phase}"
            warnings.append(msg)
            phase_reports.append({"phase": phase, "ok": False, "error": msg})
            continue

        try:
            text = pdf_to_text(pdf_path)
            payload = extract_phase_from_text(
                phase,
                text,
                caps_pdf=str(pdf_path.resolve()),
            )
            out_path = phase_sections_path(phase)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            phase_reports.append(
                {
                    "phase": phase,
                    "ok": True,
                    "caps_pdf": str(pdf_path),
                    "sections_path": str(out_path),
                    "content_area_count": len(payload.get("content_area_names", [])),
                    "grades": list(payload.get("grades", {}).keys()),
                }
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Phase {phase}: {exc}"
            warnings.append(msg)
            phase_reports.append({"phase": phase, "ok": False, "error": str(exc)})

    topic_result = write_topic_list()
    invalidate_prompt_cache()
    invalidate_jailbreak_prompt_cache()

    report = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "phases": phase_reports,
        "warnings": warnings,
        "topic_list": topic_result,
        "ok": all(p.get("ok") for p in phase_reports) and not warnings,
    }

    report_path = domain_dir() / "pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def load_last_report() -> dict[str, Any] | None:
    path = domain_dir() / "pipeline_report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
