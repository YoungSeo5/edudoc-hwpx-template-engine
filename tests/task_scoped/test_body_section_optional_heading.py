"""``BodySection``의 heading_text/heading_style optional-pair 회귀.

배경: READ-ONLY spot-check(금감원 보도자료, 한국농어촌공사 언론보도 원본
HWPX)로 실제 보도자료는 headline/subtitle/lead/body 앞에 "제목"/"부제"/
"본문 주제문"/"본문" 같은 visible label이 전혀 없음을 확인했다. 기존
``body_section``은 ``heading_text``/``heading_style``을 항상 필수로
요구해 FIXED_LABEL heading 문단을 반드시 렌더링하므로 이 구조를 표현할
수 없었다(AUTHORING_CAPABILITY_BLOCKER로 분류).

이 파일은 그 최소 수정 — heading_text/heading_style을 "둘 다 있으면 기존
동작 그대로, 둘 다 없으면 CONTENT만 렌더, 한쪽만 있으면 fail-closed" —
이 다음을 만족하는지 증명한다:

1. heading이 있는 기존 body_section 출력이 완전히 그대로 유지된다.
2. heading이 없는 body_section은 CONTENT만 렌더하고 visible heading이 없다.
3. heading이 없는 optional content는 불필요한 빈 heading/문단을 만들지 않는다.
4. heading이 없는 collection(hierarchy) body_section은 반복 CONTENT만
   렌더하고(이 경로는 원래도 heading 문단을 만들지 않았다 — 이번 변경이
   그 기존 동작을 깨지 않는지 확인하는 회귀다) visible heading이 없다.
5. heading_text/heading_style 중 하나만 선언하면 명확히 거부된다.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_authoring_resolve import resolve  # noqa: E402
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    HwpxTemplateAuthoringError,
    build_separation_rules,
    generate_source_hwpx,
    load_template_spec,
)

_DESIGN_FIXTURE = (
    ROOT / "tests" / "fixtures" / "template-contracts" / "edudoc.institution_design.json"
)
_NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}


def _design_without_masthead(tmp_path: Path) -> Path:
    # masthead가 켜져 있으면 generate_source_hwpx()가 항상 masthead 표를
    # 먼저 만든다 — 이 파일은 masthead와 무관하게 body_section 자체의
    # heading 유무만 보고 싶으므로 껐다(기존 weekly_report 테스트의
    # ``_masthead_free_design``과 동일한 패턴).
    data = json.loads(_DESIGN_FIXTURE.read_text(encoding="utf-8"))
    data["masthead"] = {"default": "none", "document_override_allowed": True}
    data["assets"] = []
    path = tmp_path / "design_no_masthead.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _write_spec(tmp_path: Path, sections: list[dict], name: str = "spec.json") -> Path:
    data = {
        "template_spec_version": "test-v1",
        "page": {
            "margins_mm": {"left": 20.0, "right": 20.0, "top": 15.0, "bottom": 15.0, "header": 10.0, "footer": 10.0}
        },
        "sections": sections,
    }
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _resolve_and_author(tmp_path: Path, sections: list[dict]) -> Path:
    spec_path = _write_spec(tmp_path, sections)
    resolved = resolve(_design_without_masthead(tmp_path), load_template_spec(spec_path))
    return generate_source_hwpx(resolved, tmp_path / "source.hwpx"), resolved


def _paragraph_texts(source_hwpx: Path) -> list[str]:
    with zipfile.ZipFile(source_hwpx) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    return [
        "".join(t.text or "" for t in p.iter(f"{{{_NS['hp']}}}t"))
        for p in root.findall(f"{{{_NS['hp']}}}p")
        if "".join(t.text or "" for t in p.iter(f"{{{_NS['hp']}}}t")).strip()
    ]


def test_heading_present_body_section_output_is_unchanged(tmp_path: Path) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "body_section",
                "heading_style": "section_title",
                "body_style": "body",
                "heading_text": "핵심 현황",
                "field_id": "summary",
                "sample_value": "요약 내용",
            }
        ],
    )
    assert _paragraph_texts(output) == ["■ 핵심 현황", "요약 내용"]
    rules = build_separation_rules(resolved, output)["rules"]
    # semantic_binding 없이 resolve()했으므로 legacy(무-semantic-contract) 경로가
    # 적용된다 — 그 경로는 모든 heading을 FIXED_LABEL이 아니라 포괄적인
    # FIXED_TEXT로 태깅한다(기존 동작, 이번 변경과 무관).
    assert [rule["role"] for rule in rules] == ["fixed_text", "content"]


def test_heading_absent_body_section_renders_content_only(tmp_path: Path) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "body_section",
                "body_style": "body",
                "field_id": "headline",
                "sample_value": "제목 없는 헤드라인",
            }
        ],
    )
    assert _paragraph_texts(output) == ["제목 없는 헤드라인"]
    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["content"]


def test_heading_absent_optional_content_creates_no_extra_paragraph(tmp_path: Path) -> None:
    output, _ = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "body_section",
                "body_style": "body",
                "field_id": "subheadline",
                "sample_value": "부제 자리",
            }
        ],
    )
    # heading이 없으면 content 문단 하나만 생성되고, 빈 heading 문단이
    # 끼어들지 않는다.
    assert len(_paragraph_texts(output)) == 1


def test_heading_absent_collection_body_section_renders_repeated_content_only(
    tmp_path: Path,
) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "body_section",
                "body_style": "body",
                "field_id": "body_paragraphs",
                "hierarchy_item_field": "text",
                "hierarchy": [
                    {"level": 1, "marker": " ", "native_intent_hwpunit": 0, "line_spacing_percent": 160}
                ],
                "items": [
                    {"level": 1, "text": "본문 문단 1"},
                    {"level": 1, "text": "본문 문단 2"},
                ],
            }
        ],
    )
    # marker(" ")가 각 hierarchy item 텍스트 앞에 그대로 붙는다(기존 동작) —
    # heading 문단이 별도로 없다는 것이 이 테스트가 확인하려는 것이다.
    assert _paragraph_texts(output) == [" 본문 문단 1", " 본문 문단 2"]
    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["content", "content"]


@pytest.mark.parametrize(
    "section",
    [
        {"type": "body_section", "heading_text": "제목만 있음", "body_style": "body", "field_id": "f1", "sample_value": "v"},
        {"type": "body_section", "heading_style": "section_title", "body_style": "body", "field_id": "f1", "sample_value": "v"},
        {
            "type": "body_section",
            "heading_style_override": {"align": "center"},
            "body_style": "body",
            "field_id": "f1",
            "sample_value": "v",
        },
        {
            "type": "body_section",
            "heading_element_id": "headline_label",
            "body_style": "body",
            "field_id": "f1",
            "sample_value": "v",
        },
    ],
)
def test_partial_heading_declaration_is_rejected(tmp_path: Path, section: dict) -> None:
    spec_path = _write_spec(tmp_path, [section])
    with pytest.raises(HwpxTemplateAuthoringError):
        load_template_spec(spec_path)
