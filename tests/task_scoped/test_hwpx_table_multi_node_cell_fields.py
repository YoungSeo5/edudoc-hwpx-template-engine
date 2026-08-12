from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapters.hwpx_template_renderer import render_candidate_roundtrip
from core.templates.hwpx_content_separator import separate_hwpx_template_content


ROOT = Path(__file__).resolve().parents[2]
ONE_PAGE_SOURCE = (
    ROOT
    / "templates"
    / "institutions"
    / "금융감독원"
    / "금감원 원페이지"
    / "source.hwpx"
)
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


def _marker_boundary_content_rules(tmp_path: Path, text_node_indexes: tuple[int, ...]) -> Path:
    # "◆◆◆◆◆ 진행상황"과 "□ 최근..." 노드는 같은 노드 안에 선행 기호 경계가
    # 있어 semantic classifier가 기본적으로 AMBIGUOUS로 남긴다. 이 fixture는
    # 기존 legacy CONTENT 분류와 같은 결과가 되도록 사람이 --rules로 확정한다.
    rules = tmp_path / "content-separation-rules.json"
    rules.write_text(
        json.dumps(
            {
                "rules": [
                    {"role": "content", "section": "section0.xml", "text_node_index": index}
                    for index in text_node_indexes
                ]
            }
        ),
        encoding="utf-8",
    )
    return rules


def _separate(tmp_path: Path):
    output = tmp_path / "candidate"
    separate_hwpx_template_content(
        _source_hwpx(tmp_path),
        output,
        template_id="multi_node_cell",
        template_name="multi node cell",
        institution="demo",
        rules_path=_marker_boundary_content_rules(tmp_path, (1, 3)),
    )
    mapping = json.loads((output / "placeholder_map.json").read_text(encoding="utf-8"))
    section_template = (output / "template" / "section0.template.xml").read_text(
        encoding="utf-8"
    )
    return mapping, section_template


def test_multi_node_cell_keeps_literal_and_replaces_only_content_node(
    tmp_path: Path,
) -> None:
    mapping, section_template = _separate(tmp_path)

    title = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "◆◆◆◆◆ 진행상황"
    )
    assert title["replacement_mode"] == "hp_t_text"
    assert title["placeholder"] in section_template

    assert "Ⅰ. " in section_template
    assert all(entry["sample_value"] != "Ⅰ." for entry in mapping["fields"])

    assert all(
        entry["sample_value"] != "Ⅰ. ◆◆◆◆◆ 진행상황" for entry in mapping["fields"]
    )


def test_multi_node_cell_field_records_its_cell_coordinates(tmp_path: Path) -> None:
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
    mapping, section_template = _separate(tmp_path)

    department = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "디지털감독국 상시감시팀"
    )
    assert department["replacement_mode"] == "table_cell"
    assert (department["table"], department["row"], department["col"]) == (1, 0, 0)
    assert department["placeholder"] not in section_template


def test_roundtrip_fills_multi_node_text_and_single_node_cell_together(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    separate_hwpx_template_content(
        ONE_PAGE_SOURCE,
        candidate,
        template_id="one_page_multi_node_roundtrip",
        template_name="one page multi node roundtrip",
        institution="금융감독원",
        rules_path=_marker_boundary_content_rules(tmp_path, (0, 4, 25, 26, 27, 42)),
    )
    mapping = json.loads(
        (candidate / "placeholder_map.json").read_text(encoding="utf-8")
    )
    fields = {
        entry["field_id"]: entry["sample_value"]
        for entry in mapping["fields"]
    }
    title = next(
        entry
        for entry in mapping["fields"]
        if entry["sample_value"] == "◆◆◆◆◆ 진행상황"
    )
    table_cell = next(
        entry
        for entry in mapping["fields"]
        if entry["replacement_mode"] == "table_cell"
    )
    fields[title["field_id"]] = "교체된 진행상황"
    fields[table_cell["field_id"]] = "교체된 표 셀"

    output = tmp_path / "roundtrip.hwpx"
    result = render_candidate_roundtrip(candidate, fields, output)

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    assert result.leftover_placeholders == []
    assert "Ⅰ. " in section
    assert "교체된 진행상황" in section
    assert "교체된 표 셀" in section
    assert "◆◆◆◆◆ 진행상황" not in section
    assert table_cell["sample_value"] not in section
