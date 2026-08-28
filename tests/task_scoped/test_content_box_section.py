"""``content_box``: 1열 bordered table, 각 row는 CONTENT 하나·label 없음.

배경: READ-ONLY contract gap audit(금감원 보도자료, 한국농어촌공사 언론보도
원본 HWPX 재검증)으로 headline/subtitle이 두 원본 모두 자유 문단이 아니라
**bordered table 안**에 있음을 확인했다. 기존 primitive 중 어느 것도 이
구조를 표현하지 못했다:

- ``info_table``은 label-value 쌍 전용이라 라벨 없는 텍스트를 못 담는다.
- ``simple_table``은 하나의 collection field가 반복되는 행 전용이라
  headline·subtitle처럼 서로 다른 두 개의 단일 CONTENT 필드를 한 표에
  못 담는다.
- ``body_section``(heading-less 포함)은 표가 아니라 자유 문단만 만든다.

이 파일은 새로 추가한 ``content_box`` section type이 다음을 만족하는지
증명한다:

1. headline 하나만 있는 content_box → CONTENT 1개, label 없음, 표 존재.
2. headline + subtitle → 두 CONTENT 모두 순서대로, label 없음.
3. 각 row가 자신의 style role로 렌더된다(행마다 다른 폰트 크기/정렬).
4. 기존 info_table 동작 불변.
5. 기존 body_section(및 heading-less body_section) 동작 불변.
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
_NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
}


def _design_without_masthead(tmp_path: Path) -> Path:
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


def _resolve_and_author(tmp_path: Path, sections: list[dict]):
    spec_path = _write_spec(tmp_path, sections)
    resolved = resolve(_design_without_masthead(tmp_path), load_template_spec(spec_path))
    return generate_source_hwpx(resolved, tmp_path / "source.hwpx"), resolved


def _section_root(output: Path) -> ET.Element:
    with zipfile.ZipFile(output) as package:
        return ET.fromstring(package.read("Contents/section0.xml"))


def _header_root(output: Path) -> ET.Element:
    with zipfile.ZipFile(output) as package:
        return ET.fromstring(package.read("Contents/header.xml"))


def _tables(root: ET.Element) -> list[ET.Element]:
    return root.findall(f".//{{{_NS['hp']}}}tbl")


def _cell_text(cell: ET.Element) -> str:
    return "".join(t.text or "" for t in cell.iter(f"{{{_NS['hp']}}}t"))


def _cell_para_pr_ref(cell: ET.Element) -> str | None:
    paragraph = cell.find(f"{{{_NS['hp']}}}subList/{{{_NS['hp']}}}p")
    return paragraph.get("paraPrIDRef") if paragraph is not None else None


def _para_align(header_root: ET.Element, para_pr_id_ref: str) -> str:
    for para_pr in header_root.iter(f"{{{_NS['hh']}}}paraPr"):
        if para_pr.get("id") == para_pr_id_ref:
            align = para_pr.find(f"{{{_NS['hh']}}}align")
            return align.get("horizontal") if align is not None else ""
    raise AssertionError(f"paraPr id={para_pr_id_ref!r} not found")


def test_single_item_content_box_renders_content_only_no_label(tmp_path: Path) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "content_box",
                "style": "info_table",
                "items": [
                    {"body_style": "title", "field_id": "headline", "sample_value": "헤드라인"},
                ],
            }
        ],
    )
    root = _section_root(output)
    tables = _tables(root)
    assert len(tables) == 1
    rows = tables[0].findall(f"{{{_NS['hp']}}}tr")
    assert len(rows) == 1
    cells = rows[0].findall(f"{{{_NS['hp']}}}tc")
    assert len(cells) == 1
    assert _cell_text(cells[0]) == "헤드라인"
    # "제목" 같은 별도 label 문단/셀이 없다 — 표 전체 텍스트가 헤드라인 하나뿐.
    assert "".join(root.itertext()).strip() == "헤드라인"

    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["content"]


def test_headline_and_subtitle_content_box_renders_both_in_order_no_label(
    tmp_path: Path,
) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "content_box",
                "style": "info_table",
                "items": [
                    {"body_style": "title", "field_id": "headline", "sample_value": "헤드라인"},
                    {
                        "body_style": "body",
                        "body_style_override": {"align": "center", "size_pt": 14},
                        "field_id": "subheadline",
                        "sample_value": "부제 문장",
                    },
                ],
            }
        ],
    )
    root = _section_root(output)
    tables = _tables(root)
    assert len(tables) == 1
    rows = tables[0].findall(f"{{{_NS['hp']}}}tr")
    assert len(rows) == 2
    texts = [_cell_text(row.find(f"{{{_NS['hp']}}}tc")) for row in rows]
    # 표 전체 텍스트가 두 CONTENT 값 그대로다 — 그 앞에 "제목:"/"부제:" 같은
    # 별도 label 문단/셀이 끼어들지 않는다(둘 다 없으면 표는 정확히 이
    # 두 값의 순서 있는 나열이어야 한다).
    assert texts == ["헤드라인", "부제 문장"]
    assert "".join(root.itertext()).strip() == "헤드라인부제 문장"

    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["content", "content"]


def test_content_box_item_uses_its_own_style_role(tmp_path: Path) -> None:
    output, _ = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "content_box",
                "style": "info_table",
                "items": [
                    {"body_style": "title", "field_id": "headline", "sample_value": "헤드라인"},
                    {
                        "body_style": "body",
                        "body_style_override": {"align": "center", "size_pt": 14},
                        "field_id": "subheadline",
                        "sample_value": "부제 문장",
                    },
                ],
            }
        ],
    )
    section_root = _section_root(output)
    header_root = _header_root(output)
    rows = _tables(section_root)[0].findall(f"{{{_NS['hp']}}}tr")
    headline_cell = rows[0].find(f"{{{_NS['hp']}}}tc")
    subtitle_cell = rows[1].find(f"{{{_NS['hp']}}}tc")

    headline_para_pr = _cell_para_pr_ref(headline_cell)
    subtitle_para_pr = _cell_para_pr_ref(subtitle_cell)
    assert headline_para_pr is not None and subtitle_para_pr is not None
    # institution "title" role의 기본 align은 center고, subtitle의
    # body_style_override도 center를 요청했다 — 둘 다 center이지만 서로
    # 다른 style role/override에서 독립적으로 온 값임을 charPr(글자 크기)로
    # 구분해 확인한다.
    assert _para_align(header_root, headline_para_pr) == "CENTER"
    assert _para_align(header_root, subtitle_para_pr) == "CENTER"

    def _run_char_pr(cell: ET.Element) -> str:
        run = cell.find(f"{{{_NS['hp']}}}subList/{{{_NS['hp']}}}p/{{{_NS['hp']}}}run")
        return run.get("charPrIDRef")

    def _char_pr_height(char_pr_id: str) -> str:
        for char_pr in header_root.iter(f"{{{_NS['hh']}}}charPr"):
            if char_pr.get("id") == char_pr_id:
                return char_pr.get("height")
        raise AssertionError(f"charPr id={char_pr_id!r} not found")

    headline_height = _char_pr_height(_run_char_pr(headline_cell))
    subtitle_height = _char_pr_height(_run_char_pr(subtitle_cell))
    # title 롤(18pt=1800) vs body+override(14pt=1400) — 서로 다른 style이
    # 실제로 각 row에 독립 적용됐다.
    assert headline_height != subtitle_height


def test_content_box_items_must_be_a_non_empty_list(tmp_path: Path) -> None:
    spec_path = _write_spec(
        tmp_path,
        [{"type": "content_box", "style": "info_table", "items": []}],
    )
    with pytest.raises(HwpxTemplateAuthoringError, match="items must be a non-empty list"):
        load_template_spec(spec_path)


def test_existing_info_table_is_unaffected(tmp_path: Path) -> None:
    output, resolved = _resolve_and_author(
        tmp_path,
        [
            {
                "type": "info_table",
                "style": "info_table",
                "rows": [
                    {"label": "담당부서", "field_id": "department", "sample_value": "홍보담당관실"},
                ],
            }
        ],
    )
    root = _section_root(output)
    tables = _tables(root)
    assert len(tables) == 1
    row = tables[0].findall(f"{{{_NS['hp']}}}tr")[0]
    cells = row.findall(f"{{{_NS['hp']}}}tc")
    assert [_cell_text(cell) for cell in cells] == ["담당부서", "홍보담당관실"]
    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["fixed_label", "content"]


def test_existing_body_section_with_and_without_heading_is_unaffected(tmp_path: Path) -> None:
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
            },
            {
                "type": "body_section",
                "body_style": "body",
                "field_id": "headline_free",
                "sample_value": "라벨 없는 문단",
            },
        ],
    )
    root = _section_root(output)
    texts = [
        "".join(t.text or "" for t in p.iter(f"{{{_NS['hp']}}}t"))
        for p in root.findall(f"{{{_NS['hp']}}}p")
        if "".join(t.text or "" for t in p.iter(f"{{{_NS['hp']}}}t")).strip()
    ]
    assert texts == ["■ 핵심 현황", "요약 내용", "라벨 없는 문단"]
    rules = build_separation_rules(resolved, output)["rules"]
    assert [rule["role"] for rule in rules] == ["fixed_text", "content", "content"]
