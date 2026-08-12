from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Final

from .hwpx_content_classifier import TextContext, build_text_contexts, classify_text
from .hwpx_raw_text_observations import decode_raw_body
from .hwpx_semantic_contract import LosslessTextSpan, SemanticNodeDecision, SemanticRole
from .hwpx_separation_rules import SeparationRules, TextRole
from .hwpx_structural_observation_models import TextObservation
from .hwpx_structural_observations import observe_hwpx_section

# 이 모듈의 경계:
# 구조 관찰(hwpx_structural_observations)과 기존 규칙 계층
# (hwpx_separation_rules/hwpx_content_classifier)만 근거로,
# 각 <hp:t>에 하나의 SemanticRole 결정을 붙인다.
# 위치만으로 의미를 추측하지 않고, 규칙 충돌·중첩 표·빈 텍스트·
# 동일 노드 표식 경계는 근거가 없으면 AMBIGUOUS로 남긴다.

_PAIRED_DELIMITERS: Final = frozenset("()[]{}<>「」『』【】〈〉《》'\"“”‘’")


class SemanticAmbiguityError(ValueError):
    """Raised when at least one text node has no deterministic semantic role."""


def detect_marker_span_candidate(raw_body: str) -> LosslessTextSpan | None:
    """Detect a role-neutral same-node leading-symbol lossless span candidate.

    This only records a boundary; it never decides FIXED/CONTENT/MARKER_CONTENT.
    """
    prefix_end = _layout_prefix_end(raw_body)
    layout_prefix_raw = raw_body[:prefix_end]
    remainder_raw = raw_body[prefix_end:]
    if "<" in remainder_raw:
        # 남은 raw 본문에 fwSpace/lineBreak 등 다른 XML 요소가 섞여 있으면
        # 표식/콘텐츠 경계가 자식 XML을 가로지를 수 있으므로 후보로 삼지 않는다.
        return None
    decoded, raw_offsets = decode_raw_body(remainder_raw)
    offsets = tuple((start + prefix_end, end + prefix_end) for start, end in raw_offsets)

    marker_len = 0
    for char in decoded:
        if _is_marker_symbol(char):
            marker_len += 1
        else:
            break
    if marker_len == 0 or any(char in _PAIRED_DELIMITERS for char in decoded[:marker_len]):
        return None

    separator_len = 0
    cursor = marker_len
    while cursor < len(decoded) and decoded[cursor] == " ":
        separator_len += 1
        cursor += 1
    if separator_len == 0:
        return None

    payload_start = marker_len + separator_len
    if payload_start >= len(decoded):
        return None
    first_payload_char = decoded[payload_start]
    if not (first_payload_char.isalpha() or first_payload_char.isdigit()):
        return None

    marker_sequence = decoded[:marker_len]
    tail = decoded[payload_start:]
    suffix_match = re.search(r"( +)" + re.escape(marker_sequence) + r"$", tail)
    content_decoded = tail[: suffix_match.start()] if suffix_match else tail
    if not content_decoded or not any(
        char.isalpha() or char.isdigit() for char in content_decoded
    ):
        return None

    marker_prefix_end_decoded = payload_start
    content_end_decoded = payload_start + len(content_decoded)

    marker_prefix_raw_end = offsets[marker_prefix_end_decoded - 1][1]
    if offsets[marker_prefix_end_decoded][0] != marker_prefix_raw_end:
        return None  # 표식/콘텐츠 경계에 정렬되지 않은 raw 구간(다른 요소)이 있다.
    content_raw_end = offsets[content_end_decoded - 1][1]
    if content_end_decoded < len(decoded) and offsets[content_end_decoded][0] != content_raw_end:
        return None  # 콘텐츠/표식-접미 경계에 정렬되지 않은 raw 구간이 있다.

    marker_prefix_raw = raw_body[prefix_end:marker_prefix_raw_end]
    content_raw = raw_body[marker_prefix_raw_end:content_raw_end]
    marker_suffix_raw = raw_body[content_raw_end:]
    if "<" in marker_prefix_raw or "<" in content_raw or "<" in marker_suffix_raw:
        return None

    try:
        return LosslessTextSpan(
            raw_body=raw_body,
            layout_prefix_raw=layout_prefix_raw,
            marker_prefix_raw=marker_prefix_raw,
            content_raw=content_raw,
            marker_suffix_raw=marker_suffix_raw,
            content_decoded=content_decoded,
            layout_prefix_offsets=(0, prefix_end),
            marker_prefix_offsets=(prefix_end, marker_prefix_raw_end),
            content_offsets=(marker_prefix_raw_end, content_raw_end),
            marker_suffix_offsets=(content_raw_end, len(raw_body)),
        )
    except ValueError:
        # 계약 불변식(예: entity 왕복)이 성립하지 않으면 후보로 삼지 않는다.
        return None


