"""Deterministic structure extraction from an HWPX reference document.

A first-pass, verifiable scan of the document body: which numbering markers are
used, what tables exist (shape only), and the ordered body lines. This is the
code half — it reports what is in the bytes. Whether a section is *required* or
*repeats*, and what each field means, is judgment left to the extractor skill.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from zipfile import ZipFile, is_zipfile

# body numbering markers, tested in this order; label is the canonical form
_MARKER_TESTS: list[tuple[str, re.Pattern]] = [
    ("(1)", re.compile(r"^\(\d+\)")),
    ("1.", re.compile(r"^\d+\.")),
    ("1)", re.compile(r"^\d+\)")),
    ("가.", re.compile(r"^[가-힣]\.")),
    ("가)", re.compile(r"^[가-힣]\)")),
    ("①", re.compile(r"^[①-⑳]")),
]
_BULLET_MARKERS = ("□", "○", "―", "※")
_MAX_LINES = 24


def extract_structure(reference: Path | str) -> dict:
    """Return a candidate structure dict. Non-HWPX inputs yield an empty candidate."""
    reference = Path(reference)
    if not is_zipfile(reference):
        return _empty(f"{reference.name}: not an HWPX (zip) package")

    with ZipFile(reference) as pkg:
        section = _read_section(pkg)
    if section is None:
        return _empty(f"{reference.name}: Contents/section0.xml not found")

    tables = _tables(section)
    lines = _body_lines(section)
    markers = _marker_system(lines)

    return {
        "marker_system": markers,
        "tables": tables,
        "line_candidates": lines[:_MAX_LINES],
        "paragraph_count": len(lines),
        "note": "candidate — 필수/반복/필드명은 스킬 큐레이션 필요",
    }


# gov one-page-report bullet markers as they appear as leading tokens in plain text
_TEXT_BULLETS = ("□", "○", "◦", "o", "-", "―", "·", "․", "‧", "※", "▪")


def extract_structure_from_text(text: str) -> dict:
    """Candidate structure from plain text (for legacy .hwp with no XML section).

    Deterministic: numbering/bullet markers at line starts, table placeholders,
    and ordered lines. No required/repeat judgment is made here.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    markers = _marker_system_text(lines)
    table_mentions = sum(1 for ln in lines if "<표>" in ln or "<table>" in ln.lower())
    return {
        "marker_system": markers,
        "tables": [],
        "table_mentions": table_mentions,
        "line_candidates": lines[:_MAX_LINES],
        "paragraph_count": len(lines),
        "note": "candidate(text-derived) — 필수/반복/필드명은 quality gate 미확정",
    }


def _marker_system_text(lines: list[str]) -> list[str]:
    seen: list[str] = []
    for line in lines:
        label = None
        for marker, pattern in _MARKER_TESTS:
            if pattern.match(line):
                label = marker
                break
        if label is None and line[:1] in _TEXT_BULLETS and (len(line) == 1 or line[1] in " \t"):
            label = line[:1]
        if label and label not in seen:
            seen.append(label)
    return seen


def _empty(reason: str) -> dict:
    return {
        "marker_system": [],
        "tables": [],
        "line_candidates": [],
        "paragraph_count": 0,
        "note": reason,
    }


def _read_section(pkg: ZipFile) -> str | None:
    for name in pkg.namelist():
        lowered = name.lower()
        if lowered.endswith("section0.xml") and "contents/" in lowered:
            return pkg.read(name).decode("utf-8", "replace")
    return None


def _cell_texts(scope: str) -> list[str]:
    cells = []
    for tc in re.findall(r"<hp:tc\b.*?</hp:tc>", scope, re.S):
        text = "".join(re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", tc, re.S))
        cells.append(html.unescape(text).strip())
    return cells


def _tables(section: str) -> list[dict]:
    tables = []
    for tbl in re.findall(r"<hp:tbl\b.*?</hp:tbl>", section, re.S):
        rows = re.findall(r"<hp:tr\b.*?</hp:tr>", tbl, re.S)
        if not rows:
            continue
        cols = max((len(_cell_texts(tr)) for tr in rows), default=0)
        tables.append({"rows": len(rows), "cols": cols, "header": _cell_texts(rows[0])})
    return tables


def _body_lines(section: str) -> list[str]:
    body = re.sub(r"<hp:tbl\b.*?</hp:tbl>", "", section, flags=re.S)  # table text handled separately
    lines = []
    for para in re.findall(r"<hp:p\b.*?</hp:p>", body, re.S):
        text = "".join(re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", para, re.S))
        text = html.unescape(text).strip()
        if text:
            lines.append(text)
    return lines


def _marker_system(lines: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in lines:
        line = raw.lstrip()
        label = None
        if line[:1] in _BULLET_MARKERS:
            label = line[:1]
        else:
            for marker, pattern in _MARKER_TESTS:
                if pattern.match(line):
                    label = marker
                    break
        if label and label not in seen:
            seen.append(label)
    return seen
