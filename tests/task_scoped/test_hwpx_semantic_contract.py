from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from core.templates.hwpx_semantic_contract import (
    LosslessTextSpan,
    SemanticNodeDecision,
    SemanticRegionAnnotation,
    SemanticReport,
    SemanticRole,
)
from core.templates.hwpx_separation_rules import (
    TextLocation,
    TextRole,
    load_separation_rules,
)


def _node_decision(
    *,
    source: bytes = b"source-a",
    text: str = "* content",
    text_node_index: int = 2,
) -> SemanticNodeDecision:
    return SemanticNodeDecision(
        role=SemanticRole.MARKER_CONTENT,
        source_sha256=sha256(source).hexdigest(),
        text_sha256=sha256(text.encode("utf-8")).hexdigest(),
        location=TextLocation(
            section="Contents/section0.xml",
            text_node_index=text_node_index,
            table=0,
            row=1,
            col=2,
            paragraph_index=4,
        ),
        reason_codes=("semantic_marker_boundary",),
        evidence=("sha256:marker",),
    )


def test_legacy_text_roles_and_rule_parsing_remain_unchanged(tmp_path) -> None:
    # Given: a legacy content-separation rule file.
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "role": "fixed_label",
                        "section": "Contents/section0.xml",
                        "text_node_index": 7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    # When: the existing parser and lookup contract are used.
    rules = load_separation_rules(rules_path)
    role = rules.role_for(
        TextLocation(
            section="Contents/section0.xml",
            text_node_index=7,
            table=None,
            row=None,
            col=None,
        )
    )

    # Then: legacy role values and resolution are unchanged.
    assert tuple(TextRole) == (
        TextRole.CONTENT,
        TextRole.FIXED_LABEL,
        TextRole.FIXED_TEXT,
    )
    assert role is TextRole.FIXED_LABEL


def test_semantic_roles_are_exhaustive_and_exclude_region_roles() -> None:
    # Given: the semantic-v1 node taxonomy.
    # When: all node role values are enumerated.
    values = tuple(role.value for role in SemanticRole)

    # Then: only placeholder-decision roles are present.
    assert values == ("fixed", "content", "marker_content", "ambiguous")
    assert "repeat_group" not in values


def test_repeat_group_is_a_non_replacement_region_annotation() -> None:
    # Given: a human-declared repeated range.
    annotation = SemanticRegionAnnotation(
        source_sha256=sha256(b"source-a").hexdigest(),
        section="Contents/section0.xml",
        start_text_node_index=8,
        end_text_node_index=12,
        declaration_source="human-review:reviewer-17",
        reason_codes=("human_repeat_declaration",),
        evidence=("sha256:declaration",),
    )

    # When: its scope and role are inspected.
    # Then: it cannot be mistaken for a node replacement decision.
    assert annotation.scope == "region"
    assert annotation.role == "repeat_group"
    assert not isinstance(annotation, SemanticNodeDecision)


def test_lossless_span_preserves_raw_xml_spelling_and_offsets() -> None:
    # Given: one entity-bearing same-node marker/content split.
    raw_body = "\u3000* A&amp;B -"
    span = LosslessTextSpan(
        raw_body=raw_body,
        layout_prefix_raw="\u3000",
        marker_prefix_raw="* ",
        content_raw="A&amp;B",
        marker_suffix_raw=" -",
        content_decoded="A&B",
        layout_prefix_offsets=(0, 1),
        marker_prefix_offsets=(1, 3),
        content_offsets=(3, 10),
        marker_suffix_offsets=(10, 12),
    )

    # When: the raw body is reconstructed.
    reconstructed = span.reconstruct_raw_body()

    # Then: every byte-bearing character and boundary is preserved losslessly.
    assert reconstructed == raw_body
    assert span.content_decoded == "A&B"


