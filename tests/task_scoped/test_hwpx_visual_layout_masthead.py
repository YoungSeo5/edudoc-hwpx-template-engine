"""HWPX visual layout materialization — masthead, logo, info_table ratio,
section heading hierarchy, paragraph layout (institution-design-contract-v1
visual-layout task, 2026-08-18).

이전 task(institution-design-contract-v1)는 skeleton/default style leakage를
막고 font/color/bold를 명시적으로 확정하는 데까지만 다뤘다. 사람이 candidate를
직접 열어 본 결과, 실제 시각 구조(masthead·로고·표 비율·section hierarchy·
문단 간격)가 없어 "일반 제목 문단 + 1행 2열 표 + 일반 문단"에 그쳤다 — 이
파일은 그 격차를 메우는 실제 materialization 코드를 검증한다.

단순히 "생성됐다"만 보지 않는다:

1. masthead — 실제 표(테두리/크기 있는 shape)로 만들어지고, 그 테두리/치수가
   institution design 값과 정확히 일치하는지.
2. logo — 문자가 아니라 실제 BinData 이진 항목 + manifest 등록 + `hp:pic`
   참조로 연결되는지.
3. info_table — label:value 열 비율이 institution design의
   ``label_width_ratio``를 반영하고 고정 1:1이 아닌지.
4. section heading — body와 실제로 다른 charPr(크기)과 paraPr(구분선·간격·
   들여쓰기 없음)을 갖는지.
5. paragraph layout — line spacing/문단 간격/들여쓰기가 skeleton 기본값(0)이
   아니라 institution 값으로 실제 적용됐는지.

모두 ``tests/fixtures/template-contracts/edudoc.institution_design.json``
(테스트 fixture — 실제 기관 값이 아니다, 로고 asset도
``tests/fixtures/template-contracts/assets/``의 자체 생성 테스트용 PNG다)와
``tests/fixtures/template-spec/weekly_report.template_spec.json``만 사용해
private submodule 초기화 여부와 무관하게 돈다.
"""
from __future__ import annotations

import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_authoring_resolve import resolve  # noqa: E402
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    generate_source_hwpx,
    load_template_spec,
)

FIXTURE = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report.template_spec.json"
INSTITUTION_DESIGN_FIXTURE = (
    ROOT / "tests" / "fixtures" / "template-contracts" / "edudoc.institution_design.json"
)

_NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
}
_HWPUNIT_PER_MM = 7200 / 25.4

# tests/fixtures/template-contracts/edudoc.institution_design.json에 실제로
# 적힌 masthead/table 값 — 이 테스트가 그 값을 그대로 베끼지 않도록, 매
# 검증에서 계산해 쓴다(fixture가 바뀌면 이 상수도 같이 바뀌어야 실패해서
# 드러난다는 뜻이기도 하다). 세 칸 폭은 institution이 명시적으로 정한
# logo_left_slot_width_mm/title_slot_width_mm/logo_right_slot_width_mm이다
# — 로고 크기나 cell_margin에서 유도한 값이 아니다(v3 visual QA P1 fix).
_MASTHEAD_LOGO_LEFT_SLOT_MM = 34.0
_MASTHEAD_TITLE_SLOT_MM = 102.0
_MASTHEAD_LOGO_RIGHT_SLOT_MM = 34.0
_MASTHEAD_WIDTH_MM = 170.0
_TABLE_LABEL_WIDTH_RATIO = 0.22


def _resolved_and_source(tmp_path: Path):
    spec = load_template_spec(FIXTURE)
    resolved = resolve(INSTITUTION_DESIGN_FIXTURE, spec)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    return resolved, source_hwpx


