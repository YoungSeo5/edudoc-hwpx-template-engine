from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Final

from .hwpx_separation_rules import SeparationRules, TextLocation, TextRole
from .hwpx_structural_observations import observe_hwpx_section


COMMON_RULE_SET: Final = "structural-v1"
COMMON_RULE_DESCRIPTIONS: Final = (
    "standalone chapter, clause, item, and bullet markers",
    "short section labels sharing a table with a section marker",
    "single-text table header and first-column row-label cells",
    "short numbered headings outside tables",
)

_DATE_RE = re.compile(r"(?:20\d{2}|'\d{2})[.년]\s*\d{1,2}")
_PHONE_RE = re.compile(r"☎|0\d{1,2}-\d{3,4}-\d{4}|\d{3,4}-\d{4}")
_ROMAN_MARKER_RE = re.compile(r"^[\u2160-\u216f]+[.]$")
_LIST_MARKER_RE = re.compile(r"^(?:\d+|[A-Za-z])[.)]$")
_NUMBERED_HEADING_RE = re.compile(r"^(?:\d+|[A-Za-z])[.)]\s+\S")
_CIRCLED_MARKER_RE = re.compile(r"^[①-⑳]$")
_SAMPLE_SYMBOL_RE = re.compile(r"[◆◇◎☆◈]{2,}")
_STANDALONE_BULLETS: Final = frozenset({"□", "○", "◦", "▪", "※"})


@dataclass(frozen=True, slots=True)
class TextContext:
    original_text: str
    normalized_text: str
    location: TextLocation
    table_rows: int | None
    table_cols: int | None
    cell_text_count: int
    table_nonempty_cell_count: int
    table_has_section_marker: bool


def build_text_contexts(root: ET.Element, section: str) -> list[TextContext]:
    parents = {child: parent for parent in root.iter() for child in parent}
    text_nodes = _nodes(root, "t")
    observations = observe_hwpx_section(
        ET.tostring(root, encoding="unicode"),
        section=section,
        section_ordinal=0,
    ).nodes
    contexts: list[TextContext] = []
    for node, observation in zip(text_nodes, observations, strict=True):
        table = _nearest(node, parents, "tbl")
        cell = _nearest(node, parents, "tc")
        location = TextLocation(
            section=section,
            text_node_index=observation.text_node_index,
            table=observation.table_index,
            row=observation.row,
            col=observation.col,
            paragraph_index=observation.paragraph_index,
        )
        contexts.append(
            TextContext(
                original_text=observation.original_text,
                normalized_text=observation.normalized_text,
                location=location,
                table_rows=observation.declared_row_count,
                table_cols=observation.declared_column_count,
                cell_text_count=_nonempty_text_count(cell),
                table_nonempty_cell_count=_nonempty_cell_count(table),
                table_has_section_marker=_table_has_section_marker(table),
            )
        )
    return contexts


def classify_text(context: TextContext, rules: SeparationRules) -> TextRole:
    configured = rules.role_for(context.location)
    if configured is not None:
        return configured
    if not context.normalized_text:
        return TextRole.FIXED_TEXT
    if _is_fixed_marker(context):
        return TextRole.FIXED_LABEL
    if _is_short_numbered_heading(context):
        return TextRole.FIXED_LABEL
    if _is_marker_companion(context):
        return TextRole.FIXED_LABEL
    if _is_table_header_or_row_label(context):
        return TextRole.FIXED_LABEL
    return TextRole.CONTENT


def content_category(text: str) -> str:
    if not text:
        return "empty"
    if _DATE_RE.search(text):
        return "date"
    if _PHONE_RE.search(text):
        return "contact"
    if "☑" in text or text.count("□") >= 2:
        return "checkbox_line"
    if text.startswith("□"):
        return "body_paragraph"
    if text.startswith("◦"):
        return "body_bullet"
    if text.startswith("*"):
        return "stat_note"
    if text.startswith("†"):
        return "detail_note"
    if text.startswith("⇨"):
        return "conclusion"
    if ("보고" in text or "현황" in text or "계획" in text) and len(text) <= 80:
        return "document_title"
    if text.endswith(("국", "팀", "과")):
        return "department"
    return "content"


