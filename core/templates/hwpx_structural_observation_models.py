from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


RawOffset: TypeAlias = tuple[int, int]


@dataclass(frozen=True, slots=True)
class LexicalShape:
    state: str
    character_class_sequence: str
    line_count: int


@dataclass(frozen=True, slots=True)
class CellSignature:
    column: int
    row_span: int
    column_span: int
    text_node_count: int
    style_layout_ids: tuple[str, ...]
    lexical_shapes: tuple[LexicalShape, ...]


@dataclass(frozen=True, slots=True)
class RowSignature:
    row_index: int
    ordered_occupied_columns: tuple[int, ...]
    cells: tuple[CellSignature, ...]


@dataclass(frozen=True, slots=True)
class PeerStructure:
    first_row_index: int
    second_row_index: int
    columns: tuple[int, ...]
    matching_columns: tuple[int, ...]
    mismatching_columns: tuple[int, ...]
    evidence: tuple[str, ...] = ("semantic_repeat_undeclared",)


@dataclass(frozen=True, slots=True)
class TableObservation:
    table_index: int
    table_depth: int
    declared_row_count: int | None
    declared_column_count: int | None
    border_fill_ref: str | None
    row_signatures: tuple[RowSignature, ...]
    peer_structures: tuple[PeerStructure, ...]


@dataclass(frozen=True, slots=True)
class TextObservation:
    observation_id: str
    source_sha256: str
    text_sha256: str
    section: str
    section_ordinal: int
    text_node_index: int
    original_text: str
    normalized_text: str
    logical_text: str
    raw_body: str
    decoded_to_raw_offsets: tuple[RawOffset, ...]
    paragraph_index: int | None
    run_index: int | None
    paragraph_text_node_index: int | None
    run_text_node_index: int | None
    previous_nonempty_text_node_index: int | None
    next_nonempty_text_node_index: int | None
    table_index: int | None
    table_depth: int
    row: int | None
    col: int | None
    cell_address_known: bool
    declared_row_count: int | None
    declared_column_count: int | None
    row_span: int | None
    column_span: int | None
    cell_text_node_indexes: tuple[int, ...]
    paragraph_id: str | None
    paragraph_style_ref: str | None
    paragraph_layout_ref: str | None
    character_style_ref: str | None
    table_border_fill_ref: str | None
    cell_border_fill_ref: str | None
    paragraph_start: bool
    leading_ascii_space_count: int
    trailing_ascii_space_count: int
    leading_fwspace_count: int
    trailing_fwspace_count: int


@dataclass(frozen=True, slots=True)
class DocumentObservation:
    source_sha256: str
    section: str
    section_ordinal: int
    nodes: tuple[TextObservation, ...]
    tables: tuple[TableObservation, ...]