def _read_package(source_hwpx: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(source_hwpx)


def _read_xml(package: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(package.read(name))


def _border_fill(header_root: ET.Element, border_fill_id_ref: str) -> ET.Element:
    for border_fill in header_root.iter(f"{{{_NS['hh']}}}borderFill"):
        if border_fill.get("id") == border_fill_id_ref:
            return border_fill
    raise AssertionError(f"borderFill id={border_fill_id_ref!r} not found")


def _char_pr(header_root: ET.Element, char_pr_id_ref: str) -> ET.Element:
    for char_pr in header_root.iter(f"{{{_NS['hh']}}}charPr"):
        if char_pr.get("id") == char_pr_id_ref:
            return char_pr
    raise AssertionError(f"charPr id={char_pr_id_ref!r} not found")


def _para_pr(header_root: ET.Element, para_pr_id_ref: str) -> ET.Element:
    for para_pr in header_root.iter(f"{{{_NS['hh']}}}paraPr"):
        if para_pr.get("id") == para_pr_id_ref:
            return para_pr
    raise AssertionError(f"paraPr id={para_pr_id_ref!r} not found")


def _default_margin(para_pr: ET.Element, side: str) -> int:
    default_branch = para_pr.find(f"{{{_NS['hp']}}}switch/{{{_NS['hp']}}}default")
    assert default_branch is not None, "paraPr has no hp:default branch"
    node = default_branch.find(f"{{{_NS['hh']}}}margin/{{{_NS['hc']}}}{side}")
    assert node is not None, f"paraPr hp:default margin has no {side!r}"
    return int(node.get("value"))


def _paragraphs_in_order(section_root: ET.Element) -> list[ET.Element]:
    return list(section_root.findall(f"{{{_NS['hp']}}}p"))


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(t.text or "" for t in paragraph.iter(f"{{{_NS['hp']}}}t"))


# ---------------------------------------------------------------------------
# 1. masthead — 실제 표(shape) + border/size가 institution design과 일치.
# ---------------------------------------------------------------------------


def test_masthead_is_a_bordered_1x3_table_sized_from_institution_design(
    tmp_path: Path,
) -> None:
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")

    tables = section_root.findall(f".//{{{_NS['hp']}}}tbl")
    assert len(tables) == 2, "masthead(로고+문서명) + info_table, 2개의 표가 있어야 한다"
    masthead = tables[0]

    assert masthead.get("rowCnt") == "1"
    assert masthead.get("colCnt") == "3"

    border_fill = _border_fill(header_root, masthead.get("borderFillIDRef"))
    left_border = border_fill.find(f"{{{_NS['hh']}}}leftBorder")
    assert left_border is not None
    assert left_border.get("type") == "SOLID"
    assert left_border.get("width") == "0.4 mm"
    assert left_border.get("color") == "#1F3864"  # fixture의 masthead.border_color

    sz = masthead.find(f"{{{_NS['hp']}}}sz")
    assert sz is not None
    assert sz.get("width") == str(round(_MASTHEAD_WIDTH_MM * _HWPUNIT_PER_MM))
    assert sz.get("height") == str(round(22.0 * _HWPUNIT_PER_MM))  # fixture의 masthead.height_mm

    cell_sizes = [cell.find(f"{{{_NS['hp']}}}cellSz") for cell in masthead.findall(f".//{{{_NS['hp']}}}tc")]
    assert cell_sizes[0].get("width") == str(round(_MASTHEAD_LOGO_LEFT_SLOT_MM * _HWPUNIT_PER_MM))
    assert cell_sizes[1].get("width") == str(round(_MASTHEAD_TITLE_SLOT_MM * _HWPUNIT_PER_MM))
    assert cell_sizes[2].get("width") == str(round(_MASTHEAD_LOGO_RIGHT_SLOT_MM * _HWPUNIT_PER_MM))
    total = _MASTHEAD_LOGO_LEFT_SLOT_MM + _MASTHEAD_TITLE_SLOT_MM + _MASTHEAD_LOGO_RIGHT_SLOT_MM
    assert total == _MASTHEAD_WIDTH_MM
    # 왼쪽/오른쪽 칸이 가운데 문서명 칸과 같은 폭이 되면 안 된다 — width/3
    # 균등분배가 아니라 institution이 명시적으로 다른 값을 정했다는 증거.
    assert _MASTHEAD_LOGO_LEFT_SLOT_MM != _MASTHEAD_TITLE_SLOT_MM
    assert _MASTHEAD_LOGO_RIGHT_SLOT_MM != _MASTHEAD_TITLE_SLOT_MM


def test_masthead_center_cell_holds_document_name_logo_cells_hold_no_text(
    tmp_path: Path,
) -> None:
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        section_root = _read_xml(package, "Contents/section0.xml")

    masthead = section_root.findall(f".//{{{_NS['hp']}}}tbl")[0]
    cells = masthead.findall(f".//{{{_NS['hp']}}}tc")
    assert len(cells) == 3
    texts = ["".join(t.text or "" for t in cell.iter(f"{{{_NS['hp']}}}t")) for cell in cells]
    assert texts == ["", "주간업무보고서", ""]

    pics_per_cell = [cell.findall(f".//{{{_NS['hp']}}}pic") for cell in cells]
    assert len(pics_per_cell[0]) == 1  # 왼쪽 로고
    assert len(pics_per_cell[1]) == 0  # 문서명 칸에는 그림 없음
    assert len(pics_per_cell[2]) == 1  # 오른쪽 로고


# ---------------------------------------------------------------------------
# 2. logo — 텍스트 문자가 아니라 실제 BinData/manifest/hp:pic로 연결된다.
# ---------------------------------------------------------------------------


def test_masthead_logos_are_embedded_as_bindata_with_manifest_and_header_registration(
    tmp_path: Path,
) -> None:
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        names = package.namelist()
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")
        manifest_xml = package.read("Contents/content.hpf").decode("utf-8")

    bin_paths = [name for name in names if name.startswith("BinData/")]
    assert len(bin_paths) == 2, f"두 로고가 각각 BinData 항목이어야 한다: {bin_paths}"

    # 실제로 유효한 PNG 바이트인지(문자로 흉내낸 게 아니라 진짜 이미지인지)
    for bin_path in bin_paths:
        with _read_package(source_hwpx) as package:
            data = package.read(bin_path)
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{bin_path} is not a valid PNG"

    bin_ids = {item.get("BinData") for item in header_root.iter(f"{{{_NS['hh']}}}binItem")}
    assert bin_ids == {Path(p).name for p in bin_paths}

    # OPC manifest(content.hpf)에도 같은 항목이 image/png로 등록돼 있어야
    # 실제 relationship이 연결된 것이다 — BinData 파일만 존재하고 manifest에
    # 없으면 패키지가 참조 무결성을 잃는다.
    for bin_path in bin_paths:
        item_id = Path(bin_path).stem
        assert f'id="{item_id}"' in manifest_xml
        assert f'href="{bin_path}"' in manifest_xml
        assert 'media-type="image/png"' in manifest_xml.split(f'id="{item_id}"', 1)[1][:200]

    # section0.xml의 hc:img가 실제로 그 binaryItemIDRef를 참조하는지.
    hc_ns = "http://www.hancom.co.kr/hwpml/2011/core"
    img_refs = {img.get("binaryItemIDRef") for img in section_root.iter(f"{{{hc_ns}}}img")}
    assert img_refs == {Path(p).stem for p in bin_paths}


# ---------------------------------------------------------------------------
# 3. info_table — label:value 비율이 institution design 값을 반영, 1:1 고정 아님.
# ---------------------------------------------------------------------------


def test_info_table_column_widths_follow_resolved_label_width_ratio_not_fixed_half(
    tmp_path: Path,
) -> None:
    resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        section_root = _read_xml(package, "Contents/section0.xml")

    info_table = section_root.findall(f".//{{{_NS['hp']}}}tbl")[1]
    assert info_table.get("colCnt") == "2"

    style = next(s for s in resolved.sections if s.type == "info_table").style
    assert style.label_width_ratio == _TABLE_LABEL_WIDTH_RATIO
    assert style.label_width_ratio != 0.5  # 이번 task가 없애려는 고정 1:1 비율

    cell_sizes = [
        cell.find(f"{{{_NS['hp']}}}cellSz") for cell in info_table.findall(f".//{{{_NS['hp']}}}tc")
    ]
    label_width = int(cell_sizes[0].get("width"))
    value_width = int(cell_sizes[1].get("width"))
    assert label_width != value_width
    expected_ratio = label_width / (label_width + value_width)
    assert abs(expected_ratio - _TABLE_LABEL_WIDTH_RATIO) < 0.01
    # label(짧은 "보고 기간")이 value(긴 날짜 범위)보다 훨씬 좁아야 한다.
    assert value_width > label_width * 2


# ---------------------------------------------------------------------------
# 4. section heading — body와 실제로 다른 charPr/paraPr를 갖는다.
# ---------------------------------------------------------------------------


def test_section_heading_has_distinct_size_and_marker_from_body(tmp_path: Path) -> None:
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")

    paragraphs = _paragraphs_in_order(section_root)
    heading_paragraph = next(p for p in paragraphs if _paragraph_text(p) == "■ 금주 업무")
    body_paragraph = next(
        p for p in paragraphs if _paragraph_text(p) == "신규 기능 A 개발 완료, 정기 점검 수행"
    )

    # 4-1. marker(■ )가 heading에만 붙는다 — body 텍스트에는 없다.
    assert _paragraph_text(heading_paragraph).startswith("■ ")
    assert not _paragraph_text(body_paragraph).startswith("■")

    # 4-2. charPr 크기가 다르다(15pt heading vs 13pt body, fixture 값 — 위계는
    # title(17) > heading(15) > body(13) > metadata(11)).
    heading_run = heading_paragraph.find(f"{{{_NS['hp']}}}run")
    body_run = body_paragraph.find(f"{{{_NS['hp']}}}run")
    heading_char_pr = _char_pr(header_root, heading_run.get("charPrIDRef"))
    body_char_pr = _char_pr(header_root, body_run.get("charPrIDRef"))
    assert heading_char_pr.get("height") == str(round(15 * 100))
    assert body_char_pr.get("height") == str(round(13 * 100))
    assert heading_char_pr.get("height") != body_char_pr.get("height")


def test_section_heading_has_no_full_width_rule_and_body_does_not_leak_it(
    tmp_path: Path,
) -> None:
    # v3 visual QA P0-2 + design 재검토: heading_rule_width_mm은 실제 baseline
    # 근거 없이 고른 값이라 edudoc weekly-report design에서 제거됐다(scheme
    # capability 자체는 institution-design-contract.schema.json에 남아 다른
    # 문서가 근거를 갖고 쓸 수 있다). 그러므로 heading/body 모두 밑줄 구분선이
    # 없어야 하고, heading과 body의 paraPr 자체도 서로 달라야 한다(하나가
    # 다른 하나의 paraPrIDRef를 그대로 이어받는 leak이 없어야 함 — P0-2).
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")

    paragraphs = _paragraphs_in_order(section_root)
    heading_paragraph = next(p for p in paragraphs if _paragraph_text(p) == "■ 금주 업무")
    body_paragraph = next(
        p for p in paragraphs if _paragraph_text(p) == "신규 기능 A 개발 완료, 정기 점검 수행"
    )

    assert heading_paragraph.get("paraPrIDRef") != body_paragraph.get("paraPrIDRef")

    heading_para_pr = _para_pr(header_root, heading_paragraph.get("paraPrIDRef"))
    body_para_pr = _para_pr(header_root, body_paragraph.get("paraPrIDRef"))

    for para_pr, label in ((heading_para_pr, "heading"), (body_para_pr, "body")):
        border = para_pr.find(f"{{{_NS['hh']}}}border")
        if border is None:
            continue
        border_fill = _border_fill(header_root, border.get("borderFillIDRef"))
        bottom = border_fill.find(f"{{{_NS['hh']}}}bottomBorder")
        assert bottom is None or bottom.get("type") == "NONE", (
            f"{label} paragraph must not have a bottom-border rule "
            "(heading_rule_width_mm is not used by the edudoc weekly-report design)"
        )


# ---------------------------------------------------------------------------
# 5. paragraph layout — spacing/indent/line spacing이 skeleton 기본값(0)이
#    아니라 institution 값으로 실제 적용된다.
# ---------------------------------------------------------------------------


def test_body_paragraph_applies_indent_and_spacing_not_left_at_skeleton_zero(
    tmp_path: Path,
) -> None:
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")

    body_paragraph = next(
        p
        for p in _paragraphs_in_order(section_root)
        if _paragraph_text(p) == "신규 기능 A 개발 완료, 정기 점검 수행"
    )
    para_pr = _para_pr(header_root, body_paragraph.get("paraPrIDRef"))

    line_spacing = para_pr.find(
        f"{{{_NS['hp']}}}switch/{{{_NS['hp']}}}default/{{{_NS['hh']}}}lineSpacing"
    )
    assert line_spacing is not None
    assert line_spacing.get("value") == "160"  # fixture의 body.line_spacing_percent

    # institution design의 body.indent_left_mm(4.0mm)이 실제 0이 아닌 왼쪽
    # 여백으로 반영된다 — HwpxDocument.new() skeleton 문단은 좌측 여백 0이다.
    assert _default_margin(para_pr, "left") > 0
    # institution design의 body.spacing_after_pt(8pt)가 실제 0이 아닌 문단
    # 다음 간격으로 반영된다.
    assert _default_margin(para_pr, "next") > 0


def test_heading_paragraph_has_no_left_indent_unlike_body(tmp_path: Path) -> None:
    # body만 institution design에서 indent_left_mm을 받았다(section_title에는
    # 없음) — heading은 들여쓰기가 없어야, 예시로 든
    # "■ 금주 업무\n  신규 기능 A 개발 완료 ..." 같은 heading vs 들여써진
    # body의 시각적 위계가 실제로 만들어진다.
    _resolved, source_hwpx = _resolved_and_source(tmp_path)
    with _read_package(source_hwpx) as package:
        header_root = _read_xml(package, "Contents/header.xml")
        section_root = _read_xml(package, "Contents/section0.xml")

    heading_paragraph = next(
        p for p in _paragraphs_in_order(section_root) if _paragraph_text(p) == "■ 금주 업무"
    )
    para_pr = _para_pr(header_root, heading_paragraph.get("paraPrIDRef"))
    assert _default_margin(para_pr, "left") == 0
