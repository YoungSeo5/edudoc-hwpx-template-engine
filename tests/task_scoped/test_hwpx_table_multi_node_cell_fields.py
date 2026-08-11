"""표 셀에 텍스트 노드가 둘 이상이면 노드 단위로 필드를 잡는다.

셀 단위(table_cell) 치환은 hwp-skill의 replace_cell_text에 위임되는데, 그 전략은
셀의 첫 노드에만 값을 쓰고 나머지 노드를 빈 문자열로 만든다. 따라서 리터럴과
변수가 한 셀에 섞여 있으면 리터럴이 소실된다. 단일 노드 셀은 지울 나머지가 없어
기존 동작 그대로 둔다.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.templates.hwpx_content_separator import separate_hwpx_template_content


HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
    "<hh:beginNum/>"
    "</hh:head>"
)
CONTENT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
    "<opf:manifest>"
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    "</opf:manifest>"
    '<opf:spine><opf:itemref idref="section0"/></opf:spine>'
    "</opf:package>"
)

# 표 0 (1행 1열): 노드 2개 — 고정 장 번호 "Ⅰ. " + 문서마다 바뀌는 제목.
#   승인된 금감원 원페이지의 t1r0c0와 같은 형태다.
# 표 1 (1행 1열): 노드 1개 — 단일 노드 셀 (기존 table_cell 경로 유지 대상).
#   같은 표에 로마자 마커가 있으면 marker_companion으로 고정 분류되므로 표를 나눈다.
SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1">'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    "<hp:p><hp:run><hp:t>Ⅰ. </hp:t>"
    "<hp:t>◆◆◆◆◆ 진행상황</hp:t></hp:run></hp:p>"
    "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1">'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    "<hp:p><hp:run><hp:t>디지털감독국 상시감시팀</hp:t></hp:run></hp:p>"
    "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>□ 최근 이상매매 정황이 포착됨</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)


def _source_hwpx(tmp_path: Path) -> Path:
    source = tmp_path / "multi_node_cell.hwpx"
    with zipfile.ZipFile(source, "w") as package:
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/section0.xml", SECTION)
    return source


def _separate(tmp_path: Path):
    output = tmp_path / "candidate"
    separate_hwpx_template_content(
        _source_hwpx(tmp_path),
        output,
        template_id="multi_node_cell",
        template_name="multi node cell",
        institution="demo",
    )
    mapping = json.loads((output / "placeholder_map.json").read_text(encoding="utf-8"))
    section_template = (output / "template" / "section0.template.xml").read_text(
        encoding="utf-8"
    )
    return mapping, section_template


def test_multi_node_cell_keeps_literal_and_replaces_only_content_node(
    tmp_path: Path,
) -> None:
    """다중 노드 셀: 고정 장 번호는 원문 유지, 제목 노드만 placeholder가 된다."""
    mapping, section_template = _separate(tmp_path)

    title = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "◆◆◆◆◆ 진행상황"
    )
    assert title["replacement_mode"] == "hp_t_text"
    assert title["placeholder"] in section_template

    # 고정 장 번호는 필드가 되지 않고 템플릿에 원문 그대로 남는다.
    assert "Ⅰ. " in section_template
    assert all(entry["sample_value"] != "Ⅰ." for entry in mapping["fields"])

    # 셀 전체를 한 값으로 삼킨 필드가 없어야 한다.
    assert all(
        entry["sample_value"] != "Ⅰ. ◆◆◆◆◆ 진행상황" for entry in mapping["fields"]
    )


def test_multi_node_cell_field_records_its_cell_coordinates(tmp_path: Path) -> None:
    """노드 단위로 잡혀도 셀 좌표와 cell_margin 계약은 그대로 기록된다."""
    mapping, _ = _separate(tmp_path)

    title = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "◆◆◆◆◆ 진행상황"
    )
    assert (title["table"], title["row"], title["col"]) == (0, 0, 0)
    assert title["section"] == "section0.xml"
    assert "cell_margin" in title["layout_context"]


def test_single_node_cell_still_uses_table_cell_mode(tmp_path: Path) -> None:
    """단일 노드 셀은 지울 나머지 노드가 없으므로 기존 table_cell 경로를 유지한다."""
    mapping, section_template = _separate(tmp_path)

    department = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "디지털감독국 상시감시팀"
    )
    assert department["replacement_mode"] == "table_cell"
    assert (department["table"], department["row"], department["col"]) == (1, 0, 0)
    # 셀 단위 필드는 템플릿에 placeholder를 쓰지 않고 좌표로만 기록된다.
    assert department["placeholder"] not in section_template
