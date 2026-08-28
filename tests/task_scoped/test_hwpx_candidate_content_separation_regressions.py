from __future__ import annotations

from pathlib import Path

from core.templates.hwpx_content_separator import _apply_decisions, _section_decisions
from core.templates.hwpx_semantic_contract import SemanticNodeDecision, SemanticRole
from core.templates.hwpx_separation_rules import TextLocation, load_separation_rules


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


# 회귀: 표 셀의 단일 text node가 semantic 분류에서 FIXED로 확정되어도, 표
# 셀 전용 legacy 판정(_table_cell_is_content)이 독립적으로 CONTENT라고 보면
# free-text 경로의 is_semantic_fixed 가드를 우회해 placeholder_map에 새던 문제.
# FIXED는 어떤 경로로도 placeholder가 되면 안 된다.
def test_semantic_fixed_table_cell_is_never_turned_into_a_placeholder(
    tmp_path: Path,
) -> None:
    section = tmp_path / "section0.xml"
    section.write_text(
        SECTION_START
        + '<hp:p><hp:run><hp:tbl rowCnt="2" colCnt="1">'
        + '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>제목 입력</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        + '<hp:tr><hp:tc><hp:cellAddr rowAddr="1" colAddr="0"/><hp:subList>'
        + "<hp:p><hp:run><hp:t>부제 입력</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        + "</hp:tbl></hp:run></hp:p></hs:sec>",
        encoding="utf-8",
    )
    # "부제 입력"은 legacy classify_text만으로는 CONTENT로 보이는 셀이지만
    # (선행 테스트가 증명), 사람이 semantic 분류에서 FIXED로 확정했다고 가정한다.
    fixed_decision = SemanticNodeDecision(
        role=SemanticRole.FIXED,
        source_sha256="a" * 64,
        text_sha256="a" * 64,
        location=TextLocation(
            section="section0.xml",
            text_node_index=1,
            table=0,
            row=1,
            col=0,
            paragraph_index=1,
        ),
        reason_codes=("test_reason",),
        evidence=("test_evidence",),
    )

    _, table_fields = _section_decisions(
        section,
        load_separation_rules(None),
        {},
        section_index=0,
        semantic_decisions=(fixed_decision,),
    )

    assert {field["sample_value"] for field in table_fields} == {"제목 입력"}
