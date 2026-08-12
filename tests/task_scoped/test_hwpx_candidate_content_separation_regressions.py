from __future__ import annotations

from pathlib import Path

from core.templates.hwpx_content_separator import _apply_decisions, _section_decisions
from core.templates.hwpx_separation_rules import load_separation_rules


SECTION_START = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
)


def test_hp_t_placeholder_preserves_leading_ascii_spaces(tmp_path: Path) -> None:
    section = tmp_path / "section0.xml"
    section.write_text(
        SECTION_START
        + "<hp:p><hp:run><hp:t>  한국농어촌공사는 내용을 작성한다</hp:t>"
        + "</hp:run></hp:p></hs:sec>",
        encoding="utf-8",
    )

    decisions, _ = _section_decisions(
        section,
        load_separation_rules(None),
        {},
        section_index=0,
    )
    template, applied = _apply_decisions(
        section.read_text(encoding="utf-8"),
        decisions,
    )

    assert applied[0]["sample_value"].startswith("  한국농어촌공사는")
    assert "<hp:t>  {{content_01}}</hp:t>" in template


def test_symmetric_single_axis_table_cells_share_content_classification(
    tmp_path: Path,
) -> None:
    section = tmp_path / "section0.xml"
    section.write_text(
        SECTION_START
        + '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="2"><hp:tr>'
        + '<hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>그림1</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        + '<hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>그림2</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        + "</hp:tr></hp:tbl></hp:run></hp:p>"
        + '<hp:p><hp:run><hp:tbl rowCnt="2" colCnt="1">'
        + '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>제목 입력</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        + '<hp:tr><hp:tc><hp:cellAddr rowAddr="1" colAddr="0"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>부제 입력</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        + "</hp:tbl></hp:run></hp:p></hs:sec>",
        encoding="utf-8",
    )

    _, table_fields = _section_decisions(
        section,
        load_separation_rules(None),
        {},
        section_index=0,
    )

    assert {field["sample_value"] for field in table_fields} == {
        "그림1",
        "그림2",
        "제목 입력",
        "부제 입력",
    }
    assert all(field["replacement_mode"] == "table_cell" for field in table_fields)