def classify_document_semantics(
    root: ET.Element, section: str, rules: SeparationRules
) -> tuple[SemanticNodeDecision, ...]:
    xml = ET.tostring(root, encoding="unicode")
    observation = observe_hwpx_section(xml, section=section, section_ordinal=0)
    contexts = build_text_contexts(root, section)
    return tuple(
        _classify_node(node, context, rules)
        for node, context in zip(observation.nodes, contexts, strict=True)
    )


def _classify_node(
    node: TextObservation, context: TextContext, rules: SeparationRules
) -> SemanticNodeDecision:
    span = detect_marker_span_candidate(node.raw_body)
    legacy_role, legacy_reasons = rules.semantic_role_for(context.location)

    if legacy_role is SemanticRole.AMBIGUOUS:
        return _decision(node, context, SemanticRole.AMBIGUOUS, ("legacy_rule_conflict",), legacy_reasons)
    if legacy_role is not None:
        # 사람이 선언한 --rules가 전체 노드 의미를 확정한다. 이 경우 표식 경계
        # 후보가 있어도 같은 노드를 표식/콘텐츠로 쪼개지 않는다.
        return _decision(node, context, legacy_role, ("legacy_rule_override",), legacy_reasons)

    if node.table_depth > 1:
        return _decision(
            node, context, SemanticRole.AMBIGUOUS, ("nested_table",), ("table_depth_gt_1",)
        )
    if node.table_index is not None and not node.cell_address_known:
        return _decision(
            node,
            context,
            SemanticRole.AMBIGUOUS,
            ("missing_cell_address",),
            ("table_cell_without_address",),
        )

    if not node.logical_text.strip():
        return _decision(
            node, context, SemanticRole.FIXED, ("empty_scaffolding",), ("empty_normalized_text",)
        )

    if span is not None:
        # 경계 후보만으로는 의미가 아니다. 독립적인 콘텐츠/고정 근거가 없으면
        # 사람이 --rules resolutions로 해결할 때까지 AMBIGUOUS로 남긴다. span은
        # 유지해, 사람이 marker_content로 확정하면 같은 span을 그대로 승격한다.
        return _decision(
            node,
            context,
            SemanticRole.AMBIGUOUS,
            ("marker_boundary_without_independent_evidence",),
            (f"marker_span_candidate:{span.marker_prefix_raw!r}",),
            span=span,
        )

    fallback_role = classify_text(context, rules)
    match fallback_role:
        case TextRole.CONTENT:
            return _decision(
                node, context, SemanticRole.CONTENT, ("structural_content_default",), ("structural_classifier",)
            )
        case TextRole.FIXED_LABEL | TextRole.FIXED_TEXT:
            return _decision(
                node, context, SemanticRole.FIXED, ("structural_fixed_pattern",), ("structural_classifier",)
            )


def _decision(
    node: TextObservation,
    context: TextContext,
    role: SemanticRole,
    reason_codes: tuple[str, ...],
    evidence: tuple[str, ...],
    *,
    span: LosslessTextSpan | None = None,
) -> SemanticNodeDecision:
    return SemanticNodeDecision(
        role=role,
        source_sha256=node.source_sha256,
        text_sha256=node.text_sha256,
        location=context.location,
        reason_codes=reason_codes,
        evidence=evidence,
        span=span,
    )


def _layout_prefix_end(raw_body: str) -> int:
    cursor = 0
    fwspace_re = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?fwSpace\b[^>]*/>")
    while cursor < len(raw_body):
        if raw_body[cursor] == " ":
            cursor += 1
            continue
        match = fwspace_re.match(raw_body, cursor)
        if match:
            cursor = match.end()
            continue
        break
    return cursor


def _is_marker_symbol(char: str) -> bool:
    return unicodedata.category(char).startswith(("P", "S")) and char not in _PAIRED_DELIMITERS
