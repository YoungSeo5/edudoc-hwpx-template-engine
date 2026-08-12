from __future__ import annotations

import pytest

from core.templates.hwpx_semantic_classifier import (
    SemanticAmbiguityError,
    detect_marker_span_candidate,
)
from core.templates.hwpx_semantic_contract import SemanticNodeDecision, SemanticRole
from core.templates.hwpx_semantic_placeholder_projection import (
    MarkerSpanDriftError,
    patch_marker_content_span,
    require_fully_resolved,
)
from core.templates.hwpx_separation_rules import TextLocation


_SHA = "a" * 64


def _location(index: int = 0) -> TextLocation:
    return TextLocation(section="section0.xml", text_node_index=index, table=None, row=None, col=None)


def _decision(role: SemanticRole, span=None, index: int = 0) -> SemanticNodeDecision:
    return SemanticNodeDecision(
        role=role,
        source_sha256=_SHA,
        text_sha256=_SHA,
        location=_location(index),
        reason_codes=("test_reason",),
        evidence=("test_evidence",),
        span=span,
    )


def test_require_fully_resolved_passes_with_no_ambiguous_decisions() -> None:
    decisions = (_decision(SemanticRole.FIXED), _decision(SemanticRole.CONTENT, index=1))
    require_fully_resolved(decisions)  # must not raise


def test_require_fully_resolved_raises_with_ambiguous_location_detail() -> None:
    decisions = (_decision(SemanticRole.FIXED), _decision(SemanticRole.AMBIGUOUS, index=1))

    with pytest.raises(SemanticAmbiguityError, match="text_node_index=1"):
        require_fully_resolved(decisions)


def test_patch_marker_content_span_reconstructs_body_with_placeholder() -> None:
    span = detect_marker_span_candidate("- 부제 -")
    assert span is not None
    decision = _decision(SemanticRole.MARKER_CONTENT, span=span)

    patched = patch_marker_content_span("- 부제 -", decision, "{{content_01}}")

    assert patched == "- {{content_01}} -"


def test_patch_marker_content_span_rejects_drifted_raw_body() -> None:
    span = detect_marker_span_candidate("- 부제 -")
    assert span is not None
    decision = _decision(SemanticRole.MARKER_CONTENT, span=span)

    with pytest.raises(MarkerSpanDriftError):
        patch_marker_content_span("- 다른 텍스트 -", decision, "{{content_01}}")


def test_patch_marker_content_span_rejects_non_marker_content_decision() -> None:
    decision = _decision(SemanticRole.CONTENT)

    with pytest.raises(ValueError, match="MARKER_CONTENT"):
        patch_marker_content_span("아무 텍스트", decision, "{{content_01}}")
