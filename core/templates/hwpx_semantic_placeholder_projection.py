from __future__ import annotations

import html
from dataclasses import dataclass

from .hwpx_semantic_classifier import SemanticAmbiguityError
from .hwpx_semantic_contract import SemanticNodeDecision, SemanticRole

# 이 모듈의 경계:
# 문서 전체의 SemanticNodeDecision을 입력받아, 모두 해소됐을 때만
# placeholder 반영을 허용한다. FIXED는 절대 건드리지 않고, MARKER_CONTENT는
# 같은 노드의 raw 본문에서 content_raw span만 치환한다. 하나라도 AMBIGUOUS면
# 아무 것도 쓰지 않고 실패를 보고한다.


@dataclass(frozen=True, slots=True)
class AmbiguousDecisionReport:
    section: str
    text_node_index: int
    table: int | None
    row: int | None
    col: int | None
    reason_codes: tuple[str, ...]
    evidence: tuple[str, ...]


class MarkerSpanDriftError(ValueError):
    """Raised when the current raw body no longer matches the recorded span."""


def require_fully_resolved(
    decisions: tuple[SemanticNodeDecision, ...],
) -> None:
    """All-or-nothing gate: raise if any decision is still AMBIGUOUS."""
    ambiguous = [item for item in decisions if item.role is SemanticRole.AMBIGUOUS]
    if not ambiguous:
        return
    reports = tuple(
        AmbiguousDecisionReport(
            section=item.location.section,
            text_node_index=item.location.text_node_index,
            table=item.location.table,
            row=item.location.row,
            col=item.location.col,
            reason_codes=item.reason_codes,
            evidence=item.evidence,
        )
        for item in ambiguous
    )
    detail = "; ".join(
        f"section={r.section} text_node_index={r.text_node_index} "
        f"table={r.table} row={r.row} col={r.col} reasons={list(r.reason_codes)}"
        for r in reports
    )
    raise SemanticAmbiguityError(
        f"{len(reports)} text node(s) remain semantically ambiguous: {detail}"
    )


def patch_marker_content_span(current_raw_body: str, decision: SemanticNodeDecision, placeholder: str) -> str:
    """Replace only the content span of a MARKER_CONTENT node, keeping the marker.

    Reconstructs: layout_prefix_raw + marker_prefix_raw + escaped placeholder + marker_suffix_raw.
    Raw offsets are re-verified against ``current_raw_body`` immediately before
    patching; drift raises instead of silently patching the wrong bytes.
    """
    if decision.role is not SemanticRole.MARKER_CONTENT:
        raise ValueError("patch_marker_content_span requires a MARKER_CONTENT decision")
    span = decision.span
    if span is None:
        raise ValueError("MARKER_CONTENT decision is missing its lossless span")
    if current_raw_body != span.raw_body:
        raise MarkerSpanDriftError(
            "recorded lossless span no longer matches the current raw body"
        )
    return "".join(
        (
            span.layout_prefix_raw,
            span.marker_prefix_raw,
            html.escape(placeholder, quote=False),
            span.marker_suffix_raw,
        )
    )
