from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from .hwpx_raw_text_observations import decode_raw_body, edge_counts, lexical_shape
from .hwpx_structural_observation_models import (
    CellSignature,
    DocumentObservation,
    PeerStructure,
    RowSignature,
    TableObservation,
    TextObservation,
)

_T_NODE_RE: Final = re.compile(
    r"<(?:[A-Za-z_][\w.-]*:)?t\b[^>]*/>|"
    r"<(?:[A-Za-z_][\w.-]*:)?t\b[^>]*>(.*?)</(?:[A-Za-z_][\w.-]*:)?t>",
    re.S,
)


@dataclass(frozen=True, slots=True)
class ObservationIndex:
    parents: dict[ET.Element, ET.Element]
    nodes: tuple[TextObservation, ...]
    text_indexes: dict[int, int]


def observe_hwpx_section(
    xml: str | bytes, *, section: str, section_ordinal: int
) -> DocumentObservation:
    source_bytes = xml if isinstance(xml, bytes) else xml.encode("utf-8")
    raw = source_bytes.decode("utf-8")
    source_sha = sha256(source_bytes).hexdigest()
    root = ET.fromstring(raw)
    parents = {child: parent for parent in root.iter() for child in parent}
    text_nodes = _nodes(root, "t")
    raw_bodies = tuple(match.group(1) or "" for match in _T_NODE_RE.finditer(raw))
    if len(raw_bodies) != len(text_nodes):
        msg = "raw hp:t scan did not match parsed text-node count"
        raise ValueError(msg)
    paragraphs, runs, tables = (_nodes(root, name) for name in ("p", "run", "tbl"))
    paragraph_indexes = {id(node): index for index, node in enumerate(paragraphs)}
    run_indexes = {id(node): index for index, node in enumerate(runs)}
    table_indexes = {id(node): index for index, node in enumerate(tables)}
    text_indexes = {id(node): index for index, node in enumerate(text_nodes)}
    cell_nodes = {
        id(cell): tuple(
            text_indexes[id(node)]
            for node in text_nodes
            if _nearest(node, parents, "tc") is cell
        )
        for cell in _nodes(root, "tc")
    }
    adjacency = _paragraph_adjacency(text_nodes, parents, text_indexes)
    observations: list[TextObservation] = []
    for index, (node, raw_body) in enumerate(zip(text_nodes, raw_bodies, strict=True)):
        paragraph = _nearest(node, parents, "p")
        run = _nearest(node, parents, "run")
        table = _nearest(node, parents, "tbl")
        cell = _nearest(node, parents, "tc")
        logical, offsets = decode_raw_body(raw_body)
        original = "".join(node.itertext())
        row, col = _cell_address(cell)
        span = _child(cell, "cellSpan")
        leading_ascii, trailing_ascii, leading_fw, trailing_fw = edge_counts(raw_body)
        text_sha = sha256(raw_body.encode("utf-8")).hexdigest()
        identity = f"{source_sha}:{section}:{section_ordinal}:{index}:{text_sha}"
        observations.append(
            TextObservation(
                observation_id=f"structural-v1:text:{sha256(identity.encode()).hexdigest()}",
                source_sha256=source_sha,
                text_sha256=text_sha,
                section=section,
                section_ordinal=section_ordinal,
                text_node_index=index,
                original_text=original,
                normalized_text=_normalize(original),
                logical_text=logical,
                raw_body=raw_body,
                decoded_to_raw_offsets=offsets,
                paragraph_index=_index_of(paragraph, paragraph_indexes),
                run_index=_index_of(run, run_indexes),
                paragraph_text_node_index=_local_index(node, paragraph, "t"),
                run_text_node_index=_local_index(node, run, "t"),
                previous_nonempty_text_node_index=adjacency[index][0],
                next_nonempty_text_node_index=adjacency[index][1],
                table_index=_index_of(table, table_indexes),
                table_depth=_ancestor_count(node, parents, "tbl"),
                row=row,
                col=col,
                cell_address_known=row is not None and col is not None,
                declared_row_count=_int_attr(table, "rowCnt"),
                declared_column_count=_int_attr(table, "colCnt"),
                row_span=_int_attr(span, "rowSpan"),
                column_span=_int_attr(span, "colSpan"),
                cell_text_node_indexes=cell_nodes.get(id(cell), ()) if cell is not None else (),
                paragraph_id=_attr(paragraph, "id"),
                paragraph_style_ref=_attr(paragraph, "paraPrIDRef"),
                paragraph_layout_ref=_attr(paragraph, "styleIDRef"),
                character_style_ref=_attr(run, "charPrIDRef"),
                table_border_fill_ref=_attr(table, "borderFillIDRef"),
                cell_border_fill_ref=_attr(cell, "borderFillIDRef"),
                paragraph_start=_local_index(node, paragraph, "t") == 0,
                leading_ascii_space_count=leading_ascii,
                trailing_ascii_space_count=trailing_ascii,
                leading_fwspace_count=leading_fw,
                trailing_fwspace_count=trailing_fw,
            )
        )
    frozen_nodes = tuple(observations)
    observation_index = ObservationIndex(parents, frozen_nodes, text_indexes)
    return DocumentObservation(
        source_sha256=source_sha,
        section=section,
        section_ordinal=section_ordinal,
        nodes=frozen_nodes,
        tables=tuple(
            _observe_table(
                table,
                table_indexes[id(table)],
                observation_index,
            )
            for table in tables
        ),
    )


