"""Deterministic style extraction from an HWPX reference document.

Reads the document's own XML and reports what is actually there, with evidence:
- fonts + body char size from ``Contents/header.xml``
- page margins + the dominant body char reference from ``Contents/section0.xml``

Nothing is defaulted. Fields the reference does not provide stay ``None`` so a
renderer can decide to fall back explicitly. This is the code half of the
template pipeline (facts that live in the bytes); judgment about which section is
required or how to write it belongs to the extractor skill, not here.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile, is_zipfile

from ..models import ExtractedStyleProfile

_HWPUNIT_PER_MM = 7200 / 25.4  # 1 inch = 7200 HWPUNIT = 25.4 mm


def extract_style(reference: Path | str) -> ExtractedStyleProfile:
    """Extract style from an HWPX reference. Non-HWPX inputs yield a low-confidence
    profile with all values ``None`` (PDF/DOCX extraction is out of scope here)."""
    reference = Path(reference)
    if not is_zipfile(reference):
        return ExtractedStyleProfile(
            source="unknown", confidence="low",
            evidence=[f"{reference.name}: not an HWPX (zip) package"],
        )

    with ZipFile(reference) as pkg:
        names = pkg.namelist()
        header = _read(pkg, names, "header.xml")
        section = _read(pkg, names, "section0.xml")

    if header is None or section is None:
        return ExtractedStyleProfile(
            source="unknown", confidence="low",
            evidence=[f"{reference.name}: header.xml/section0.xml not found in package"],
        )

    margins = _margins_mm(section)
    body_id = _dominant_char_id(section)
    size_pt, hangul_font_id = _char_size_and_font(header, body_id)
    font_family = _font_face(header, hangul_font_id)
    line_spacing = _dominant_line_spacing(header)

    found = [v for v in (font_family, size_pt, margins) if v is not None]
    confidence = "high" if len(found) == 3 else "medium" if found else "low"

    return ExtractedStyleProfile(
        source="extracted_from_hwpx",
        font_family=font_family,
        body_font_size_pt=size_pt,
        page_margins_mm=margins,
        line_spacing=line_spacing,
        confidence=confidence,
        evidence=["Contents/header.xml", "Contents/section0.xml"],
    )


def _read(pkg: ZipFile, names: list[str], suffix: str) -> str | None:
    suffix = suffix.lower()
    for name in names:
        lowered = name.lower()
        if lowered.endswith(suffix) and "contents/" in lowered:
            return pkg.read(name).decode("utf-8", "replace")
    return None


def _margins_mm(section: str) -> dict | None:
    m = re.search(r"<hp:margin\b([^>]*)>", section)
    if not m:
        return None
    attrs = m.group(1)

    def mm(name: str) -> float | None:
        a = re.search(rf'\b{name}="(\d+)"', attrs)
        return round(int(a.group(1)) / _HWPUNIT_PER_MM, 1) if a else None

    margins = {k: mm(k) for k in ("top", "bottom", "left", "right")}
    return margins if any(v is not None for v in margins.values()) else None


def _dominant_char_id(section: str) -> int | None:
    refs = re.findall(r'charPrIDRef="(\d+)"', section)
    if not refs:
        return None
    return int(Counter(refs).most_common(1)[0][0])


def _char_size_and_font(header: str, body_id: int | None) -> tuple[float | None, int | None]:
    if body_id is None:
        return None, None
    m = re.search(rf'<hh:charPr id="{body_id}"([^>]*)>(.*?)</hh:charPr>', header, re.S)
    if not m:
        return None, None
    head_attrs, body = m.group(1), m.group(2)
    h = re.search(r'height="(\d+)"', head_attrs)
    size = int(h.group(1)) / 100 if h else None
    fr = re.search(r'<hh:fontRef\b[^>]*\bhangul="(\d+)"', body)
    fid = int(fr.group(1)) if fr else None
    return size, fid


def _font_face(header: str, hangul_id: int | None) -> str | None:
    if hangul_id is None:
        return None
    block = re.search(r'<hh:fontface lang="HANGUL"[^>]*>(.*?)</hh:fontface>', header, re.S)
    if not block:
        return None
    f = re.search(rf'<hh:font id="{hangul_id}"[^>]*\bface="([^"]+)"', block.group(1))
    return f.group(1) if f else None


def _dominant_line_spacing(header: str) -> str | None:
    vals = re.findall(r'<hh:lineSpacing\b[^>]*type="PERCENT"[^>]*value="(\d+)"', header)
    if not vals:
        return None
    return f"{Counter(vals).most_common(1)[0][0]}%"
