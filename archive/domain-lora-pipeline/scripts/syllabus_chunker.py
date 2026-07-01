"""Split ATP PDF text into term/week chunks for coupled LLM extraction."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TERM_PATTERN = re.compile(r"TERM\s+(\d+)", re.IGNORECASE)
WEEK_PATTERN = re.compile(r"WEEK\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class SyllabusChunk:
    grade: int
    term: int
    week: int
    text: str
    char_start: int
    char_end: int


def pdf_to_text(pdf_path: Path, cache_txt: bool = True) -> str:
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


def find_atp_pdf(grade_dir: Path) -> Path | None:
    for pattern in ("atp-*.pdf", "atp-mathematics*.pdf"):
        matches = sorted(grade_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def chunk_atp_text(text: str, grade: int) -> list[SyllabusChunk]:
    """Split ATP plain text into week-level chunks using TERM/WEEK markers."""
    lines = text.splitlines()
    chunks: list[SyllabusChunk] = []

    current_term = 1
    current_week = 0
    week_lines: list[str] = []
    char_cursor = 0
    week_start = 0

    def flush_week() -> None:
        nonlocal week_lines, week_start, current_week
        if current_week < 1 or not week_lines:
            week_lines = []
            return
        body = "\n".join(week_lines).strip()
        if len(body) < 20:
            week_lines = []
            return
        chunks.append(
            SyllabusChunk(
                grade=grade,
                term=current_term,
                week=current_week,
                text=body,
                char_start=week_start,
                char_end=week_start + len(body),
            )
        )
        week_lines = []

    for raw_line in lines:
        line = _clean_line(raw_line)
        line_start = char_cursor
        char_cursor += len(raw_line) + 1

        if not line:
            continue

        term_match = TERM_PATTERN.search(line)
        if term_match and "TEACHING" in line.upper():
            flush_week()
            current_term = int(term_match.group(1))
            current_week = 0
            week_start = line_start
            week_lines = [line]
            continue

        week_match = WEEK_PATTERN.search(line)
        if week_match and current_term > 0:
            flush_week()
            week_num = int(week_match.group(1))
            if 1 <= week_num <= 15:
                current_week = week_num
                week_start = line_start
                week_lines = [line]
            continue

        if current_week > 0:
            week_lines.append(line)

    flush_week()

    if chunks:
        return chunks

    return _page_window_chunks(text, grade)


def _page_window_chunks(text: str, grade: int, window: int = 3000, overlap: int = 400) -> list[SyllabusChunk]:
    """Fallback when TERM/WEEK markers are missing."""
    chunks: list[SyllabusChunk] = []
    start = 0
    week = 1
    while start < len(text):
        end = min(len(text), start + window)
        body = text[start:end].strip()
        if len(body) >= 100:
            chunks.append(
                SyllabusChunk(
                    grade=grade,
                    term=1,
                    week=week,
                    text=body,
                    char_start=start,
                    char_end=end,
                )
            )
            week += 1
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def load_grade_chunks(grade: int, syllabus_root: Path) -> tuple[Path, list[SyllabusChunk]]:
    grade_dir = syllabus_root / f"grade-{grade}" / "mathematics"
    atp_pdf = find_atp_pdf(grade_dir)
    if not atp_pdf:
        raise FileNotFoundError(f"No ATP PDF in {grade_dir}")
    text = pdf_to_text(atp_pdf)
    return atp_pdf, chunk_atp_text(text, grade)
