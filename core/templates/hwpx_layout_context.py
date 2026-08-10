"""One layout-preservation contract for every ``{{placeholder}}``.

A placeholder is a hole in someone else's formatting. Rendering replaces the text
inside an ``<hp:t>`` and nothing else, so every formatting fact that surrounds the
hole has to come out of the render unchanged. This module is the single place
that decides which facts those are.

    source.hwpx
      -> DocumentLayout.context_for()   extract what surrounds each placeholder
      -> placeholder_map.json           record it as the field's "layout_context"
      -> verify_recorded_layout()       separation, QA round-trip, and rendering
                                        all re-extract it and compare

Adding a preserved aspect (tab stops, container geometry, ...) means reading it
in ``DocumentLayout.read`` and naming it in ``DocumentLayout.context_for``.
Extraction, the recorded contract, and every verification point follow from
those two places. It must never mean one more aspect-shaped branch in the
separator plus two more in the renderer.

Honesty:
- The contract records what the source document actually has, including "no
  margin at all". It never requires a formatting fact the source did not have.
- A placeholder with no recorded layout context cannot be rendered: an
  unprotected hole is reported, not silently filled.
- Paragraph anchors are indices into the section, so a render that inserts or
  removes paragraphs (repeat expansion) must declare the rewritten range.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias
from xml.etree import ElementTree

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

LAYOUT_CONTRACT: Final = "layout-context-v1"
LAYOUT_CONTEXT_KEY: Final = "layout_context"
STYLE_MARGIN_KEY: Final = "paragraph_style_margins"

# section -> rewritten paragraph ranges, each
# (source paragraph index, source paragraph count, rendered paragraph count).
RewrittenRanges: TypeAlias = Mapping[str, Sequence[tuple[int, int, int]]]


class LayoutContractError(ValueError):
    """The document does not match the recorded layout context."""


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    """The layout facts one section and its header expose at a placeholder."""

    paragraph_styles: tuple[str | None, ...]
    fwspace_counts: tuple[tuple[int, int], ...]
    cell_margins: Mapping[tuple[int, int, int], dict[str, str] | None]
    style_margins: Mapping[str, list[dict[str, dict[str, str]]]]

    @classmethod
    def read(cls, section_xml: str | bytes, header_xml: str | bytes) -> DocumentLayout:
        section = ElementTree.fromstring(section_xml)
        header = ElementTree.fromstring(header_xml)
        return cls(
            paragraph_styles=tuple(
                node.get("paraPrIDRef") for node in _nodes(section, "p")
            ),
            fwspace_counts=tuple(
                _edge_fwspace_counts(node) for node in _nodes(section, "t")
            ),
            cell_margins=_cell_margins(section),
            style_margins=_style_margins(header),
        )

    @property
    def paragraph_count(self) -> int:
        return len(self.paragraph_styles)

    def context_for(self, field: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        """Every preserved layout aspect at one placeholder's anchor.

        This is the aspect list. Nothing else in the project may decide which
        formatting a placeholder depends on.
        """
        index = paragraph_anchor(field)
        if index >= self.paragraph_count:
            raise LayoutContractError(
                f"{_field_id(field)} anchors paragraph {index}, "
                f"but the document has {self.paragraph_count} paragraphs"
            )
        context: dict[str, JsonValue] = {
            "para_pr_id_ref": self.paragraph_styles[index],
        }
        text_node_index = field.get("text_node_index")
        if (
            isinstance(text_node_index, int)
            and not isinstance(text_node_index, bool)
            and 0 <= text_node_index < len(self.fwspace_counts)
        ):
            leading_fwspace_count, trailing_fwspace_count = self.fwspace_counts[
                text_node_index
            ]
            if leading_fwspace_count:
                context["leading_fwspace_count"] = leading_fwspace_count
            if trailing_fwspace_count:
                context["trailing_fwspace_count"] = trailing_fwspace_count
        cell = _cell_anchor(field)
        if cell is not None:
            if cell not in self.cell_margins:
                raise LayoutContractError(
                    f"{_field_id(field)} anchors table cell {cell}, "
                    "which the document does not have"
                )
            context["cell_margin"] = self.cell_margins[cell]
        return context

    def margins_of_referenced_styles(
        self,
        fields: Iterable[Mapping[str, JsonValue]],
    ) -> dict[str, list[dict[str, dict[str, str]]]]:
        """The header margin definitions the given placeholders depend on.

        Document-level half of the contract: styles are shared, so recording
        their definitions once keeps ``placeholder_map.json`` readable instead
        of repeating the same margins under every field.
        """
        return {
            style: self.style_margins.get(style, [])
            for style in sorted(
                {
                    self.paragraph_styles[paragraph_anchor(field)]
                    for field in fields
                    if paragraph_anchor(field) < self.paragraph_count
                }
                - {None}
            )
        }


def paragraph_anchor(field: Mapping[str, JsonValue]) -> int:
    index = field.get("paragraph_index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise LayoutContractError(
            f"{_field_id(field)} has no paragraph_index to anchor its layout to"
        )
    return index


def _cell_anchor(field: Mapping[str, JsonValue]) -> tuple[int, int, int] | None:
    address = tuple(field.get(name) for name in ("table", "row", "col"))
    if all(value is None for value in address):
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, int) for value in address
    ):
        raise LayoutContractError(
            f"{_field_id(field)} has an incomplete table cell address: {address}"
        )
    return address  # type: ignore[return-value]


def verify_recorded_layout(
    placeholder_map: Mapping[str, JsonValue],
    read_section: Callable[[str], str | bytes],
    header_xml: str | bytes,
    *,
    where: str,
    rewritten: RewrittenRanges | None = None,
) -> None:
    """Re-extract every placeholder's layout context and compare it to the record.

    ``rewritten`` declares paragraph ranges this document intentionally rebuilt
    (repeat expansion). Anchors after such a range shift by its length change,
    and anchors inside it are not compared: those paragraphs are copies of the
    recorded source paragraphs with new text (see ``_render_repeat_items``).
    """
    fields, counts, style_margins = _contract(placeholder_map, where)
    for section, recorded_count in counts.items():
        ranges = sorted((rewritten or {}).get(section, ()))
        _verify_section(
            DocumentLayout.read(read_section(section), header_xml),
            [field for field in fields if field.get("section") == section],
            style_margins,
            where=f"{where} {section}",
            expected_paragraph_count=recorded_count
            + sum(rendered - source for _, source, rendered in ranges),
            rewritten=ranges,
        )


def _verify_section(
    layout: DocumentLayout,
    fields: Iterable[Mapping[str, JsonValue]],
    recorded_style_margins: Mapping[str, JsonValue],
    *,
    where: str,
    expected_paragraph_count: int,
    rewritten: Sequence[tuple[int, int, int]],
) -> None:
    if layout.paragraph_count != expected_paragraph_count:
        raise LayoutContractError(
            f"paragraph count changed in {where}: "
            f"expected {expected_paragraph_count}, found {layout.paragraph_count}"
        )
    for field in fields:
        recorded = field.get(LAYOUT_CONTEXT_KEY)
        if not isinstance(recorded, dict):
            raise LayoutContractError(
                f"{_field_id(field)} has no recorded layout context in {where}; "
                "re-extract the template so every placeholder records one"
            )
        anchor = _shifted_anchor(paragraph_anchor(field), rewritten)
        if anchor is None:
            continue
        actual = layout.context_for({**field, "paragraph_index": anchor})
        for aspect in sorted(set(recorded) | set(actual)):
            if recorded.get(aspect) != actual.get(aspect):
                raise LayoutContractError(
                    f"{aspect} changed in {where} for {_field_id(field)}: "
                    f"recorded {recorded.get(aspect)!r}, found {actual.get(aspect)!r}"
                )
        # 문단이 참조하는 스타일의 header 정의도 계약의 일부다. 정의는 여러
        # placeholder가 공유하므로 문서 단위 표에 한 번만 기록돼 있다.
        style = actual["para_pr_id_ref"]
        if style is None:
            continue
        margins = layout.style_margins.get(style, [])
        if recorded_style_margins.get(style) != margins:
            raise LayoutContractError(
                f"paragraph style {style} margins changed in {where} "
                f"for {_field_id(field)}: "
                f"recorded {recorded_style_margins.get(style)!r}, found {margins!r}"
            )


def _shifted_anchor(
    index: int,
    rewritten: Sequence[tuple[int, int, int]],
) -> int | None:
    shift = 0
    for start, source, rendered in rewritten:
        if index < start:
            break
        if index < start + source:
            return None  # 이 문단 자체가 원본 복사본으로 다시 만들어졌다
        shift += rendered - source
    return index + shift


def _contract(
    placeholder_map: Mapping[str, JsonValue],
    where: str,
) -> tuple[list[Mapping[str, JsonValue]], dict[str, int], Mapping[str, JsonValue]]:
    if placeholder_map.get("layout_contract") != LAYOUT_CONTRACT:
        raise LayoutContractError(
            f"{where} declares no {LAYOUT_CONTRACT}; re-extract the template with "
            "scripts/templates/qa_hwpx_template.py so its placeholders record "
            "the layout they must preserve"
        )
    counts = placeholder_map.get("section_paragraph_counts")
    fields = placeholder_map.get("fields")
    style_margins = placeholder_map.get(STYLE_MARGIN_KEY)
    if (
        not isinstance(counts, dict)
        or not isinstance(fields, list)
        or not isinstance(style_margins, dict)
        or not all(
            isinstance(count, int) and not isinstance(count, bool)
            for count in counts.values()
        )
        or not all(isinstance(field, dict) for field in fields)
    ):
        raise LayoutContractError(f"{where} has an unreadable layout contract")
    unanchored = sorted(
        str(field.get("field_id"))
        for field in fields
        if field.get("section") not in counts
    )
    if unanchored:
        raise LayoutContractError(
            f"{where} records no paragraph count for the sections of {unanchored}"
        )
    return fields, counts, style_margins


def _style_margins(header: ElementTree.Element) -> dict[str, list[dict[str, dict[str, str]]]]:
    # 한 paraPr는 hp:switch의 case/default마다 다른 margin을 가질 수 있으므로
    # 문서 순서대로 모두 기록한다.
    margins: dict[str, list[dict[str, dict[str, str]]]] = {}
    for style in _nodes(header, "paraPr"):
        style_id = style.get("id")
        if style_id is None:
            continue
        margins[style_id] = [
            {_local_name(part.tag): dict(part.attrib) for part in margin}
            for margin in _nodes(style, "margin")
        ]
    return margins


def _cell_margins(
    section: ElementTree.Element,
) -> dict[tuple[int, int, int], dict[str, str] | None]:
    margins: dict[tuple[int, int, int], dict[str, str] | None] = {}
    for table_index, table in enumerate(_nodes(section, "tbl")):
        for cell in _nodes(table, "tc"):
            address = _child(cell, "cellAddr")
            if address is None:
                continue
            row = address.get("rowAddr")
            col = address.get("colAddr")
            if row is None or col is None:
                continue
            margin = _child(cell, "cellMargin")
            margins[(table_index, int(row), int(col))] = (
                dict(margin.attrib) if margin is not None else None
            )
    return margins


def _edge_fwspace_counts(text: ElementTree.Element) -> tuple[int, int]:
    leading = 0
    if not (text.text and text.text.strip()):
        for child in text:
            if _local_name(child.tag) != "fwSpace":
                break
            leading += 1
            if child.tail and child.tail.strip():
                break
    trailing = 0
    for child in reversed(text):
        if child.tail and child.tail.strip():
            break
        if _local_name(child.tag) != "fwSpace":
            break
        trailing += 1
    return leading, trailing


def _field_id(field: Mapping[str, JsonValue]) -> str:
    field_id = field.get("field_id")
    return field_id if isinstance(field_id, str) else "an unnamed placeholder"


def _child(node: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
    return next(
        (child for child in node if _local_name(child.tag) == local_name),
        None,
    )


def _nodes(root: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]