@pytest.mark.parametrize(
    ("content_offsets", "content_raw"),
    [((4, 10), "A&amp;B"), ((3, 10), "changed")],
)
def test_lossless_span_rejects_invalid_offsets_or_reconstruction(
    content_offsets: tuple[int, int], content_raw: str
) -> None:
    # Given: offsets or parts that cannot reconstruct the original raw body.
    # When/Then: the malformed span is rejected at construction.
    with pytest.raises(ValueError, match="lossless text span"):
        LosslessTextSpan(
            raw_body="\u3000* A&amp;B -",
            layout_prefix_raw="\u3000",
            marker_prefix_raw="* ",
            content_raw=content_raw,
            marker_suffix_raw=" -",
            content_decoded="A&B",
            layout_prefix_offsets=(0, 1),
            marker_prefix_offsets=(1, 3),
            content_offsets=content_offsets,
            marker_suffix_offsets=(10, 12),
        )


def test_node_decision_is_immutable_and_identity_rejects_stale_text() -> None:
    # Given: decisions for the same location but different source text.
    first = _node_decision(text="first")
    stale = _node_decision(text="second")

    # When/Then: text identity changes the stable ID and decisions are frozen.
    assert first.decision_id != stale.decision_id
    with pytest.raises(FrozenInstanceError):
        setattr(first, "role", SemanticRole.CONTENT)


def test_semantic_report_rejects_decisions_from_a_stale_source() -> None:
    # Given: a decision whose source hash differs from the current document.
    stale = _node_decision(source=b"old-source")

    # When/Then: the canonical report refuses to reuse that stale decision.
    with pytest.raises(ValueError, match="source identity"):
        SemanticReport(
            source_sha256=sha256(b"current-source").hexdigest(),
            decisions=(stale,),
            regions=(),
        )


def test_semantic_report_has_canonical_ordering_and_bytes() -> None:
    # Given: semantically identical reports with shuffled inputs.
    first_node = SemanticNodeDecision(
        role=SemanticRole.MARKER_CONTENT,
        source_sha256=sha256(b"source-a").hexdigest(),
        text_sha256=sha256(b"node-nine").hexdigest(),
        location=TextLocation(
            section="Contents/section0.xml",
            text_node_index=9,
            table=0,
            row=1,
            col=2,
            paragraph_index=4,
        ),
        reason_codes=("reason-z", "reason-a"),
        evidence=("evidence-z", "evidence-a"),
    )
    second_node = _node_decision(text_node_index=2)
    first = SemanticReport(
        source_sha256=sha256(b"source-a").hexdigest(),
        decisions=(first_node, second_node),
        regions=(),
    )
    second = SemanticReport(
        source_sha256=sha256(b"source-a").hexdigest(),
        decisions=(second_node, first_node),
        regions=(),
    )

    # When: both reports are serialized canonically.
    first_bytes = first.canonical_json_bytes()
    second_bytes = second.canonical_json_bytes()
    payload = json.loads(first_bytes)

    # Then: input ordering cannot affect bytes or machine-consumed ordering.
    assert first_bytes == second_bytes
    assert payload["taxonomy_version"] == "semantic-v1"
    assert [item["location"]["text_node_index"] for item in payload["decisions"]] == [2, 9]
    assert payload["decisions"][1]["reason_codes"] == ["reason-a", "reason-z"]
    assert payload["decisions"][1]["evidence"] == ["evidence-a", "evidence-z"]


def test_conflicting_legacy_evidence_becomes_ambiguous(tmp_path) -> None:
    # Given: contradictory legacy override evidence for the same text node.
    rules_path = tmp_path / "conflict.json"
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {"role": "content", "section": "section0.xml", "text_node_index": 3},
                    {"role": "fixed_text", "section": "section0.xml", "text_node_index": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    location = TextLocation("section0.xml", 3, None, None, None)

    # When: the additive semantic view resolves the legacy rules.
    semantic_role, reasons = load_separation_rules(rules_path).semantic_role_for(location)

    # Then: conflict is explicit and retains both machine-readable reasons.
    assert semantic_role is SemanticRole.AMBIGUOUS
    assert reasons == ("legacy_override_content", "legacy_override_fixed_text")
