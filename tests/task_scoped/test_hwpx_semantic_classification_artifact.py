from __future__ import annotations

import json
from pathlib import Path

from core.templates.hwpx_content_artifacts import (
    mark_ambiguous_content_separation,
    render_ambiguous_review,
    write_semantic_classification,
)
from core.templates.hwpx_semantic_contract import SemanticNodeDecision, SemanticRole
from core.templates.hwpx_separation_rules import TextLocation


_SHA = "b" * 64


def _decision(role: SemanticRole, index: int) -> SemanticNodeDecision:
    return SemanticNodeDecision(
        role=role,
        source_sha256=_SHA,
        text_sha256=_SHA,
        location=TextLocation(section="section0.xml", text_node_index=index, table=None, row=None, col=None),
        reason_codes=("reason",),
        evidence=("evidence",),
    )


def test_write_semantic_classification_is_byte_identical_for_same_inputs(tmp_path: Path) -> None:
    decisions = (_decision(SemanticRole.FIXED, 0), _decision(SemanticRole.AMBIGUOUS, 1))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_semantic_classification(first, source_sha256=_SHA, decisions=decisions)
    write_semantic_classification(second, source_sha256=_SHA, decisions=decisions)

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["taxonomy_version"] == "semantic-v1"
    assert payload["unresolved_count"] == 1
    assert payload["role_counts"] == {"ambiguous": 1, "fixed": 1}
    assert len(payload["node_decisions"]) == 2
    assert payload["region_annotations"] == []


def test_mark_ambiguous_content_separation_sets_semantic_status(tmp_path: Path) -> None:
    template_json = tmp_path / "template.json"
    template_json.write_text(json.dumps({"status": "candidate"}), encoding="utf-8")
    semantic_path = tmp_path / "semantic_classification.json"
    semantic_path.write_text("{}", encoding="utf-8")
    review_path = tmp_path / "template.review.md"
    review_path.write_text("review", encoding="utf-8")

    mark_ambiguous_content_separation(
        template_json,
        semantic_classification=semantic_path,
        review=review_path,
        unresolved_count=2,
    )

    data = json.loads(template_json.read_text(encoding="utf-8"))
    assert data["content_separation"]["semantic_status"] == "ambiguous"
    assert data["content_separation"]["unresolved_count"] == 2
    assert data["status"] == "candidate"


def test_render_ambiguous_review_lists_each_unresolved_decision() -> None:
    unresolved = [
        {
            "decision_id": "semantic-v1:text_node:abc",
            "section": "section0.xml",
            "text_node_index": 3,
            "table": None,
            "row": None,
            "col": None,
            "reason_codes": ("marker_boundary_without_independent_evidence",),
        }
    ]

    review = render_ambiguous_review("demo", unresolved)

    assert "ambiguous" in review
    assert "semantic-v1:text_node:abc" in review
    assert "text_node_index=3" in review
