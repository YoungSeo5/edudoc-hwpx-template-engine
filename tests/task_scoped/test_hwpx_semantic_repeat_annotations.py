from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from core.adapters.hwpx_alias_map import AliasMap, AliasMapError, load_alias_map
from core.adapters.hwpx_template_input import ResolvedRenderPlan
from core.adapters.hwpx_template_renderer import render_repeat_block
from core.templates.hwpx_semantic_contract import SemanticReport
from core.templates.hwpx_semantic_regions import (
    FieldSourceLocation,
    RepeatSourceLocations,
    SemanticRepeatProjectionError,
    project_repeat_group_annotations,
)
from core.templates.hwpx_separation_rules import TextLocation


def _load_valid_repeat_alias_map(tmp_path: Path):
    (tmp_path / "alias_map.json").write_text(
        json.dumps(
            {
                "template_id": "repeat-annotation-fixture",
                "fields": {},
                "blocks": {
                    "body": {
                        "anchor": "body_anchor_01",
                        "repeat": True,
                        "table_scope": False,
                        "levels": {
                            "0": {"field": "body_anchor_01", "prefix": ""},
                            "1": {"field": "body_detail_01", "prefix": "- "},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    alias_map = load_alias_map(
        tmp_path,
        field_ids=frozenset({"body_anchor_01", "body_detail_01"}),
        template_id="repeat-annotation-fixture",
    )
    assert alias_map is not None
    return alias_map


def _source_locations(*, source: bytes = b"current-source") -> RepeatSourceLocations:
    return RepeatSourceLocations(
        source_sha256=sha256(source).hexdigest(),
        fields=(
            FieldSourceLocation(
                field_id="body_anchor_01",
                location=TextLocation(
                    section="Contents/section0.xml",
                    text_node_index=7,
                    table=None,
                    row=None,
                    col=None,
                    paragraph_index=7,
                ),
            ),
            FieldSourceLocation(
                field_id="body_detail_01",
                location=TextLocation(
                    section="Contents/section0.xml",
                    text_node_index=12,
                    table=1,
                    row=2,
                    col=3,
                    paragraph_index=4,
                ),
            ),
        ),
    )


def test_repeat_execution_uses_only_validated_alias_map_blocks(tmp_path: Path) -> None:
    # Given: a human-declared repeat block accepted by the existing alias parser.
    alias_map = _load_valid_repeat_alias_map(tmp_path)
    xml = (
        "<hp:p><hp:t>{{body_anchor_01}}</hp:t></hp:p>"
        "<hp:p><hp:t>{{body_detail_01}}</hp:t></hp:p>"
    )
    items = {"body_anchor_01": [[0, "Heading"], [1, "Detail"]]}

    # When: the existing renderer receives the parsed block declarations.
    rendered, filled, _ = render_repeat_block(xml, items, alias_map.blocks)

    # Then: repeat expansion comes from the validated declarations, not geometry.
    assert rendered == (
        "<hp:p><hp:t>Heading</hp:t></hp:p>"
        "<hp:p><hp:t>- Detail</hp:t></hp:p>"
    )
    assert filled == {"body_anchor_01", "body_detail_01"}


def test_repeat_group_annotation_projects_one_validated_human_block(
    tmp_path: Path,
) -> None:
    # Given: one existing parser-validated human repeat declaration and its source fields.
    alias_map = _load_valid_repeat_alias_map(tmp_path)

    # When: the declaration is projected into the non-replacement semantic view.
    annotations = project_repeat_group_annotations(alias_map, _source_locations())

    # Then: it produces one region bounded by the declared field locations.
    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.role == "repeat_group"
    assert annotation.declaration_source == "human-reviewed:alias_map.blocks:body"
    assert (
        annotation.section,
        annotation.start_text_node_index,
        annotation.end_text_node_index,
    ) == ("Contents/section0.xml", 7, 12)
    assert annotation.reason_codes == ("human_repeat_declaration",)
    assert "anchor:body_anchor_01" in annotation.evidence
    assert "level:0:body_anchor_01" in annotation.evidence
    assert "level:1:body_detail_01" in annotation.evidence


def test_repeat_looking_source_without_blocks_emits_no_repeat_annotation() -> None:
    # Given: source locations that look structurally repeated but have no declaration.
    alias_map = AliasMap(template_id="no-repeat", aliases={})

    # When: the semantic projection receives the empty parser-validated blocks mapping.
    annotations = project_repeat_group_annotations(alias_map, _source_locations())

    # Then: it cannot infer a repeat region or executable block from geometry.
    assert annotations == ()
    assert alias_map.blocks == {}


def test_invalid_repeat_block_remains_rejected_by_existing_alias_parser(
    tmp_path: Path,
) -> None:
    # Given: a raw declaration whose anchor is not a known placeholder field.
    (tmp_path / "alias_map.json").write_text(
        json.dumps(
            {
                "fields": {},
                "blocks": {
                    "invalid": {
                        "anchor": "missing_anchor",
                        "repeat": True,
                        "table_scope": False,
                        "levels": {
                            "0": {"field": "body_anchor_01", "prefix": ""}
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    # When/Then: validation stops at the established alias-map boundary.
    with pytest.raises(AliasMapError, match="unknown anchor"):
        load_alias_map(tmp_path, field_ids=frozenset({"body_anchor_01"}))


def test_repeat_annotations_do_not_mutate_render_plan_or_renderer_output(
    tmp_path: Path,
) -> None:
    # Given: a resolved repeat plan using the same pre-existing block declaration.
    alias_map = _load_valid_repeat_alias_map(tmp_path)
    block = alias_map.blocks["body"]
    plan = ResolvedRenderPlan(
        field_values={},
        repeat_values={"body_anchor_01": [[0, "Heading"], [1, "Detail"]]},
        repeat_blocks={"body_anchor_01": block},
        fit_constraints={},
    )
    xml = (
        "<hp:p><hp:t>{{body_anchor_01}}</hp:t></hp:p>"
        "<hp:p><hp:t>{{body_detail_01}}</hp:t></hp:p>"
    )
    before = render_repeat_block(xml, plan.repeat_values, plan.repeat_blocks)

    # When: source-backed semantic annotations are projected.
    annotations = project_repeat_group_annotations(alias_map, _source_locations())
    after = render_repeat_block(xml, plan.repeat_values, plan.repeat_blocks)

    # Then: annotations are read-only and leave the executable plan and output intact.
    assert len(annotations) == 1
    assert plan.repeat_blocks == {"body_anchor_01": block}
    assert after == before


def test_projection_rejects_missing_source_field_and_stale_source_identity(
    tmp_path: Path,
) -> None:
    # Given: one declared field has no source location and an old source is later reported.
    alias_map = _load_valid_repeat_alias_map(tmp_path)
    incomplete = RepeatSourceLocations(
        source_sha256=sha256(b"current-source").hexdigest(),
        fields=_source_locations().fields[:1],
    )
    stale_annotations = project_repeat_group_annotations(
        alias_map,
        _source_locations(source=b"old-source"),
    )

    # When/Then: missing identities are rejected and stale annotations cannot enter a report.
    with pytest.raises(SemanticRepeatProjectionError, match="missing source location"):
        project_repeat_group_annotations(alias_map, incomplete)
    with pytest.raises(ValueError, match="source identity"):
        SemanticReport(
            source_sha256=sha256(b"current-source").hexdigest(),
            decisions=(),
            regions=stale_annotations,
        )
