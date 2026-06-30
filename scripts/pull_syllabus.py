#!/usr/bin/env python3
"""Download CAPS syllabus documents from the DBE website.

Examples:
  python3 pull_syllabus.py --subject mathematics --grade 6 --year 2026
  python3 pull_syllabus.py --subject mathematics --all-grades --year 2026
  python3 pull_syllabus.py --subject mathematics --all-grades --skip-existing

Per grade downloads:
  1. CAPS policy PDF (phase-based — one doc shared across grades in a phase)
  2. Annual Teaching Plan (ATP) — grade-specific

Phases: Foundation (1–3), Intermediate (4–6), Senior (7–9), FET (10–12).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

DBE_BASE = "https://www.education.gov.za"

Phase = Literal["foundation", "intermediate", "senior", "fet"]

PHASE_CONFIG: dict[Phase, dict[str, str]] = {
    "foundation": {
        "caps_page": f"{DBE_BASE}/Curriculum/CurriculumAssessmentPolicyStatements/CAPSFoundation/tabid/571/Default.aspx",
        "atp_page": f"{DBE_BASE}/Curriculum/NationalCurriculumStatementsGradesR-12/2023ATPsFP.aspx",
    },
    "intermediate": {
        "caps_page": f"{DBE_BASE}/Curriculum/CurriculumAssessmentPolicyStatements/CAPSIntermediatePhase/tabid/572/Default.aspx",
        "atp_page": f"{DBE_BASE}/Curriculum/NationalCurriculumStatementsGradesR-12/2023ATPsIP.aspx",
    },
    "senior": {
        "caps_page": f"{DBE_BASE}/Curriculum/CurriculumAssessmentPolicyStatements/CAPSSeniorPhase/tabid/573/Default.aspx",
        "atp_page": f"{DBE_BASE}/Curriculum/NationalCurriculumStatementsGradesR-12/2023ATPsSP.aspx",
    },
    "fet": {
        "caps_page": f"{DBE_BASE}/Curriculum/CurriculumAssessmentPolicyStatements/CAPSFET/tabid/570/Default.aspx",
        "atp_page": f"{DBE_BASE}/Curriculum/NationalCurriculumStatementsGradesR-12/2023ATPsFET.aspx",
    },
}

USER_AGENT = "KynoCurriculumBot/1.0 (+https://github.com/kyno; educational use)"

# Cache fetched HTML per phase within a run to avoid redundant requests.
_caps_html_cache: dict[Phase, str] = {}
_atp_html_cache: dict[Phase, str] = {}


@dataclass
class DocumentLink:
    title: str
    url: str
    doc_type: str  # caps | atp


def grade_to_phase(grade: int) -> Phase:
    if grade < 1 or grade > 12:
        raise ValueError(f"Grade must be 1–12, got {grade}")
    if grade <= 3:
        return "foundation"
    if grade <= 6:
        return "intermediate"
    if grade <= 9:
        return "senior"
    return "fet"


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def get_caps_html(phase: Phase) -> str:
    if phase not in _caps_html_cache:
        print(f"  Fetching CAPS page ({phase})…")
        _caps_html_cache[phase] = fetch_html(PHASE_CONFIG[phase]["caps_page"])
        time.sleep(1)
    return _caps_html_cache[phase]


def get_atp_html(phase: Phase) -> str:
    if phase not in _atp_html_cache:
        print(f"  Fetching ATP page ({phase})…")
        _atp_html_cache[phase] = fetch_html(PHASE_CONFIG[phase]["atp_page"])
        time.sleep(1)
    return _atp_html_cache[phase]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip().lower()


def is_mathematical_literacy(title: str) -> bool:
    t = normalize(title)
    return "mathematical literacy" in t or "wiskundige geletterdheid" in t


def subject_matches(title: str, subject: str) -> bool:
    title_norm = normalize(title)
    if is_mathematical_literacy(title_norm):
        return False
    subject_norm = normalize(subject)
    aliases = {
        "mathematics": ("mathematics", "wiskunde"),
        "math": ("mathematics", "wiskunde"),
        "maths": ("mathematics", "wiskunde"),
    }
    options = aliases.get(subject_norm, (subject_norm,))
    return any(option in title_norm for option in options)


def year_matches(title: str, year: int | None) -> bool:
    if year is None:
        return True
    return str(year) in title or f"({year})" in title


def parse_page_sections(page_html: str) -> dict[str, list[tuple[str, str]]]:
    """Return {section_title: [(title, download_url), ...]} from a DBE documents page."""
    sections: dict[str, list[tuple[str, str]]] = {}
    chunks = re.split(
        r'class="eds_containerTitle">([^<]+)</span>',
        page_html,
        flags=re.IGNORECASE,
    )
    for index in range(1, len(chunks), 2):
        section_title = normalize(chunks[index])
        section_html = chunks[index + 1] if index + 1 < len(chunks) else ""
        rows = re.findall(
            r'TitleCell"><a[^>]+href="[^"]+"[^>]*>(.*?)</a></td>.*?'
            r'DownloadCell"><a[^>]+href="([^"]+forcedownload=true[^"]*)"',
            section_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        links: list[tuple[str, str]] = []
        for raw_title, download_href in rows:
            title = normalize(raw_title)
            url = html.unescape(download_href)
            if not url.startswith("http"):
                url = urllib.parse.urljoin(DBE_BASE, url)
            links.append((title, url))
        if links:
            sections[section_title] = links
    return sections


def find_caps_link(page_html: str, subject: str, phase: Phase) -> DocumentLink | None:
    sections = parse_page_sections(page_html)

    if phase == "foundation":
        for title, url in sections.get("mathematics", []):
            if title == "english":
                return DocumentLink(title=f"mathematics ({title})", url=url, doc_type="caps")
        for title, url in sections.get("mathematics", []):
            if title == "afrikaans":
                return DocumentLink(title=f"mathematics ({title})", url=url, doc_type="caps")

    search_order = [
        "nonlanguages in english",
        "nonlanguages in afrikaans",
        "content subjects",
        "grade 10 - 12",
        "grade 10-12",
        "fet",
    ]

    for section_name in search_order:
        for title, url in sections.get(section_name, []):
            if subject_matches(title, subject):
                return DocumentLink(title=title, url=url, doc_type="caps")

    for title, url in (
        link for section_links in sections.values() for link in section_links
    ):
        if subject_matches(title, subject):
            return DocumentLink(title=title, url=url, doc_type="caps")
    return None


def find_atp_link(
    page_html: str, subject: str, grade: int, year: int, phase: Phase
) -> DocumentLink | None:
    sections = parse_page_sections(page_html)

    section_candidates = [
        normalize(f"Grade {grade}: Content Subjects"),
        normalize(f"grade {grade}: content subjects"),
    ]
    if phase == "foundation":
        section_candidates.extend(
            [
                normalize("grade 1-3: content subjects"),
                normalize("grade 1 – 3: content subjects"),
            ]
        )

    candidates: list[tuple[str, str]] = []
    for section_title in section_candidates:
        candidates.extend(sections.get(section_title, []))

    if not candidates:
        for section_title, links in sections.items():
            if f"grade {grade}" in section_title and "content" in section_title:
                candidates.extend(links)

    for title, url in candidates:
        if subject_matches(title, subject) and year_matches(title, year):
            return DocumentLink(title=title, url=url, doc_type="atp")

    for title, url in candidates:
        if subject_matches(title, subject):
            return DocumentLink(title=title, url=url, doc_type="atp")

    return None


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    destination.write_bytes(data)


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", text.strip().lower())
    return cleaned.strip("-") or "document"


def manifest_complete(output_dir: Path) -> bool:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    for doc in manifest.get("documents", []):
        path = Path(doc.get("local_path", ""))
        if not path.is_file() or path.stat().st_size < 1000:
            return False
    return len(manifest.get("documents", [])) >= 2


def pull_syllabus(
    subject: str,
    grade: int,
    year: int,
    output_dir: Path,
    *,
    skip_existing: bool = False,
) -> list[DocumentLink]:
    phase = grade_to_phase(grade)

    if skip_existing and manifest_complete(output_dir):
        print(f"Grade {grade}: skipping (manifest + PDFs present)")
        return []

    caps_html = get_caps_html(phase)
    atp_html = get_atp_html(phase)

    caps = find_caps_link(caps_html, subject, phase)
    atp = find_atp_link(atp_html, subject, grade, year, phase)

    if not caps:
        raise RuntimeError(
            f"Could not find CAPS Mathematics for phase '{phase}' on the DBE site."
        )
    if not atp:
        raise RuntimeError(
            f"Could not find Grade {grade} ATP for '{subject}' (year {year}) on the DBE site."
        )

    documents = [caps, atp]
    manifest: list[dict] = []

    for doc in documents:
        filename = f"{safe_filename(doc.doc_type)}-{safe_filename(doc.title)}.pdf"
        path = output_dir / filename
        print(f"  Downloading {doc.doc_type.upper()}: {doc.title}")
        print(f"    → {doc.url}")
        download_file(doc.url, path)
        print(f"    Saved {path} ({path.stat().st_size:,} bytes)")
        manifest.append(
            {
                **asdict(doc),
                "local_path": str(path.resolve()),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        time.sleep(1)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "subject": subject,
                "grade": grade,
                "year": year,
                "phase": phase,
                "documents": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  Wrote manifest → {manifest_path}")
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Download DBE CAPS syllabus documents.")
    parser.add_argument("--subject", default="mathematics", help="Subject (default: mathematics)")
    parser.add_argument("--grade", type=int, default=6, help="Grade 1–12 (default: 6)")
    parser.add_argument("--all-grades", action="store_true", help="Pull grades 1–12")
    parser.add_argument("--year", type=int, default=2026, help="ATP year label (default: 2026)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/syllabus"),
        help="Output root (default: data/syllabus)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip grades that already have a complete manifest + PDFs",
    )
    args = parser.parse_args()

    grades = list(range(1, 13)) if args.all_grades else [args.grade]
    subject_slug = normalize(args.subject).replace(" ", "-")
    errors: list[str] = []

    for grade in grades:
        output_dir = args.output / f"grade-{grade}" / subject_slug
        print(f"\n=== Grade {grade} ({grade_to_phase(grade)}) ===")
        try:
            pull_syllabus(
                args.subject,
                grade,
                args.year,
                output_dir,
                skip_existing=args.skip_existing,
            )
        except (urllib.error.URLError, RuntimeError, ValueError) as exc:
            msg = f"Grade {grade}: {exc}"
            print(f"Error: {msg}", file=sys.stderr)
            errors.append(msg)
        if args.all_grades and grade < grades[-1]:
            time.sleep(1)

    if errors:
        print(f"\n{len(errors)} grade(s) failed.", file=sys.stderr)
        return 1

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
