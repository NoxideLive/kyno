"""Extract CAPS policy PDF sections for training-data enrichment."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from syllabus_grounding import similarity
from syllabus_phases import PHASE_GRADES, REPRESENTATIVE_GRADE, Phase, grade_to_phase

OVERVIEW_CAP = 2000
AIMS_CAP = 2000
ASSESSMENT_CAP = 1500
AREA_EXCERPT_CAP = 2500
FALLBACK_EXCERPT_CAP = 3500

CONTENT_AREA_ALIASES: dict[str, tuple[str, ...]] = {
    "numbers, operations and relationships": (
        "number",
        "whole number",
        "fraction",
        "decimal",
        "ratio",
        "percent",
    ),
    "patterns, functions and algebra": (
        "pattern",
        "algebra",
        "function",
        "sequence",
    ),
    "space and shape": (
        "geometry",
        "shape",
        "space",
        "angle",
        "triangle",
    ),
    "measurement": ("measurement", "length", "area", "volume", "mass", "time"),
    "data handling": ("data", "graph", "statistics", "probability"),
}

GRADE_SLICE_START: dict[Phase, re.Pattern[str]] = {
    "foundation": re.compile(
        r"3\.5\.(\d+)\s+Clarification of Grade (\d+) content",
        re.IGNORECASE,
    ),
    "intermediate": re.compile(
        r"3\.3\.(\d+)\.?\s+Clarification of content for Grade (\d+)",
        re.IGNORECASE,
    ),
    "senior": re.compile(
        r"3\.3\.(\d+)\s+Verheldering van inhoud vir Graad (\d+)",
        re.IGNORECASE,
    ),
    "fet": re.compile(r"Grade (\d{2})\s+Term:\s*1", re.IGNORECASE),
}

SECTION_4_PATTERN = re.compile(r"SECTION\s+4[:\s]", re.IGNORECASE)
OVERVIEW_PATTERN = re.compile(r"1\.2\s+Overview", re.IGNORECASE)
SECTION_2_PATTERN = re.compile(
    r"SECTION\s+2[:\s].*?(?:DEFINITION|INTRODUCTION)",
    re.IGNORECASE,
)
ASSESSMENT_PATTERN = re.compile(r"SECTION\s+4[:\s].*?ASSESSMENT", re.IGNORECASE)


def find_caps_pdf(grade_dir: Path) -> Path | None:
    manifest_path = grade_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for doc in manifest.get("documents", []):
                if doc.get("doc_type") == "caps":
                    path = Path(doc.get("local_path", ""))
                    if path.is_file():
                        return path
        except json.JSONDecodeError:
            pass
    matches = sorted(grade_dir.glob("caps-*.pdf"))
    return matches[0] if matches else None


def pdf_to_text(pdf_path: Path, *, cache_txt: bool = True) -> str:
    if cache_txt:
        cache_path = pdf_path.with_suffix(".txt")
        if cache_path.is_file() and cache_path.stat().st_mtime >= pdf_path.stat().st_mtime:
            return cache_path.read_text(encoding="utf-8", errors="replace")

    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {pdf_path}: {result.stderr.strip()}")

    text = result.stdout
    if cache_txt:
        pdf_path.with_suffix(".txt").write_text(text, encoding="utf-8")
    return text


def _cap_text(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    truncated = cleaned[:max_len]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated + "…"


def _slice_between(text: str, start: int, end: int) -> str:
    return text[start:end].strip()


def _find_overview(text: str) -> str:
    match = OVERVIEW_PATTERN.search(text)
    if not match:
        return ""
    start = match.end()
    end_match = SECTION_2_PATTERN.search(text, start)
    end = end_match.start() if end_match else start + 8000
    return _cap_text(_slice_between(text, start, end), OVERVIEW_CAP)


def _find_aims(text: str) -> str:
    match = SECTION_2_PATTERN.search(text)
    if not match:
        return ""
    start = match.start()
    section_3 = re.search(r"SECTION\s+3[:\s]", text[start:], re.IGNORECASE)
    end = start + section_3.start() if section_3 else start + 12000
    return _cap_text(_slice_between(text, start, end), AIMS_CAP)


def _find_assessment(text: str) -> str:
    match = ASSESSMENT_PATTERN.search(text)
    if not match:
        match = SECTION_4_PATTERN.search(text)
    if not match:
        return ""
    start = match.start()
    end = min(len(text), start + 12000)
    return _cap_text(_slice_between(text, start, end), ASSESSMENT_CAP)


def _is_toc_line(text: str, pos: int) -> bool:
    line_end = text.find("\n", pos)
    if line_end < 0:
        line_end = min(len(text), pos + 300)
    line = text[pos:line_end]
    return line.count(".") > 15 or (
        len(line) < 150 and re.search(r"\.{4,}\s*\d+\s*$", line) is not None
    )


def _grade_slice_bounds(text: str, phase: Phase, grade: int) -> tuple[int, int] | None:
    pattern = GRADE_SLICE_START[phase]
    starts: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        if phase == "fet":
            matched_grade = int(match.group(1))
        else:
            matched_grade = int(match.group(2))
        if _is_toc_line(text, match.start()):
            continue
        starts.append((matched_grade, match.start()))

    if not starts:
        return None

    starts.sort(key=lambda item: item[1])
    grade_starts = [pos for matched_grade, pos in starts if matched_grade == grade]
    if not grade_starts:
        return None

    best: tuple[int, int] | None = None
    for start_pos in grade_starts:
        end_pos = len(text)
        for matched_grade, pos in starts:
            if pos > start_pos and matched_grade != grade:
                end_pos = pos
                break
        section_4 = SECTION_4_PATTERN.search(text, start_pos + 1)
        if section_4 and section_4.start() < end_pos:
            end_pos = section_4.start()
        if best is None or (end_pos - start_pos) > (best[1] - best[0]):
            best = (start_pos, end_pos)

    return best


def _normalize_area_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip().lower()
    name = name.replace(" and ", " and ")
    return name


def _split_content_areas(grade_slice: str) -> dict[str, str]:
    areas: dict[str, str] = {}
    lower_slice = grade_slice.lower()

    for canon in CONTENT_AREA_ALIASES:
        positions: list[int] = []
        for alias in (canon, *CONTENT_AREA_ALIASES[canon]):
            pos = lower_slice.find(alias)
            if pos >= 0:
                positions.append(pos)
        if not positions:
            continue
        start = min(positions)
        end = len(grade_slice)
        for other_canon in CONTENT_AREA_ALIASES:
            if other_canon == canon:
                continue
            for alias in (other_canon, *CONTENT_AREA_ALIASES[other_canon]):
                pos = lower_slice.find(alias, start + 40)
                if pos >= 0:
                    end = min(end, pos)
        body = grade_slice[start:end].strip()
        if len(body) >= 80:
            areas[canon.title()] = _cap_text(body, AREA_EXCERPT_CAP)

    if not areas and len(grade_slice) > 200:
        areas["General"] = _cap_text(grade_slice, AREA_EXCERPT_CAP)

    return areas


def extract_caps_sections(text: str, phase: Phase, grade: int) -> dict[str, Any]:
    bounds = _grade_slice_bounds(text, phase, grade)
    grade_slice = ""
    content_areas: dict[str, str] = {}
    if bounds:
        grade_slice = _slice_between(text, bounds[0], bounds[1])
        content_areas = _split_content_areas(grade_slice)

    return {
        "overview": _find_overview(text),
        "aims": _find_aims(text),
        "assessment": _find_assessment(text),
        "grade_content": _cap_text(grade_slice, 8000) if grade_slice else "",
        "content_areas": content_areas,
        "content_area_names": list(content_areas.keys()),
    }


def _phase_caps_cache_path(syllabus_root: Path, phase: Phase) -> Path:
    return syllabus_root / "phases" / phase / "mathematics" / "caps-sections.json"


def _representative_grade_dir(syllabus_root: Path, phase: Phase) -> Path:
    grade = REPRESENTATIVE_GRADE[phase]
    return syllabus_root / f"grade-{grade}" / "mathematics"


def load_phase_caps_sections(syllabus_root: Path, phase: Phase) -> dict[str, Any]:
    cache_path = _phase_caps_cache_path(syllabus_root, phase)
    grade_dir = _representative_grade_dir(syllabus_root, phase)
    caps_pdf = find_caps_pdf(grade_dir)
    if not caps_pdf:
        return {"phase": phase, "loaded": False, "grades": {}}

    if cache_path.is_file() and cache_path.stat().st_mtime >= caps_pdf.stat().st_mtime:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    text = pdf_to_text(caps_pdf)
    grades_data: dict[str, Any] = {}
    for grade in PHASE_GRADES[phase]:
        grades_data[str(grade)] = extract_caps_sections(text, phase, grade)

    payload = {
        "phase": phase,
        "loaded": True,
        "caps_pdf": str(caps_pdf.resolve()),
        "overview": _find_overview(text),
        "aims": _find_aims(text),
        "assessment": _find_assessment(text),
        "grades": grades_data,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def grade_caps_summary(phase_sections: dict[str, Any], grade: int) -> dict[str, Any]:
    grade_data = phase_sections.get("grades", {}).get(str(grade), {})
    return {
        "overview_excerpt": phase_sections.get("overview") or grade_data.get("overview", ""),
        "aims_excerpt": phase_sections.get("aims") or grade_data.get("aims", ""),
        "assessment_excerpt": phase_sections.get("assessment") or grade_data.get("assessment", ""),
        "content_area_names": grade_data.get("content_area_names", []),
    }


def _score_area_match(
    area_name: str,
    area_body: str,
    topics: list[str],
    skills: list[str],
) -> float:
    canon = _normalize_area_name(area_name)
    aliases = CONTENT_AREA_ALIASES.get(canon, (canon,))
    phrases = [t for t in topics + skills if t]
    if not phrases:
        return 0.0

    best = 0.0
    for phrase in phrases:
        lower = phrase.lower()
        for alias in aliases:
            if alias in lower:
                best = max(best, 0.95)
        best = max(best, similarity(phrase, area_name))
        best = max(best, similarity(phrase, area_body[:500]))
    return best


def caps_excerpt_for_week(
    phase_sections: dict[str, Any],
    grade: int,
    topics: list[str],
    skills: list[str],
) -> tuple[str, str | None]:
    grade_data = phase_sections.get("grades", {}).get(str(grade), {})
    content_areas: dict[str, str] = grade_data.get("content_areas", {})

    best_name: str | None = None
    best_score = 0.0
    best_body = ""

    for name, body in content_areas.items():
        score = _score_area_match(name, body, topics, skills)
        if score > best_score:
            best_score = score
            best_name = name
            best_body = body

    if best_name and best_score >= 0.35:
        return _cap_text(best_body, AREA_EXCERPT_CAP), best_name

    overview = phase_sections.get("overview", "")
    aims = phase_sections.get("aims", "")
    fallback = f"{overview}\n\n{aims}".strip()
    if grade_data.get("grade_content"):
        fallback = f"{fallback}\n\n{grade_data['grade_content'][:1500]}".strip()
    return _cap_text(fallback, FALLBACK_EXCERPT_CAP), None


def combined_grounding_text(atp_chunk: str, caps_excerpt: str) -> str:
    parts = [atp_chunk.strip()]
    if caps_excerpt.strip():
        parts.append(caps_excerpt.strip())
    return "\n\n".join(parts)


def match_content_area_name(
    name: str,
    content_area_names: list[str],
    *,
    threshold: float = 0.55,
) -> str | None:
    if not name or not content_area_names:
        return None
    best: str | None = None
    best_score = 0.0
    for candidate in content_area_names:
        score = similarity(name, candidate)
        if score > best_score:
            best_score = score
            best = candidate
    return best if best_score >= threshold else None
