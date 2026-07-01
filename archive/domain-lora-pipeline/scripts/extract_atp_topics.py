#!/usr/bin/env python3
"""Extract term/week/topic structure from ATP PDFs into topics.json.

Requires: pdftotext (poppler-utils)

Example:
  python3 extract_atp_topics.py --grade 6
  python3 extract_atp_topics.py --all-grades
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_SYLLABUS_ROOT = Path("data/syllabus")

TERM_PATTERN = re.compile(r"TERM\s+(\d+)", re.IGNORECASE)
WEEK_PATTERN = re.compile(r"WEEK\s+(\d+)", re.IGNORECASE)

EMPTY_CAPS_SUMMARY = {
    "overview_excerpt": "",
    "aims_excerpt": "",
    "assessment_excerpt": "",
    "content_area_names": [],
}


def empty_week_fields() -> dict:
    return {
        "content_area": "",
        "short_phrases": [],
        "caps_excerpt": "",
        "assessment_notes": [],
    }


def pdf_to_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {pdf_path}: {result.stderr.strip()}")
    return result.stdout


def find_atp_pdf(grade_dir: Path) -> Path | None:
    for pattern in ("atp-*.pdf", "atp-mathematics*.pdf"):
        matches = sorted(grade_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def extract_topics_from_text(text: str, grade: int) -> dict:
    lines = [clean_line(line) for line in text.splitlines() if clean_line(line)]
    terms: list[dict] = []
    current_term: dict | None = None
    current_week: dict | None = None

    def flush_week() -> None:
        nonlocal current_week
        if current_term is not None and current_week is not None:
            current_term["weeks"].append(current_week)
        current_week = None

    def flush_term() -> None:
        nonlocal current_term
        flush_week()
        if current_term is not None and current_term["weeks"]:
            terms.append(current_term)
        current_term = None

    topic_keywords = (
        "number",
        "fraction",
        "decimal",
        "geometry",
        "measurement",
        "algebra",
        "data",
        "pattern",
        "whole",
        "shape",
        "space",
        "calculus",
        "trigonometry",
        "probability",
        "statistics",
        "equation",
        "graph",
        "ratio",
        "percent",
        "mental",
        "revision",
        "assessment",
    )

    for line in lines:
        term_match = TERM_PATTERN.search(line)
        if term_match and "TEACHING" in line.upper():
            flush_term()
            current_term = {"term": int(term_match.group(1)), "weeks": []}
            continue

        week_match = WEEK_PATTERN.search(line)
        if week_match and current_term is not None:
            flush_week()
            week_num = int(week_match.group(1))
            if 1 <= week_num <= 15:
                current_week = {"week": week_num, "topics": [], "skills": [], **empty_week_fields()}
            continue

        if current_week is None:
            continue

        lower = line.lower()
        if len(line) < 12 or len(line) > 280:
            continue
        if any(skip in lower for skip in ("page ", "copyright", "department of basic")):
            continue
        if any(kw in lower for kw in topic_keywords) or line.isupper():
            bucket = "skills" if "skill" in lower or "concept" in lower else "topics"
            if line not in current_week[bucket]:
                current_week[bucket].append(line[:200])
            if "assessment" in lower or "afl" in lower:
                if line not in current_week["assessment_notes"]:
                    current_week["assessment_notes"].append(line[:200])

    flush_term()

    if not terms:
        terms = _fallback_terms(lines, grade)

    return {
        "grade": grade,
        "subject": "mathematics",
        "curriculum": "CAPS",
        "terms": terms,
        "term_count": len(terms),
        "week_count": sum(len(t["weeks"]) for t in terms),
    }


def _fallback_terms(lines: list[str], grade: int) -> list[dict]:
    """When week grid parsing fails, bucket lines that look like content areas."""
    snippets = [
        line[:200]
        for line in lines
        if 20 < len(line) < 200
        and not line.startswith("2023")
        and "MATHEMATICS" not in line.upper()[:20]
    ][:40]
    return [
        {
            "term": 1,
            "weeks": [
                {
                    "week": 1,
                    "topics": snippets[:20],
                    "skills": snippets[20:40],
                    **empty_week_fields(),
                }
            ],
        }
    ]


def enrich_topics_document(topics: dict, grade: int, syllabus_root: Path) -> dict:
    """Add CAPS metadata when caps_chunker and PDFs are available."""
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    from caps_chunker import (  # noqa: WPS433
        caps_excerpt_for_week,
        find_caps_pdf,
        grade_caps_summary,
        load_phase_caps_sections,
    )
    from syllabus_phases import grade_to_phase  # noqa: WPS433

    grade_dir = syllabus_root / f"grade-{grade}" / "mathematics"
    caps_pdf = find_caps_pdf(grade_dir)
    atp_pdf = find_atp_pdf(grade_dir)

    topics["phase"] = grade_to_phase(grade)
    topics["sources"] = {
        "atp_pdf": str(atp_pdf.resolve()) if atp_pdf else topics.get("source_pdf", ""),
        "caps_pdf": str(caps_pdf.resolve()) if caps_pdf else "",
    }
    topics.pop("source_pdf", None)

    phase_sections = load_phase_caps_sections(syllabus_root, grade_to_phase(grade))
    caps_summary = (
        grade_caps_summary(phase_sections, grade)
        if phase_sections.get("loaded")
        else dict(EMPTY_CAPS_SUMMARY)
    )
    topics["caps_summary"] = caps_summary

    for term_block in topics.get("terms", []):
        for week_block in term_block.get("weeks", []):
            for key, default in empty_week_fields().items():
                week_block.setdefault(key, default if not isinstance(default, list) else [])
            if phase_sections.get("loaded"):
                excerpt, matched = caps_excerpt_for_week(
                    phase_sections,
                    grade,
                    week_block.get("topics", []),
                    week_block.get("skills", []),
                )
                week_block["caps_excerpt"] = excerpt
                if matched and not week_block.get("content_area"):
                    week_block["content_area"] = matched

    return topics


def extract_grade(grade: int, syllabus_root: Path) -> Path:
    grade_dir = syllabus_root / f"grade-{grade}" / "mathematics"
    atp_pdf = find_atp_pdf(grade_dir)
    if not atp_pdf:
        raise FileNotFoundError(f"No ATP PDF in {grade_dir}")

    text = pdf_to_text(atp_pdf)
    topics = extract_topics_from_text(text, grade)
    topics = enrich_topics_document(topics, grade, syllabus_root)

    out_path = grade_dir / "topics.json"
    out_path.write_text(json.dumps(topics, indent=2), encoding="utf-8")
    print(
        f"Grade {grade}: {topics['term_count']} terms, "
        f"{topics['week_count']} weeks → {out_path}"
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract ATP topics to topics.json")
    parser.add_argument("--grade", type=int, help="Grade 1–12")
    parser.add_argument("--all-grades", action="store_true")
    parser.add_argument(
        "--syllabus-root",
        type=Path,
        default=DEFAULT_SYLLABUS_ROOT,
        help="Syllabus data root",
    )
    args = parser.parse_args()

    grades = list(range(1, 13)) if args.all_grades else [args.grade]
    if not args.all_grades and args.grade is None:
        parser.error("Specify --grade or --all-grades")

    errors: list[str] = []
    for grade in grades:
        try:
            extract_grade(grade, args.syllabus_root)
        except (FileNotFoundError, RuntimeError) as exc:
            errors.append(f"Grade {grade}: {exc}")
            print(f"Error: {errors[-1]}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
