from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.templates.hwpx_semantic_classifier import detect_marker_span_candidate
from core.templates.hwpx_semantic_contract import SemanticNodeDecision, SemanticRole
from core.templates.hwpx_semantic_resolutions import (
    ResolutionError,
    apply_resolutions,
    load_resolutions,
    unresolved_skeleton,
)
from core.templates.hwpx_separation_rules import TextLocation


_SHA = "a" * 64


def _location(index: int = 0) -> TextLocation:
    return TextLocation(section="section0.xml", text_node_index=index, table=None, row=None, col=None)


def _ambiguous(index: int = 0, span=None) -> SemanticNodeDecision:
    return SemanticNodeDecision(
        role=SemanticRole.AMBIGUOUS,
        source_sha256=_SHA,
        text_sha256=_SHA,
        location=_location(index),
        reason_codes=("marker_boundary_without_independent_evidence",),
        evidence=("test_evidence",),
        span=span,
    )


def test_load_resolutions_parses_content_role(tmp_path: Path) -> None:
    (ambiguous,) = (_ambiguous(),)
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "resolutions": [
                    {
                        "decision_id": ambiguous.decision_id,
                        "source_sha256": _SHA,
                        "text_sha256": _SHA,
                        "role": "content",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (resolution,) = load_resolutions(path)

    assert resolution.decision_id == ambiguous.decision_id
    assert resolution.role == "content"


def test_load_resolutions_rejects_conflicting_duplicate_target(tmp_path: Path) -> None:
    ambiguous = _ambiguous()
    path = tmp_path / "rules.json"
    entry = {
        "decision_id": ambiguous.decision_id,
        "source_sha256": _SHA,
        "text_sha256": _SHA,
        "role": "content",
    }
    path.write_text(json.dumps({"resolutions": [entry, entry]}), encoding="utf-8")

    with pytest.raises(ResolutionError, match="conflicting"):
        load_resolutions(path)


def test_apply_resolutions_promotes_content_role() -> None:
    ambiguous = _ambiguous()
    resolutions = tuple(
        load_resolutions_from_dict(
            [
                {
                    "decision_id": ambiguous.decision_id,
                    "source_sha256": _SHA,
                    "text_sha256": _SHA,
                    "role": "content",
                }
            ]
        )
    )

    (resolved,) = apply_resolutions((ambiguous,), resolutions)

    assert resolved.role is SemanticRole.CONTENT
    assert "human_resolution_applied" in resolved.reason_codes


def test_apply_resolutions_promotes_marker_content_with_matching_span() -> None:
    span = detect_marker_span_candidate("- 부제 -")
    assert span is not None
    ambiguous = _ambiguous(span=span)
    resolutions = tuple(
        load_resolutions_from_dict(
            [
                {
                    "decision_id": ambiguous.decision_id,
                    "source_sha256": _SHA,
                    "text_sha256": _SHA,
                    "role": "marker_content",
                    "marker_prefix_raw": span.marker_prefix_raw,
                    "marker_suffix_raw": span.marker_suffix_raw,
                }
            ]
        )
    )

    (resolved,) = apply_resolutions((ambiguous,), resolutions)

    assert resolved.role is SemanticRole.MARKER_CONTENT
    assert resolved.span is span


def test_apply_resolutions_rejects_stale_marker_span() -> None:
    span = detect_marker_span_candidate("- 부제 -")
    assert span is not None
    ambiguous = _ambiguous(span=span)
    resolutions = tuple(
        load_resolutions_from_dict(
            [
                {
                    "decision_id": ambiguous.decision_id,
                    "source_sha256": _SHA,
                    "text_sha256": _SHA,
                    "role": "marker_content",
                    "marker_prefix_raw": "stale ",
                    "marker_suffix_raw": " stale",
                }
            ]
        )
    )

    with pytest.raises(ResolutionError, match="stale"):
        apply_resolutions((ambiguous,), resolutions)


def test_apply_resolutions_rejects_unknown_decision_id() -> None:
    ambiguous = _ambiguous()
    resolutions = tuple(
        load_resolutions_from_dict(
            [
                {
                    "decision_id": "semantic-v1:text_node:" + "0" * 64,
                    "source_sha256": _SHA,
                    "text_sha256": _SHA,
                    "role": "content",
                }
            ]
        )
    )

    with pytest.raises(ResolutionError, match="unknown decision_id"):
        apply_resolutions((ambiguous,), resolutions)


def test_apply_resolutions_rejects_already_resolved_target() -> None:
    resolved_decision = SemanticNodeDecision(
        role=SemanticRole.CONTENT,
        source_sha256=_SHA,
        text_sha256=_SHA,
        location=_location(),
        reason_codes=("structural_content_default",),
        evidence=("structural_classifier",),
    )
    resolutions = tuple(
        load_resolutions_from_dict(
            [
                {
                    "decision_id": resolved_decision.decision_id,
                    "source_sha256": _SHA,
                    "text_sha256": _SHA,
                    "role": "content",
                }
            ]
        )
    )

    with pytest.raises(ResolutionError, match="not \\(or no longer\\) AMBIGUOUS"):
        apply_resolutions((resolved_decision,), resolutions)


def test_unresolved_skeleton_lists_only_ambiguous_decisions_with_role_unset() -> None:
    ambiguous = _ambiguous()
    resolved_decision = SemanticNodeDecision(
        role=SemanticRole.FIXED,
        source_sha256=_SHA,
        text_sha256=_SHA,
        location=_location(1),
        reason_codes=("empty_scaffolding",),
        evidence=("empty_normalized_text",),
    )

    (entry,) = unresolved_skeleton((ambiguous, resolved_decision))

    assert entry["decision_id"] == ambiguous.decision_id
    assert entry["role"] is None
    assert entry["marker_prefix_raw"] is None


def load_resolutions_from_dict(entries: list[dict], tmp_path: Path | None = None):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rules.json"
        path.write_text(json.dumps({"resolutions": entries}), encoding="utf-8")
        return load_resolutions(path)
