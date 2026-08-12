from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from core.adapters.hwpx_alias_map import AliasMap, RepeatBlock

from .hwpx_semantic_contract import SemanticRegionAnnotation
from .hwpx_separation_rules import TextLocation


_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")


class SemanticRepeatProjectionError(ValueError):
    """Raised when a validated repeat declaration lacks source-backed locations."""


@dataclass(frozen=True, slots=True)
class FieldSourceLocation:
    field_id: str
    location: TextLocation

    def __post_init__(self) -> None:
        if not self.field_id:
            raise SemanticRepeatProjectionError("field source location requires field_id")


@dataclass(frozen=True, slots=True)
class RepeatSourceLocations:
    source_sha256: str
    fields: tuple[FieldSourceLocation, ...]

    def __post_init__(self) -> None:
        if _SHA256_RE.fullmatch(self.source_sha256) is None:
            raise SemanticRepeatProjectionError(
                "repeat source locations require a lowercase SHA-256 digest"
            )
        field_ids = tuple(item.field_id for item in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise SemanticRepeatProjectionError(
                "repeat source locations contain duplicate field identities"
            )

    def by_field_id(self) -> dict[str, TextLocation]:
        return {item.field_id: item.location for item in self.fields}


def project_repeat_group_annotations(
    alias_map: AliasMap,
    source_locations: RepeatSourceLocations,
) -> tuple[SemanticRegionAnnotation, ...]:
    """Project only existing validated repeat declarations as semantic regions."""
    locations_by_field = source_locations.by_field_id()
    annotations: list[SemanticRegionAnnotation] = []
    for name, block in sorted(alias_map.blocks.items()):
        field_ids = {block.anchor}
        field_ids.update(field_id for field_id, _ in block.levels.values())
        locations = tuple(
            _required_source_location(name, field_id, locations_by_field)
            for field_id in sorted(field_ids)
        )
        section = _shared_section(name, locations)
        start = min(location.text_node_index for location in locations)
        end = max(location.text_node_index for location in locations)
        annotations.append(
            SemanticRegionAnnotation(
                source_sha256=source_locations.source_sha256,
                section=section,
                start_text_node_index=start,
                end_text_node_index=end,
                declaration_source=f"human-reviewed:alias_map.blocks:{name}",
                reason_codes=("human_repeat_declaration",),
                evidence=_annotation_evidence(name, block, locations_by_field),
            )
        )
    return tuple(annotations)


def _required_source_location(
    block_name: str,
    field_id: str,
    locations_by_field: dict[str, TextLocation],
) -> TextLocation:
    location = locations_by_field.get(field_id)
    if location is None:
        raise SemanticRepeatProjectionError(
            f"repeat block {block_name!r} is missing source location for {field_id!r}"
        )
    _validate_location(block_name, field_id, location)
    return location


def _validate_location(
    block_name: str,
    field_id: str,
    location: TextLocation,
) -> None:
    coordinates = (location.table, location.row, location.col)
    has_complete_cell = all(value is not None for value in coordinates)
    has_partial_cell = any(value is not None for value in coordinates)
    has_paragraph = location.paragraph_index is not None
    if (
        not location.section
        or location.text_node_index < 0
        or (has_partial_cell and not has_complete_cell)
        or not has_paragraph and not has_complete_cell
    ):
        raise SemanticRepeatProjectionError(
            f"repeat block {block_name!r} has invalid source location for {field_id!r}"
        )
    values = (location.text_node_index, *coordinates, location.paragraph_index)
    if any(value is not None and value < 0 for value in values):
        raise SemanticRepeatProjectionError(
            f"repeat block {block_name!r} has invalid source location for {field_id!r}"
        )


def _shared_section(block_name: str, locations: tuple[TextLocation, ...]) -> str:
    sections = {location.section for location in locations}
    if len(sections) != 1:
        raise SemanticRepeatProjectionError(
            f"repeat block {block_name!r} spans multiple source sections"
        )
    return next(iter(sections))


def _annotation_evidence(
    block_name: str,
    block: RepeatBlock,
    locations_by_field: dict[str, TextLocation],
) -> tuple[str, ...]:
    fields = {block.anchor}
    fields.update(field_id for field_id, _ in block.levels.values())
    evidence = [f"anchor:{block.anchor}"]
    evidence.extend(
        f"level:{level}:{field_id}"
        for level, (field_id, _) in sorted(block.levels.items())
    )
    evidence.extend(
        f"item_separator_level:{level}" for level in block.item_separator_levels
    )
    if block.section_transition is not None:
        evidence.append(
            "section_transition:"
            f"{block.section_transition[0]}:{block.section_transition[1]}"
        )
    evidence.extend(
        _field_location_evidence(field_id, locations_by_field[field_id])
        for field_id in sorted(fields)
    )
    return tuple(evidence)


def _field_location_evidence(field_id: str, location: TextLocation) -> str:
    table = "" if location.table is None else str(location.table)
    row = "" if location.row is None else str(location.row)
    col = "" if location.col is None else str(location.col)
    paragraph = "" if location.paragraph_index is None else str(location.paragraph_index)
    return (
        f"field_location:{field_id}:{location.section}:text={location.text_node_index}"
        f":table={table}:row={row}:col={col}:paragraph={paragraph}"
    )
