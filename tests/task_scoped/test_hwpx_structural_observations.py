from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import FrozenInstanceError

import pytest

from core.templates.hwpx_content_classifier import build_text_contexts
from core.templates.hwpx_document_observations import observe_hwpx_document
from core.templates.hwpx_structural_observations import observe_hwpx_section
from core.templates.hwpx_separation_rules import TextLocation


SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:t>  Outside  text </hp:t></hp:run></hp:p>'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="2">'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    '<hp:p><hp:run><hp:t>Label</hp:t></hp:run></hp:p>'
    '</hp:subList></hp:tc><hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/>'
    '<hp:subList><hp:p><hp:run><hp:t>Value</hp:t></hp:run></hp:p>'
    '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>'
    '</hs:sec>'
)


def test_build_text_contexts_legacy_projection_remains_unchanged() -> None:
    root = ET.fromstring(SECTION)

    contexts = build_text_contexts(root, "section7.xml")

    assert [item.original_text for item in contexts] == ["  Outside  text ", "Label", "Value"]
    assert [item.normalized_text for item in contexts] == ["Outside text", "Label", "Value"]
    assert [item.location for item in contexts] == [
        TextLocation("section7.xml", 0, None, None, None, 0),
        TextLocation("section7.xml", 1, 0, 0, 0, 2),
        TextLocation("section7.xml", 2, 0, 0, 1, 3),
    ]
    assert [item.table_rows for item in contexts] == [None, 1, 1]
    assert [item.table_cols for item in contexts] == [None, 2, 2]
    assert [item.cell_text_count for item in contexts] == [0, 1, 1]
    assert [item.table_nonempty_cell_count for item in contexts] == [0, 2, 2]


OBSERVATION_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p id="p0" paraPrIDRef="para0" styleIDRef="style0">'
    '<hp:run charPrIDRef="char0">'
    '<hp:t></hp:t><hp:t>  A&amp;B<hp:fwSpace/></hp:t><hp:t>tail</hp:t>'
    '</hp:run></hp:p>'
    '</hs:sec>'
)


def test_observation_records_lossless_text_edges_indexes_and_adjacency() -> None:
    document = observe_hwpx_section(
        OBSERVATION_SECTION,
        section="section2.xml",
        section_ordinal=1,
    )

    empty, entity, tail = document.nodes
    assert (empty.section, empty.section_ordinal, empty.text_node_index) == ("section2.xml", 1, 0)
    assert (entity.original_text, entity.normalized_text, entity.logical_text) == ("  A&B", "A&B", "  A&B\u3000")
    assert entity.raw_body == "  A&amp;B<hp:fwSpace/>"
    assert entity.decoded_to_raw_offsets == ((0, 1), (1, 2), (2, 3), (3, 8), (8, 9), (9, 22))
    assert (
        entity.leading_ascii_space_count,
        entity.trailing_ascii_space_count,
        entity.leading_fwspace_count,
        entity.trailing_fwspace_count,
    ) == (2, 0, 0, 1)
    assert (entity.paragraph_index, entity.run_index) == (0, 0)
    assert (entity.paragraph_text_node_index, entity.run_text_node_index) == (1, 1)
    assert entity.previous_nonempty_text_node_index is None
    assert entity.next_nonempty_text_node_index == 2
    assert tail.previous_nonempty_text_node_index == 1
    assert tail.next_nonempty_text_node_index is None
    assert empty.paragraph_start is True
    assert entity.paragraph_start is False
    assert (
        entity.paragraph_id,
        entity.paragraph_style_ref,
        entity.paragraph_layout_ref,
        entity.character_style_ref,
    ) == ("p0", "para0", "style0", "char0")
    with pytest.raises(FrozenInstanceError):
        setattr(entity, "original_text", "changed")


def test_fwspace_edge_counts_only_include_contiguous_edge_nodes() -> None:
    xml = (
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p><hp:run><hp:t><hp:fwSpace/><hp:fwSpace/> X '
        '<hp:fwSpace/><hp:fwSpace/></hp:t></hp:run></hp:p></hs:sec>'
    )

    node = observe_hwpx_section(
        xml,
        section="section0.xml",
        section_ordinal=0,
    ).nodes[0]

    assert node.logical_text == "\u3000\u3000 X \u3000\u3000"
    assert (
        node.leading_ascii_space_count,
        node.trailing_ascii_space_count,
        node.leading_fwspace_count,
        node.trailing_fwspace_count,
    ) == (0, 0, 2, 2)