def _is_fixed_marker(context: TextContext) -> bool:
    text = context.normalized_text
    if text == "끝.":
        return True
    if _ROMAN_MARKER_RE.fullmatch(text) or _LIST_MARKER_RE.fullmatch(text):
        return True
    if _CIRCLED_MARKER_RE.fullmatch(text) or text in _STANDALONE_BULLETS:
        return True
    if len(text) == 1 and unicodedata.category(text) == "Co":
        return True
    return (
        context.location.table is not None
        and context.location.col == 0
        and len(text) == 1
        and "가" <= text <= "힣"
    )


def _is_short_numbered_heading(context: TextContext) -> bool:
    return (
        context.location.table is None
        and len(context.normalized_text) <= 80
        and bool(_NUMBERED_HEADING_RE.match(context.normalized_text))
    )


def _is_marker_companion(context: TextContext) -> bool:
    return (
        context.table_has_section_marker
        and _is_short_label(context.normalized_text)
        and not _looks_like_sample_content(context.normalized_text)
    )


def _is_table_header_or_row_label(context: TextContext) -> bool:
    row = context.location.row
    col = context.location.col
    if (
        context.location.table is None
        or row is None
        or col is None
        or context.cell_text_count != 1
        or not _is_short_label(context.normalized_text)
        or _looks_like_sample_content(context.normalized_text)
    ):
        return False
    rows = context.table_rows or 0
    cols = context.table_cols or 0
    if rows >= 2 and cols >= 2 and (row == 0 or col == 0):
        return True
    return (
        rows == 1
        and cols >= 2
        and col == 0
        and context.table_nonempty_cell_count >= 2
        and content_category(context.normalized_text) == "document_title"
    )


def _is_short_label(text: str) -> bool:
    return bool(text) and len(text) <= 40 and "\n" not in text


def _looks_like_sample_content(text: str) -> bool:
    return bool(_SAMPLE_SYMBOL_RE.search(text))


def _table_has_section_marker(table: ET.Element | None) -> bool:
    if table is None:
        return False
    for cell in _nodes(table, "tc"):
        _, col = _cell_address(cell)
        for node in _nodes(cell, "t"):
            text = _normalize("".join(node.itertext()))
            if _ROMAN_MARKER_RE.fullmatch(text) or _LIST_MARKER_RE.fullmatch(text):
                return True
            if col == 0 and len(text) == 1 and "가" <= text <= "힣":
                return True
    return False


def _nearest(
    node: ET.Element,
    parents: dict[ET.Element, ET.Element],
    local_name: str,
) -> ET.Element | None:
    current = node
    while current in parents:
        current = parents[current]
        if _local_name(current.tag) == local_name:
            return current
    return None


def _cell_address(cell: ET.Element | None) -> tuple[int | None, int | None]:
    if cell is None:
        return None, None
    address = next((node for node in cell if _local_name(node.tag) == "cellAddr"), None)
    return _int_attr(address, "rowAddr"), _int_attr(address, "colAddr")


def _nonempty_text_count(node: ET.Element | None) -> int:
    if node is None:
        return 0
    return sum(bool(_normalize("".join(text.itertext()))) for text in _nodes(node, "t"))


def _nonempty_cell_count(table: ET.Element | None) -> int:
    if table is None:
        return 0
    return sum(_nonempty_text_count(cell) > 0 for cell in _nodes(table, "tc"))


def _nodes(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].split(":", 1)[-1]


def _int_attr(node: ET.Element | None, name: str) -> int | None:
    if node is None:
        return None
    for key, value in node.attrib.items():
        if _local_name(key) == name:
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _normalize(value: str) -> str:
    return " ".join(value.split())
