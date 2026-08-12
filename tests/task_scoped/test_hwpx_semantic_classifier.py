from __future__ import annotations

import xml.etree.ElementTree as ET

from core.templates.hwpx_semantic_classifier import (
    classify_document_semantics,
    detect_marker_span_candidate,
)
from core.templates.hwpx_semantic_contract import SemanticRole
from core.templates.hwpx_separation_rules import (
    LocationRule,
    SeparationRules,
    TextLocation,
    TextRole,
)


SECTION_START = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
)


def _section(body: str) -> ET.Element:
    return ET.fromstring(SECTION_START + body + "</hs:sec>")


def _decisions(body: str, rules: SeparationRules = SeparationRules()):
    return classify_document_semantics(_section(body), "section0.xml", rules)


def test_conflicting_location_rules_produce_ambiguous() -> None:
    rules = SeparationRules(
        (
            LocationRule(role=TextRole.CONTENT, section="section0.xml", text_node_index=0),
            LocationRule(role=TextRole.FIXED_LABEL, section="section0.xml", text_node_index=0),
        )
    )
    (decision,) = _decisions("<hp:p><hp:run><hp:t>본문</hp:t></hp:run></hp:p>", rules)

    assert decision.role is SemanticRole.AMBIGUOUS
    assert "legacy_rule_conflict" in decision.reason_codes


def test_legacy_rule_override_resolves_whole_node_and_drops_span() -> None:
    rules = SeparationRules(
        (LocationRule(role=TextRole.CONTENT, section="section0.xml", text_node_index=0),),
    )
    (decision,) = _decisions("<hp:p><hp:run><hp:t>- 부제 -</hp:t></hp:run></hp:p>", rules)

    assert decision.role is SemanticRole.CONTENT
    assert "legacy_rule_override" in decision.reason_codes
    assert decision.span is None


def test_nested_table_is_ambiguous() -> None:
    body = (
        '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        "<hp:p><hp:run><hp:t>중첩 표 내용</hp:t></hp:run></hp:p>"
        "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
        "</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    )
    (decision,) = _decisions(body)

    assert decision.role is SemanticRole.AMBIGUOUS
    assert decision.reason_codes == ("nested_table",)


def test_missing_cell_address_is_ambiguous() -> None:
    body = (
        '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        "<hp:subList><hp:p><hp:run><hp:t>주소 없는 셀</hp:t></hp:run></hp:p></hp:subList>"
        "</hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    )
    (decision,) = _decisions(body)

    assert decision.role is SemanticRole.AMBIGUOUS
    assert decision.reason_codes == ("missing_cell_address",)


def test_empty_node_is_fixed() -> None:
    (decision,) = _decisions("<hp:p><hp:run><hp:t></hp:t></hp:run></hp:p>")

    assert decision.role is SemanticRole.FIXED
    assert decision.reason_codes == ("empty_scaffolding",)


def test_same_node_marker_boundary_without_evidence_is_ambiguous() -> None:
    for text in ("- 부제 -", "* 설명", "※ 신청서를 제출하세요"):
        (decision,) = _decisions(f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>")
        assert decision.role is SemanticRole.AMBIGUOUS, text
        assert decision.reason_codes == ("marker_boundary_without_independent_evidence",), text


def test_standalone_marker_falls_back_to_fixed() -> None:
    (decision,) = _decisions("<hp:p><hp:run><hp:t>끝.</hp:t></hp:run></hp:p>")

    assert decision.role is SemanticRole.FIXED
    assert decision.reason_codes == ("structural_fixed_pattern",)


def test_plain_content_falls_back_to_content() -> None:
    (decision,) = _decisions(
        "<hp:p><hp:run><hp:t>한국농어촌공사는 내용을 작성한다</hp:t></hp:run></hp:p>"
    )

    assert decision.role is SemanticRole.CONTENT
    assert decision.reason_codes == ("structural_content_default",)


def test_unspaced_marker_is_not_a_span_candidate() -> None:
    assert detect_marker_span_candidate("*설명") is None


def test_paired_delimiter_prefix_is_not_a_span_candidate() -> None:
    assert detect_marker_span_candidate("(061-123-4567) 문의") is None


def test_lossless_span_reconstructs_raw_body() -> None:
    span = detect_marker_span_candidate("- 부제 -")
    assert span is not None
    assert span.reconstruct_raw_body() == "- 부제 -"
    assert span.marker_prefix_raw == "- "
    assert span.content_raw == "부제"
    assert span.marker_suffix_raw == " -"


def test_marker_span_survives_leading_ascii_and_fwspace_layout_prefix() -> None:
    span = detect_marker_span_candidate('  <hp:fwSpace/>* 설명')
    assert span is not None
    assert span.layout_prefix_raw == '  <hp:fwSpace/>'
    assert span.content_raw == "설명"