MALFORMED_AND_NESTED = (
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="2" borderFillIDRef="outer">'
    '<hp:tr><hp:tc borderFillIDRef="c0"><hp:cellAddr rowAddr="0" colAddr="0"/>'
    '<hp:cellSpan rowSpan="1" colSpan="1"/><hp:subList><hp:p><hp:run>'
    '<hp:t>known</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    '<hp:tc borderFillIDRef="c1"><hp:cellAddr rowAddr="bad"/>'
    '<hp:subList><hp:p><hp:run><hp:t>unknown</hp:t>'
    '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/>'
    '<hp:subList><hp:p><hp:run><hp:t>nested</hp:t></hp:run></hp:p></hp:subList>'
    '</hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hp:subList></hp:tc>'
    '</hp:tr></hp:tbl></hp:run></hp:p></hs:sec>'
)


def test_missing_addresses_stay_unknown_and_nested_table_depth_is_observed() -> None:
    document = observe_hwpx_section(
        MALFORMED_AND_NESTED,
        section="section0.xml",
        section_ordinal=0,
    )

    known, unknown, nested = document.nodes
    assert (known.row, known.col, known.cell_address_known) == (0, 0, True)
    assert (unknown.row, unknown.col, unknown.cell_address_known) == (None, None, False)
    assert (nested.row, nested.col, nested.cell_address_known) == (0, 0, True)
    assert (known.table_index, known.table_depth) == (0, 1)
    assert (unknown.table_index, unknown.table_depth) == (0, 1)
    assert (nested.table_index, nested.table_depth) == (1, 2)
    assert known.cell_text_node_indexes == (0,)
    assert unknown.cell_text_node_indexes == (1,)
    assert nested.cell_text_node_indexes == (2,)
    assert unknown.table_border_fill_ref == "outer"
    assert unknown.cell_border_fill_ref == "c1"


def test_cell_local_nodes_exclude_nested_table_text() -> None:
    document = observe_hwpx_section(MALFORMED_AND_NESTED, section="section0.xml", section_ordinal=0)

    outer_cell_node, nested_cell_node = document.nodes[1:]
    assert outer_cell_node.cell_text_node_indexes == (1,)
    assert nested_cell_node.cell_text_node_indexes == (2,)


def test_row_signature_excludes_nested_cell_text_from_all_cell_evidence() -> None:
    xml = MALFORMED_AND_NESTED.replace(
        '<hp:cellAddr rowAddr="bad"/>',
        '<hp:cellAddr rowAddr="0" colAddr="1"/>',
    )

    document = observe_hwpx_section(xml, section="section0.xml", section_ordinal=0)
    outer_cell = document.tables[0].row_signatures[0].cells[1]
    nested_cell = document.tables[1].row_signatures[0].cells[0]

    assert outer_cell.text_node_count == 1
    assert len(outer_cell.style_layout_ids) == 1
    assert len(outer_cell.lexical_shapes) == 1
    assert outer_cell.lexical_shapes[0].character_class_sequence == "LLLLLLL"
    assert nested_cell.text_node_count == 1


