from __future__ import annotations

import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
import zipfile

from core.adapters.hwpx_authoring_resolve import resolve
from core.adapters.hwpx_template_authoring import (
    ResolvedBodySection,
    generate_source_hwpx,
    load_template_spec,
)
from scripts.templates import author_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "business-status-one-page"
DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"


def test_one_page_section_heading_resolves_declared_line_spacing() -> None:
    resolved = resolve(DESIGN, load_template_spec(FIXTURES / "template_spec.json"))

    heading = next(
        section
        for section in resolved.sections
        if isinstance(section, ResolvedBodySection) and section.field_id == "next_actions_summary"
    )

    assert heading.heading_style.line_spacing_percent == 160.0


def test_hierarchy_projection_uses_children_after_the_section_heading() -> None:
    candidate_id = f"hierarchy_projection_{uuid.uuid4().hex}"
    candidate = ROOT / "sandbox" / "template-candidates" / candidate_id
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(FIXTURES / "template_request.json"),
            "--semantic-contract", str(FIXTURES / "semantic_contract.json"),
            "--template-spec", str(FIXTURES / "template_spec.json"),
            "--institution-design", str(DESIGN),
            "--institution", "edudoc",
            "--document-type", "사업 추진현황 1페이지 보고서",
            "--candidate-id", candidate_id,
            "--template-id", f"tpl_{uuid.uuid4().hex}",
        ]
    )
    assert exit_code in (0, 1)

    expected = [
        ("□ 향후 조치", "0", "0", "160"),
        (" ◦ 운영기관 협약 마무리", "1417", "-2990", "150"),
        ("      * 권역별 실행계획 확인", "1417", "-4410", "130"),
    ]
    for output_name in ("source.hwpx", "roundtrip.sample.hwpx"):
        with zipfile.ZipFile(candidate / output_name) as package:
            section_root = ET.fromstring(package.read("Contents/section0.xml"))
            header_root = ET.fromstring(package.read("Contents/header.xml"))
        paragraphs = {
            "".join(node.text or "" for node in paragraph.iter(f"{{{HP}}}t")): paragraph
            for paragraph in section_root.iter(f"{{{HP}}}p")
        }
        actual = []
        for text, expected_left, expected_intent, expected_line_spacing in expected:
            paragraph = paragraphs[text]
            para_pr = next(
                value
                for value in header_root.iter(f"{{{HH}}}paraPr")
                if value.get("id") == paragraph.get("paraPrIDRef")
            )
            margin = next(para_pr.iter(f"{{{HH}}}margin"))
            line_spacing = next(para_pr.iter(f"{{{HH}}}lineSpacing"))
            actual.append(
                (
                    text,
                    next(margin.iter(f"{{{HC}}}left")).get("value"),
                    next(margin.iter(f"{{{HC}}}intent")).get("value"),
                    line_spacing.get("value"),
                )
            )
        assert actual == expected


def test_native_hierarchy_intent_keeps_resolved_left_indent(tmp_path: Path) -> None:
    resolved = resolve(DESIGN, load_template_spec(FIXTURES / "template_spec.json"))
    hierarchy = next(
        section
        for section in resolved.sections
        if isinstance(section, ResolvedBodySection) and section.field_id == "next_actions"
    )
    expected_left = str(round(hierarchy.body_style.indent_left_mm * 7200 / 25.4))
    source = generate_source_hwpx(resolved, tmp_path / "source.hwpx")

    with zipfile.ZipFile(source) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
        header_root = ET.fromstring(package.read("Contents/header.xml"))
    paragraphs = {
        "".join(node.text or "" for node in paragraph.iter(f"{{{HP}}}t")): paragraph
        for paragraph in section_root.iter(f"{{{HP}}}p")
    }
    for text, expected_intent in {
        " ◦ 운영기관 협약 마무리": "-2990",
        "      * 권역별 실행계획 확인": "-4410",
    }.items():
        paragraph = paragraphs[text]
        para_pr = next(
            value
            for value in header_root.iter(f"{{{HH}}}paraPr")
            if value.get("id") == paragraph.get("paraPrIDRef")
        )
        margin = next(para_pr.iter(f"{{{HH}}}margin"))
        assert next(margin.iter(f"{{{HC}}}left")).get("value") == expected_left
        assert next(margin.iter(f"{{{HC}}}intent")).get("value") == expected_intent