def _observe_table(
    table: ET.Element,
    table_index: int,
    observation_index: ObservationIndex,
) -> TableObservation:
    rows = tuple(
        _row_signature(row, index, observation_index)
        for index, row in enumerate(_children(table, "tr"))
    )
    peers = tuple(_peer_structure(first, second) for first, second in zip(rows, rows[1:]))
    return TableObservation(
        table_index=table_index,
        table_depth=_ancestor_count(table, observation_index.parents, "tbl") + 1,
        declared_row_count=_int_attr(table, "rowCnt"),
        declared_column_count=_int_attr(table, "colCnt"),
        border_fill_ref=_attr(table, "borderFillIDRef"),
        row_signatures=rows,
        peer_structures=peers,
    )


def _row_signature(
    row: ET.Element,
    row_index: int,
    observation_index: ObservationIndex,
) -> RowSignature:
    cells: list[CellSignature] = []
    for cell in _children(row, "tc"):
        _, col = _cell_address(cell)
        if col is None:
            continue
        indexes = {
            observation_index.text_indexes[id(node)]
            for node in _nodes(cell, "t")
            if _nearest(node, observation_index.parents, "tc") is cell
        }
        cell_nodes = tuple(
            item for item in observation_index.nodes if item.text_node_index in indexes
        )
        refs = tuple(
            f"{item.paragraph_style_ref}|{item.paragraph_layout_ref}|{item.character_style_ref}|{item.cell_border_fill_ref}"
            for item in cell_nodes
        )
        cells.append(
            CellSignature(
                column=col,
                row_span=_int_attr(_child(cell, "cellSpan"), "rowSpan") or 1,
                column_span=_int_attr(_child(cell, "cellSpan"), "colSpan") or 1,
                text_node_count=len(cell_nodes),
                style_layout_ids=refs,
                lexical_shapes=tuple(lexical_shape(item.logical_text) for item in cell_nodes),
            )
        )
    cells.sort(key=lambda item: item.column)
    return RowSignature(row_index, tuple(item.column for item in cells), tuple(cells))


def _peer_structure(first: RowSignature, second: RowSignature) -> PeerStructure:
    left = {cell.column: cell for cell in first.cells if cell.row_span == cell.column_span == 1}
    right = {cell.column: cell for cell in second.cells if cell.row_span == cell.column_span == 1}
    columns = tuple(sorted(left.keys() & right.keys()))
    matching = tuple(col for col in columns if left[col] == right[col])
    return PeerStructure(first.row_index, second.row_index, columns, matching, tuple(col for col in columns if col not in matching))


def _paragraph_adjacency(
    text_nodes: list[ET.Element],
    parents: dict[ET.Element, ET.Element],
    text_indexes: dict[int, int],
) -> dict[int, tuple[int | None, int | None]]:
    result: dict[int, tuple[int | None, int | None]] = {}
    groups: dict[int, list[ET.Element]] = {}
    for node in text_nodes:
        paragraph = _nearest(node, parents, "p")
        groups.setdefault(id(paragraph), []).append(node)
    for group in groups.values():
        indexes = [text_indexes[id(node)] for node in group]
        nonempty = [
            text_indexes[id(node)]
            for node in group
            if _normalize("".join(node.itertext()))
        ]
        for index in indexes:
            previous = next((item for item in reversed(nonempty) if item < index), None)
            following = next((item for item in nonempty if item > index), None)
            result[index] = (previous, following)
    return result


def _nearest(node: ET.Element, parents: dict[ET.Element, ET.Element], name: str) -> ET.Element | None:
    current = node
    while current in parents:
        current = parents[current]
        if _local_name(current.tag) == name:
            return current
    return None


def _ancestor_count(node: ET.Element, parents: dict[ET.Element, ET.Element], name: str) -> int:
    count = 0
    current = node
    while current in parents:
        current = parents[current]
        count += _local_name(current.tag) == name
    return count


def _cell_address(cell: ET.Element | None) -> tuple[int | None, int | None]:
    address = _child(cell, "cellAddr")
    row, col = _int_attr(address, "rowAddr"), _int_attr(address, "colAddr")
    return (row, col) if row is not None and col is not None else (None, None)


def _local_index(node: ET.Element, parent: ET.Element | None, name: str) -> int | None:
    return _nodes(parent, name).index(node) if parent is not None else None


def _index_of(node: ET.Element | None, indexes: dict[int, int]) -> int | None:
    return indexes.get(id(node)) if node is not None else None


def _attr(node: ET.Element | None, name: str) -> str | None:
    return next((value for key, value in node.attrib.items() if _local_name(key) == name), None) if node is not None else None


def _int_attr(node: ET.Element | None, name: str) -> int | None:
    value = _attr(node, name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _child(node: ET.Element | None, name: str) -> ET.Element | None:
    return next((child for child in node if _local_name(child.tag) == name), None) if node is not None else None


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in node if _local_name(child.tag) == name]


def _nodes(node: ET.Element | None, name: str) -> list[ET.Element]:
    return [item for item in node.iter() if _local_name(item.tag) == name] if node is not None else []


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _normalize(value: str) -> str:
    return " ".join(value.split())