CONTACT_TABLE = (
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:tbl rowCnt="2" colCnt="6" borderFillIDRef="table">'
    '<hp:tr>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:cellSpan rowSpan="2" colSpan="1"/>'
    '<hp:subList><hp:p paraPrIDRef="p"><hp:run charPrIDRef="c"><hp:t>담당 부서</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    + "".join(
        f'<hp:tc borderFillIDRef="b{col}"><hp:cellAddr rowAddr="0" colAddr="{col}"/>'
        '<hp:cellSpan rowSpan="1" colSpan="1"/><hp:subList><hp:p paraPrIDRef="p">'
        f'<hp:run charPrIDRef="c"><hp:t>R0C{col}{"<hp:lineBreak/>" if col == 4 else ""}</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        for col in range(1, 6)
    )
    + '</hp:tr><hp:tr>'
    + "".join(
        f'<hp:tc borderFillIDRef="b{col}"><hp:cellAddr rowAddr="1" colAddr="{col}"/>'
        '<hp:cellSpan rowSpan="1" colSpan="1"/><hp:subList><hp:p paraPrIDRef="p">'
        f'<hp:run charPrIDRef="c"><hp:t>R1C{col}{"<hp:lineBreak/>" if col == 4 else ""}</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        for col in range(1, 5)
    )
    + '<hp:tc borderFillIDRef="different"><hp:cellAddr rowAddr="1" colAddr="5"/>'
    '<hp:cellSpan rowSpan="1" colSpan="1"/><hp:subList><hp:p paraPrIDRef="p">'
    '<hp:run charPrIDRef="c"><hp:t>R1C5</hp:t><hp:t>extra</hp:t></hp:run>'
    '</hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></hs:sec>'
)


def test_contact_table_row_signatures_and_peer_evidence_are_structural_only() -> None:
    document = observe_hwpx_section(CONTACT_TABLE, section="section0.xml", section_ordinal=0)

    table = document.tables[0]
    first, second = table.row_signatures
    comparison = table.peer_structures[0]
    assert (table.declared_row_count, table.declared_column_count) == (2, 6)
    assert first.ordered_occupied_columns == (0, 1, 2, 3, 4, 5)
    assert second.ordered_occupied_columns == (1, 2, 3, 4, 5)
    assert (first.cells[0].row_span, first.cells[0].column_span) == (2, 1)
    assert comparison.columns == (1, 2, 3, 4, 5)
    assert comparison.matching_columns == (1, 2, 3, 4)
    assert comparison.mismatching_columns == (5,)
    assert comparison.evidence == ("semantic_repeat_undeclared",)
    assert first.cells[1].lexical_shapes[0].state == "nonempty"
    assert first.cells[1].lexical_shapes[0].character_class_sequence == "LDLD"
    assert first.cells[1].lexical_shapes[0].line_count == 1
    assert first.cells[4].lexical_shapes[0].line_count == 2
    assert not hasattr(document, "roles")
    assert not hasattr(document, "categories")
    assert not hasattr(document, "repeat_blocks")
    assert not hasattr(document, "annotations")


def test_observation_identity_is_stable_and_text_sensitive_across_sections() -> None:
    first = observe_hwpx_section(
        OBSERVATION_SECTION,
        section="section0.xml",
        section_ordinal=0,
    )
    same = observe_hwpx_section(
        OBSERVATION_SECTION.encode("utf-8"),
        section="section0.xml",
        section_ordinal=0,
    )
    other_section = observe_hwpx_section(
        OBSERVATION_SECTION,
        section="section1.xml",
        section_ordinal=1,
    )
    changed = observe_hwpx_section(
        OBSERVATION_SECTION.replace("tail", "changed"),
        section="section0.xml",
        section_ordinal=0,
    )

    assert [node.observation_id for node in first.nodes] == [node.observation_id for node in same.nodes]
    assert first.nodes[2].text_sha256 != changed.nodes[2].text_sha256
    assert first.nodes[2].observation_id != changed.nodes[2].observation_id
    assert first.nodes[2].observation_id != other_section.nodes[2].observation_id


def test_document_pass_assigns_deterministic_section_ordinals() -> None:
    sections = (
        ("section0.xml", OBSERVATION_SECTION),
        ("section2.xml", OBSERVATION_SECTION.replace("tail", "second")),
    )

    first = observe_hwpx_document(sections)
    same = observe_hwpx_document(sections)

    assert tuple(item.section_ordinal for item in first) == (0, 1)
    assert tuple(item.section for item in first) == ("section0.xml", "section2.xml")
    assert tuple(node.section_ordinal for item in first for node in item.nodes) == (
        (0,) * len(first[0].nodes) + (1,) * len(first[1].nodes)
    )
    assert tuple(node.observation_id for item in first for node in item.nodes) == tuple(
        node.observation_id for item in same for node in item.nodes
    )
