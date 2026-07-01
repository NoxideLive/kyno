"""PDF to text via pdftotext with optional cache."""

from __future__ import annotations

import subprocess
from pathlib import Path


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
