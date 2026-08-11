"""Render a filled HWPX from a template's {{placeholder}}s and a content mapping.

Deterministic. Reads the template's ``placeholder_map.json`` +
``template/section*.template.xml``, replaces each ``{{field_id}}`` (kept inside its
``<hp:t>``) with the XML-escaped content value, then writes the filled sections into
a byte-preserving copy of the *base* HWPX. Filled sections change, and a missing
Hancom ``hwpunitchar`` root declaration is restored when strict validation requires it.
Changed sections discard ``hp:linesegarray`` caches so Hancom recalculates the
new text layout instead of reusing character positions from the sample content.

Content may be keyed by ``field_id`` or, when the template ships an
``alias_map.json``, by the human-authored names bound there (see
``core.adapters.hwpx_alias_map``). Nested objects and arrays in the content are
flattened onto those names (``담당.국``, ``부제[0]``).

Honesty:
- Missing fields (in the placeholder map but absent from content) are left as
  ``{{placeholder}}`` and reported — never invented. ``on_missing="sample"``
  restores the reference document's own text for them instead.
- Content keys that match neither an alias nor a ``field_id`` are reported as
  ``unknown_keys`` rather than dropped.
- Any ``{{...}}`` still present after filling is reported as a leftover placeholder.
- ``Contents/content.hpf`` gets fresh created/modified stamps on every render.
  The FSS input adapter prepares its nine metadata values before rendering;
  other templates retain the existing title/date flow.
- The FSS director report rebuilds ``Preview/PrvText.txt`` from the final leaf
  paragraphs after mapped table cells have been filled.
- The output is validated with strict HWPX package validation before it is returned
  (``validate=True``); a file that only opens in Hancom is not treated as finished.
- A base package is required. The template's ``raw/`` folder omits entries
  (mimetype, version.xml, Preview/…) and cannot be repacked on its own, so a
  self-contained template stores the exact original as ``source.hwpx`` (see
  ``snapshot_source_hwpx``); the renderer uses it when no ``base_hwpx`` is given.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from html import unescape
from pathlib import Path
from typing import TypeAlias
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont

from .hwpx_alias_map import FitConstraint, RepeatBlock
from .hwpx_fss_director_report import (
    FSS_META_NAMES,
    FssPackageMetadata,
)
from ..templates.hwpx_layout_context import (
    LayoutContractError,
    verify_recorded_layout,
)
from .hwpx_table_fill_adapter import (
    HwpxTableCellFill,
    fill_hwpx_table_cells,
)
from .hwpx_template_input import (
    HwpxTemplateInputError,
    HwpxTemplateRenderError,
    PreparedRenderContent,
    RenderExecutionContext,
    ResolvedRenderPlan,
    load_placeholder_map,
    prepare_hwpx_template_input,
    resolve_hwpx_template_input,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
_SECTION_TEMPLATE_RE = re.compile(r"^section(\d+)\.template\.xml$", re.IGNORECASE)
_REPEAT_OBJECT_RE = re.compile(
    r"<hp:(?:tbl|ctrl|pic|ole|equation|container)\b"
)
_REPEAT_SEPARATOR_ELEMENT_RE = re.compile(
    r"</?hp:(?:p|run|t|linesegarray|lineseg)\b[^>]*>"
)
_SECTION_PART_RE = re.compile(r"^Contents/section\d+\.xml$", re.IGNORECASE)
_PARAGRAPH_START_RE = re.compile(r"<hp:p\b")
_LINESEGARRAY_RE = re.compile(
    r"<hp:linesegarray\b[^>]*/>|<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>",
    re.DOTALL,
)
_XML_TAG_RE = re.compile(
    r"<(?P<closing>/)?(?P<name>[A-Za-z_][\w.-]*(?::[A-Za-z_][\w.-]*)?)(?:\s+(?:[^\"'>]|\"[^\"]*\"|'[^']*')*)?\s*/?>",
    re.DOTALL,
)
_LEADING_FWSPACE_TAG_RE = re.compile(
    r"\s*<(?:[A-Za-z_][\w.-]*:)?fwSpace\b[^>]*/>"
)
_ROW_ADDRESS_RE = re.compile(r'\browAddr="(?P<row>\d+)"')
_COL_ADDRESS_RE = re.compile(r'\bcolAddr="(?P<col>\d+)"')
_HPF_PART = "Contents/content.hpf"
_FSS_SECTION_PART = "Contents/section0.xml"
_FSS_PREVIEW_TEXT_PART = "Preview/PrvText.txt"
_HPF_TITLE_RE = re.compile(r"<opf:title(?:\s*/>|>.*?</opf:title>)", re.DOTALL)
_HWPUNITCHAR_DECLARATION_RE = re.compile(br"\bxmlns:hwpunitchar\s*=")
_HWPML_ROOT_START_RE = re.compile(br"<(?:[A-Za-z_][\w.-]*:)?(?:head|sec)\b")
_HWPUNITCHAR_DECLARATION = (
    b'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"'
)
_HP_NAMESPACE = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HH_NAMESPACE = "http://www.hancom.co.kr/hwpml/2011/head"
_XML_NAMESPACES = {"hp": _HP_NAMESPACE, "hh": _HH_NAMESPACE}
_FSS_FONT_FILES = {"맑은 고딕": "malgun.ttf"}
_FSS_SYMBOL_FALLBACK = "seguisym.ttf"

UNKNOWN = "확인 필요"
ON_MISSING_MODES = ("keep", "sample", "unknown", "error")


@dataclass(frozen=True, slots=True)
class _PackageContent:
    sections: Mapping[str, str]
    # None only on the candidate round-trip, where content.hpf is copied unchanged.
    fss_metadata: FssPackageMetadata | None


@dataclass(frozen=True, slots=True)
class _XmlSpan:
    name: str
    start: int
    open_end: int
    content_end: int
    end: int
    parent: int | None


@dataclass(frozen=True, slots=True)
class TemplateContent:
    """Explicit field values bound to one approved template identity."""

    template_id: str
    fields: dict[str, JsonValue]


@dataclass
class RenderResult:
    output: Path
    filled_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    leftover_placeholders: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    title_updated: bool = False

    def to_meta(self) -> dict:
        return {
            "output": str(self.output),
            "filled_fields": self.filled_fields,
            "missing_fields": self.missing_fields,
            "leftover_placeholders": self.leftover_placeholders,
            "unknown_keys": self.unknown_keys,
            "title_updated": self.title_updated,
        }


def fill_template_sections(
    template_dir: Path | str,
    content: Mapping[str, JsonValue],
    *,
    on_missing: str = "keep",
) -> tuple[dict[str, str], RenderResult]:
    """Fill each template section's placeholders. Returns ({internal_path: xml}, result).

    ``on_missing``: "keep" leaves ``{{field}}`` (default), "sample" restores the
    reference document's own text from ``content.sample.json``, "unknown" writes
    ``확인 필요``, "error" raises if any mapped field is absent from content.
    """
    template_dir = Path(template_dir)
    _validate_on_missing(on_missing)
    try:
        resolved = resolve_hwpx_template_input(
            template_dir,
            content,
            resolve_metadata=False,
        )
    except HwpxTemplateInputError as exc:
        raise HwpxTemplateRenderError(str(exc)) from exc
    filled_sections, result, _ = _fill_resolved_template_sections(
        template_dir,
        resolved.render_plan,
        resolved.unknown_keys,
        on_missing,
    )
    return filled_sections, result


def _fill_resolved_template_sections(
    template_dir: Path,
    plan: ResolvedRenderPlan,
    unknown_keys: tuple[str, ...],
    on_missing: str,
) -> tuple[dict[str, str], RenderResult, dict[str, list[tuple[int, int, int]]]]:
    """Fill one template's sections; also report which paragraph ranges were rebuilt."""
    filled: set[str] = set()
    missing: set[str] = set()

    filled_sections: dict[str, str] = {}
    rewritten: dict[str, list[tuple[int, int, int]]] = {}
    template_files = sorted((template_dir / "template").glob("section*.template.xml"))
    if not template_files:
        raise HwpxTemplateRenderError(f"no template/section*.template.xml in {template_dir}")
    _validate_fit_constraints(
        template_dir,
        plan.field_values,
        plan.fit_constraints,
    )
    for template_file in template_files:
        match = _SECTION_TEMPLATE_RE.fullmatch(template_file.name)
        if match is None:
            continue
        section = f"section{int(match.group(1))}.xml"
        internal = f"Contents/{section}"
        xml = template_file.read_text(encoding="utf-8")
        filled_xml, repeat_filled, repeat_ranges = render_repeat_block(
            xml,
            plan.repeat_values,
            plan.repeat_blocks,
        )
        filled.update(repeat_filled)
        if repeat_ranges:
            rewritten[section] = repeat_ranges
        filled_xml = _fill_xml(
            filled_xml,
            plan.field_values,
            filled,
            missing,
        )
        if filled_xml != xml:
            filled_xml = _LINESEGARRAY_RE.sub("", filled_xml)
        filled_sections[internal] = filled_xml

    if on_missing == "error" and missing:
        raise HwpxTemplateRenderError(f"missing content for fields: {sorted(missing)}")
    if missing and on_missing in ("unknown", "sample"):
        # second pass fills still-unfilled placeholders from a fallback source;
        # a field absent from that source stays {{field}} and is reported below
        fallback = _missing_fallback(template_dir, missing, on_missing)
        for internal, xml in filled_sections.items():
            filled_xml = _PLACEHOLDER_RE.sub(
                lambda m: escape(str(fallback[m.group(1)]))
                if m.group(1) in fallback
                else m.group(0),
                xml,
            )
            if filled_xml != xml:
                filled_xml = _LINESEGARRAY_RE.sub("", filled_xml)
            filled_sections[internal] = filled_xml

    leftover = sorted(
        {m.group(1) for xml in filled_sections.values() for m in _PLACEHOLDER_RE.finditer(xml)}
    )
    result = RenderResult(
        output=Path(),
        filled_fields=sorted(filled),
        missing_fields=sorted(missing),
        leftover_placeholders=leftover,
        unknown_keys=list(unknown_keys),
    )
    return filled_sections, result, rewritten


def _write_hwpx_package(
    base: Path,
    output_path: Path,
    package_content: _PackageContent,
) -> None:
    replaced: set[str] = set()
    with zipfile.ZipFile(base) as zin, zipfile.ZipFile(output_path, "w") as zout:
        for info in zin.infolist():  # keep entry order (mimetype first) + compress types
            data = zin.read(info.filename)
            if info.filename in package_content.sections:
                data = package_content.sections[info.filename].encode("utf-8")
                replaced.add(info.filename)
            if (
                info.filename == "Contents/header.xml"
                or _SECTION_PART_RE.fullmatch(info.filename)
            ):
                data = _ensure_hwpunitchar_namespace(data)
            if (
                info.filename == _HPF_PART
                and package_content.fss_metadata is not None
            ):
                data = _update_fss_content_hpf(data, package_content.fss_metadata)
            zout.writestr(info, data)

    unmatched = sorted(set(package_content.sections) - replaced)
    if unmatched:
        raise HwpxTemplateRenderError(
            f"filled sections not present in base HWPX: {unmatched}"
        )


def _apply_table_fills(
    output_path: Path,
    table_fills: list[HwpxTableCellFill],
    placeholder_map: Mapping[str, JsonValue],
) -> None:
    if not table_fills:
        return
    with tempfile.TemporaryDirectory(
        prefix=".hwpx-template-table-fill-",
        dir=output_path.parent,
    ) as temp:
        table_output = Path(temp) / output_path.name
        table_result = fill_hwpx_table_cells(
            output_path,
            table_output,
            table_fills,
            skill_dir=Path(__file__).resolve().parents[2] / "skills" / "hwp-skill",
        )
        if not table_result.ok:
            raise HwpxTemplateRenderError(
                f"mapped table-cell rendering failed: {table_result.error}"
            )
        _restore_table_cell_leading_fwspaces(
            table_output,
            table_fills,
            placeholder_map,
            reference_path=output_path,
        )
        shutil.copyfile(table_output, output_path)


def _restore_table_cell_leading_fwspaces(
    output_path: Path,
    table_fills: list[HwpxTableCellFill],
    placeholder_map: Mapping[str, JsonValue],
    *,
    reference_path: Path,
) -> None:
    filled_cells = {
        (fill.section, fill.table, fill.row, fill.col) for fill in table_fills
    }
    targets: dict[str, dict[tuple[int, int, int, int], tuple[int, bool]]] = {}
    fields = placeholder_map.get("fields", [])
    if not isinstance(fields, list):
        return
    section_ordinals: Mapping[str, int] | None = None
    for field in fields:
        if not isinstance(field, dict):
            continue
        context = field.get("layout_context")
        if not isinstance(context, dict):
            continue
        expected = context.get("leading_fwspace_count")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
            continue
        section = field.get("section")
        table = field.get("table")
        row = field.get("row")
        col = field.get("col")
        text_node_index = field.get("text_node_index")
        if (
            not isinstance(section, str)
            or not isinstance(table, int)
            or not isinstance(row, int)
            or not isinstance(col, int)
        ):
            continue
        if "section_index" not in field and section_ordinals is None:
            section_ordinals = _section_ordinals(output_path)
        section_index = _table_cell_section_index(field, section_ordinals)
        if not isinstance(section_index, int):
            raise HwpxTemplateRenderError(
                "table-cell leading_fwspace_count requires an integer section_index"
            )
        if (section_index, table, row, col) not in filled_cells:
            continue
        if (
            not isinstance(text_node_index, int)
            or isinstance(text_node_index, bool)
            or text_node_index < 0
        ):
            raise HwpxTemplateRenderError(
                "table-cell leading_fwspace_count requires text_node_index"
            )
        targets.setdefault(f"Contents/{section}", {})[
            (table, row, col, text_node_index)
        ] = (expected, field.get("replacement_mode") != "table_cell")

    if not targets:
        return
    with zipfile.ZipFile(output_path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(reference_path) as reference:
        reference_data = {
            section: reference.read(section).decode("utf-8") for section in targets
        }
    entry_data = {info.filename: data for info, data in entries}
    restored = {
        section: _restore_leading_fwspaces_in_section(
            data.decode("utf-8"),
            reference_data[section],
            cells,
        ).encode("utf-8")
        for section, cells in targets.items()
        for data in [entry_data[section]]
    }
    with tempfile.TemporaryDirectory(
        prefix=".hwpx-template-table-indent-",
        dir=output_path.parent,
    ) as temp:
        temporary_output = Path(temp) / output_path.name
        with zipfile.ZipFile(temporary_output, "w") as destination:
            for info, data in entries:
                destination.writestr(info, restored.get(info.filename, data))
        os.replace(temporary_output, output_path)


def _restore_leading_fwspaces_in_section(
    section: str,
    reference: str,
    targets: Mapping[tuple[int, int, int, int], tuple[int, bool]],
) -> str:
    spans = _xml_spans(section)
    reference_spans = _xml_spans(reference)
    tables = [index for index, span in enumerate(spans) if span.name == "hp:tbl"]
    reference_tables = [
        index for index, span in enumerate(reference_spans) if span.name == "hp:tbl"
    ]
    replacements: list[tuple[int, int, str]] = []
    for table_index, row, col, text_node_index in targets:
        if table_index >= len(tables) or table_index >= len(reference_tables):
            raise HwpxTemplateRenderError(
                f"table-cell fwSpace restoration cannot find table {table_index}"
            )
        table_span = tables[table_index]
        cell_span = _cell_span(spans, table_span, row, col, section)
        text_span = _text_span_in_cell(spans, cell_span, text_node_index)
        expected, preserve_content = targets[(table_index, row, col, text_node_index)]
        if preserve_content:
            reference_table_span = reference_tables[table_index]
            reference_cell_span = _cell_span(
                reference_spans,
                reference_table_span,
                row,
                col,
                reference,
            )
            reference_text_span = _text_span_in_cell(
                reference_spans,
                reference_cell_span,
                text_node_index,
            )
            replacements.append(
                (
                    text_span.open_end,
                    text_span.content_end,
                    reference[
                        reference_text_span.open_end : reference_text_span.content_end
                    ],
                )
            )
            continue
        body = section[text_span.open_end : text_span.content_end]
        position = 0
        count = 0
        while match := _LEADING_FWSPACE_TAG_RE.match(body, position):
            position = match.end()
            count += 1
        missing = expected - count
        if missing > 0:
            replacements.append(
                (
                    text_span.open_end + position,
                    text_span.open_end + position,
                    "<hp:fwSpace/>" * missing,
                )
            )
    for start, end, value in sorted(replacements, reverse=True):
        section = section[:start] + value + section[end:]
    return section


def _xml_spans(xml: str) -> list[_XmlSpan]:
    spans: list[_XmlSpan] = []
    stack: list[int] = []
    for match in _XML_TAG_RE.finditer(xml):
        name = match.group("name")
        if match.group("closing"):
            if not stack or spans[stack[-1]].name != name:
                raise HwpxTemplateRenderError("malformed section XML during fwSpace restoration")
            index = stack.pop()
            spans[index] = replace(
                spans[index],
                content_end=match.start(),
                end=match.end(),
            )
            continue
        parent = stack[-1] if stack else None
        span = _XmlSpan(
            name=name,
            start=match.start(),
            open_end=match.end(),
            content_end=match.end(),
            end=match.end(),
            parent=parent,
        )
        spans.append(span)
        if not match.group(0).rstrip().endswith("/>"):
            stack.append(len(spans) - 1)
    if stack:
        raise HwpxTemplateRenderError("unclosed section XML during fwSpace restoration")
    return spans


def _cell_span(
    spans: list[_XmlSpan],
    table_span: int,
    row: int,
    col: int,
    section: str,
) -> int:
    for index, span in enumerate(spans):
        if span.name != "hp:tc" or _nearest_ancestor(spans, index, "hp:tbl") != table_span:
            continue
        address = next(
            (
                child
                for child, child_span in enumerate(spans)
                if child_span.parent == index and child_span.name == "hp:cellAddr"
            ),
            None,
        )
        if address is None:
            continue
        opening = section[spans[address].start : spans[address].open_end]
        row_match = _ROW_ADDRESS_RE.search(opening)
        col_match = _COL_ADDRESS_RE.search(opening)
        if (
            row_match is not None
            and col_match is not None
            and int(row_match.group("row")) == row
            and int(col_match.group("col")) == col
        ):
            return index
    raise HwpxTemplateRenderError(
        f"table-cell fwSpace restoration cannot find row {row}, col {col}"
    )


def _text_span_in_cell(
    spans: list[_XmlSpan],
    cell_span: int,
    text_node_index: int,
) -> _XmlSpan:
    text_spans = [index for index, span in enumerate(spans) if span.name == "hp:t"]
    if text_node_index < len(text_spans):
        span_index = text_spans[text_node_index]
        if _nearest_ancestor(spans, span_index, "hp:tc") == cell_span:
            return spans[span_index]
    raise HwpxTemplateRenderError(
        f"table-cell fill moved text node {text_node_index} outside its recorded cell"
    )


def _nearest_ancestor(
    spans: list[_XmlSpan],
    index: int,
    name: str,
) -> int | None:
    parent = spans[index].parent
    while parent is not None:
        if spans[parent].name == name:
            return parent
        parent = spans[parent].parent
    return None


def _refresh_fss_preview_text(output_path: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix=".hwpx-template-preview-",
        dir=output_path.parent,
    ) as temp:
        with zipfile.ZipFile(output_path) as source:
            infos = source.infolist()
            section_infos = [
                info for info in infos if info.filename == _FSS_SECTION_PART
            ]
            preview_infos = [
                info for info in infos if info.filename == _FSS_PREVIEW_TEXT_PART
            ]
            if len(section_infos) != 1 or len(preview_infos) != 1:
                raise HwpxTemplateRenderError(
                    "fss package requires exactly one section0.xml and PrvText.txt"
                )

            root = ElementTree.fromstring(source.read(section_infos[0]))
            paragraph_tag = f"{{{_HP_NAMESPACE}}}p"
            text_tag = f"{{{_HP_NAMESPACE}}}t"
            table_tag = f"{{{_HP_NAMESPACE}}}tbl"
            row_tag = f"{{{_HP_NAMESPACE}}}tr"
            cell_tag = f"{{{_HP_NAMESPACE}}}tc"
            lines: list[str] = []
            for paragraph in root.findall(paragraph_tag):
                tables = list(paragraph.iter(table_tag))
                if tables:
                    for table in tables:
                        for row in table.findall(row_tag):
                            cells: list[str] = []
                            for cell in row.findall(cell_tag):
                                cell_text = "".join(
                                    "".join(node.itertext())
                                    for node in cell.iter(text_tag)
                                )
                                cells.append(f"<{cell_text}>")
                            lines.append("".join(cells))
                    continue
                text = "".join(
                    "".join(node.itertext()) for node in paragraph.iter(text_tag)
                )
                if text.strip():
                    lines.append(text)
            preview_data = "\r\n".join(lines).encode("utf-8")

            preview_output = Path(temp) / output_path.name
            with zipfile.ZipFile(preview_output, "w") as destination:
                for info in infos:
                    payload = source.read(info)
                    if info.filename == _FSS_PREVIEW_TEXT_PART:
                        payload = preview_data
                    destination.writestr(info, payload)
        os.replace(preview_output, output_path)


def orchestrate_hwpx_render(
    template_dir: Path | str,
    content: Mapping[str, JsonValue],
    output_path: Path | str,
    *,
    execution_context: RenderExecutionContext | None = None,
    base_hwpx: Path | str | None = None,
    on_missing: str = "keep",
    validate: bool = True,
) -> RenderResult:
    """Generate a final document from an approved template.

    The template must declare a metadata contract in ``alias_map.json`` and an
    ``execution_context`` must name the requester; without either this raises
    rather than writing a document with partial metadata. To round-trip a
    template that is still being built, use ``render_candidate_roundtrip``.

    The base package is ``base_hwpx`` if given, otherwise the self-contained
    ``<template_dir>/source.hwpx`` snapshot. ``Contents/section*.xml`` change,
    ``Contents/content.hpf`` gets all nine declared metadata values, and
    ``Preview/PrvText.txt`` is rebuilt from the final section. Every other entry
    is copied byte-for-byte except that a missing required ``hwpunitchar`` root
    namespace is restored in header/section XML. A self-contained template needs
    no external file.

    ``validate`` (default True) runs strict HWPX package validation on the output
    and raises if it does not pass — a file that only opens in Hancom is not enough.
    Set ``validate=False`` only to intentionally inspect an unvalidated result.
    """
    try:
        prepared = prepare_hwpx_template_input(
            template_dir,
            content,
            execution_context=execution_context,
        )
    except HwpxTemplateInputError as exc:
        raise HwpxTemplateRenderError(str(exc)) from exc
    return render_prepared_hwpx_template(
        template_dir,
        prepared,
        output_path,
        base_hwpx=base_hwpx,
        on_missing=on_missing,
        validate=validate,
    )


def render_prepared_hwpx_template(
    template_dir: Path | str,
    content: PreparedRenderContent,
    output_path: Path | str,
    *,
    base_hwpx: Path | str | None = None,
    on_missing: str = "keep",
    validate: bool = True,
) -> RenderResult:
    template_dir = Path(template_dir)
    output_path = Path(output_path)
    try:
        target_map = load_placeholder_map(template_dir)
    except HwpxTemplateInputError as exc:
        raise HwpxTemplateRenderError(str(exc)) from exc
    target_template_id_raw = target_map.get("template_id")
    target_template_id = (
        target_template_id_raw
        if isinstance(target_template_id_raw, str)
        else None
    )
    if content.template_id != target_template_id:
        raise HwpxTemplateRenderError(
            "prepared template_id mismatch: "
            f"content={content.template_id!r}, target={target_template_id!r}"
        )
    base = Path(base_hwpx) if base_hwpx is not None else template_dir / "source.hwpx"
    _validate_render_paths(template_dir, base, output_path)
    return _render_filled_package(
        template_dir,
        content.placeholder_map,
        content.render_plan,
        content.unknown_keys,
        output_path,
        base,
        package_metadata=content.package_metadata,
        on_missing=on_missing,
        validate=validate,
    )


def render_candidate_roundtrip(
    template_dir: Path | str,
    content: Mapping[str, JsonValue],
    output_path: Path | str,
    *,
    base_hwpx: Path | str | None = None,
    on_missing: str = "keep",
    validate: bool = True,
) -> RenderResult:
    """Round-trip a template that is still being built: structure and format only.

    This is the check run while extracting and QA-ing a template, before anyone
    has written its ``alias_map.json``. No document metadata exists yet, so
    ``Contents/content.hpf`` and ``Preview/PrvText.txt`` are copied unchanged and
    the output is a structural round-trip, not a finished document. Generating a
    final document from an approved template goes through
    ``orchestrate_hwpx_render``, which requires the metadata contract.
    """
    template_dir = Path(template_dir)
    output_path = Path(output_path)
    try:
        resolved = resolve_hwpx_template_input(
            template_dir,
            content,
            resolve_metadata=False,
        )
    except HwpxTemplateInputError as exc:
        raise HwpxTemplateRenderError(str(exc)) from exc
    base = Path(base_hwpx) if base_hwpx is not None else template_dir / "source.hwpx"
    _validate_render_paths(template_dir, base, output_path)
    return _render_filled_package(
        template_dir,
        resolved.placeholder_map,
        resolved.render_plan,
        resolved.unknown_keys,
        output_path,
        base,
        package_metadata=None,
        on_missing=on_missing,
        validate=validate,
    )


def _validate_render_paths(
    template_dir: Path,
    base: Path,
    output_path: Path,
) -> None:
    if not base.is_file() or not zipfile.is_zipfile(base):
        raise HwpxTemplateRenderError(
            f"no base HWPX: pass base_hwpx or add a self-contained {template_dir / 'source.hwpx'}"
        )
    same_file = base.resolve() == output_path.resolve()
    if not same_file and output_path.exists():
        same_file = os.path.samefile(base, output_path)
    if same_file:
        raise HwpxTemplateRenderError(
            "output_path must not reference the source HWPX"
        )


def _render_filled_package(
    template_dir: Path,
    placeholder_map: Mapping[str, JsonValue],
    render_plan: ResolvedRenderPlan,
    unknown_keys: tuple[str, ...],
    output_path: Path,
    base: Path,
    *,
    package_metadata: FssPackageMetadata | None,
    on_missing: str,
    validate: bool,
) -> RenderResult:
    _validate_on_missing(on_missing)
    table_fills, table_filled, table_missing = _table_cell_fills(
        template_dir,
        placeholder_map,
        render_plan.field_values,
        on_missing=on_missing,
    )
    if on_missing == "error" and table_missing:
        raise HwpxTemplateRenderError(
            f"missing content for fields: {sorted(table_missing)}"
        )
    filled_sections, result, rewritten = _fill_resolved_template_sections(
        template_dir,
        render_plan,
        unknown_keys,
        on_missing,
    )
    result.filled_fields = sorted(set(result.filled_fields) | table_filled)
    result.missing_fields = sorted(set(result.missing_fields) | table_missing)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_hwpx_package(
        base,
        output_path,
        _PackageContent(
            sections=filled_sections,
            fss_metadata=package_metadata,
        ),
    )
    _apply_table_fills(output_path, table_fills, placeholder_map)
    _validate_rendered_layout(output_path, placeholder_map, rewritten)
    if package_metadata is not None:
        _refresh_fss_preview_text(output_path)
    if validate:
        validate_hwpx_output(output_path)
    result.output = output_path
    result.title_updated = package_metadata is not None
    return result


def _validate_rendered_layout(
    output_path: Path,
    placeholder_map: Mapping[str, JsonValue],
    rewritten: Mapping[str, list[tuple[int, int, int]]],
) -> None:
    """Check the rendered document still gives every placeholder its recorded layout."""
    with zipfile.ZipFile(output_path) as package:
        try:
            verify_recorded_layout(
                placeholder_map,
                lambda section: package.read(f"Contents/{section}"),
                package.read("Contents/header.xml"),
                where="the rendered document",
                rewritten=rewritten,
            )
        except LayoutContractError as exc:
            raise HwpxTemplateRenderError(str(exc)) from exc


def validate_hwpx_output(output_path: Path | str) -> None:
    """Run strict HWPX package validation; raise ``HwpxTemplateRenderError`` if it fails.

    Uses ``python-hwpx``. If that library is not installed, validation was
    requested but cannot run, so this raises rather than silently passing.
    """
    try:
        import hwpx  # local import: keep the renderer importable without python-hwpx
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise HwpxTemplateRenderError(
            "validate=True requires python-hwpx (pip install python-hwpx); "
            "pass validate=False to skip validation"
        ) from exc

    report = hwpx.validate_package(Path(output_path))
    if not report.ok:
        raise HwpxTemplateRenderError(
            f"rendered HWPX failed strict package validation: {list(report.errors)}"
        )


def snapshot_source_hwpx(source_hwpx: Path | str, template_dir: Path | str) -> Path:
    """Store a byte copy of the source HWPX as ``<template_dir>/source.hwpx``.

    Makes the template self-contained: ``orchestrate_hwpx_render`` can then render
    with no external base file, using this exact original package as the base.
    """
    source_hwpx = Path(source_hwpx)
    if not zipfile.is_zipfile(source_hwpx):
        raise HwpxTemplateRenderError(f"source is not a readable HWPX ZIP: {source_hwpx}")
    destination = Path(template_dir) / "source.hwpx"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_hwpx, destination)
    return destination


def load_template_content(content_json: Path | str) -> TemplateContent:
    """Parse a content.json and retain its template identity."""
    source = Path(content_json)
    data: JsonValue = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HwpxTemplateRenderError(f"content JSON root must be an object: {source}")
    template_id = data.get("template_id")
    fields = data.get("fields")
    if not isinstance(template_id, str) or not template_id:
        raise HwpxTemplateRenderError(f"content JSON requires a non-empty template_id: {source}")
    if not isinstance(fields, dict):
        raise HwpxTemplateRenderError(f"content JSON requires a fields object: {source}")
    return TemplateContent(template_id=template_id, fields=dict(fields))


def load_content_fields(content_json: Path | str) -> dict[str, JsonValue]:
    """Read a content.json and return a mutable copy of its ``fields`` mapping."""
    return dict(load_template_content(content_json).fields)


def _validate_on_missing(on_missing: str) -> None:
    if on_missing not in ON_MISSING_MODES:
        raise HwpxTemplateRenderError(
            f"on_missing must be one of {list(ON_MISSING_MODES)}, got {on_missing!r}"
        )


def _set_hpf_meta(xml: str, name: str, value: str) -> str:
    """Replace one ``<opf:meta name="...">`` value; raise if it is not there."""
    pattern = re.compile(
        rf'<opf:meta name="{re.escape(name)}"([^>]*?)(?:/>|>.*?</opf:meta>)',
        re.DOTALL,
    )
    # 값에 든 역슬래시가 역참조로 해석되지 않도록 치환은 함수로 넘긴다.
    filled, count = pattern.subn(
        lambda match: f'<opf:meta name="{name}"{match.group(1)}>'
        f"{escape(value)}</opf:meta>",
        xml,
        count=1,
    )
    if count != 1:
        raise HwpxTemplateRenderError(
            f"content.hpf has no <opf:meta name={name!r}> element to update"
        )
    return filled


def _replace_single_fss_meta(xml: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf'(<opf:meta\b(?=[^>]*\bname="{re.escape(name)}")[^>]*?)'
        r'(?:\s*/>|>.*?</opf:meta>)',
        re.DOTALL,
    )
    matches = list(pattern.finditer(xml))
    if len(matches) != 1:
        raise HwpxTemplateRenderError(
            f"content.hpf requires exactly one <opf:meta name={name!r}> element"
        )
    match = matches[0]
    replacement = f"{match.group(1)}>{escape(value)}</opf:meta>"
    return xml[: match.start()] + replacement + xml[match.end() :]


def _update_fss_content_hpf(
    data: bytes,
    metadata: FssPackageMetadata,
) -> bytes:
    xml = data.decode("utf-8")
    title_matches = list(_HPF_TITLE_RE.finditer(xml))
    if len(title_matches) != 1:
        raise HwpxTemplateRenderError(
            "content.hpf requires exactly one <opf:title> element"
        )
    title_match = title_matches[0]
    xml = (
        xml[: title_match.start()]
        + f"<opf:title>{escape(metadata.title)}</opf:title>"
        + xml[title_match.end() :]
    )
    stamp = metadata.requested_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    values = (
        metadata.creator,
        metadata.subject,
        metadata.description,
        metadata.lastsaveby,
        metadata.report_date,
        metadata.keywords,
        stamp,
        stamp,
    )
    for name, value in zip(FSS_META_NAMES, values, strict=True):
        xml = _replace_single_fss_meta(xml, name, value)
    return xml.encode("utf-8")


def _missing_fallback(
    template_dir: Path,
    missing: set[str],
    on_missing: str,
) -> dict[str, JsonValue]:
    """Values used for fields the content did not supply."""
    if on_missing == "unknown":
        return {field_id: UNKNOWN for field_id in missing}

    path = template_dir / "content.sample.json"
    if not path.is_file():
        raise HwpxTemplateRenderError(f'on_missing="sample" requires {path}')
    samples = load_content_fields(path)
    return {
        field_id: samples[field_id]
        for field_id in missing
        if samples.get(field_id) is not None
    }


def _table_cell_fills(
    template_dir: Path,
    placeholder_map: dict,
    content: Mapping[str, JsonValue],
    *,
    on_missing: str,
) -> tuple[list[HwpxTableCellFill], set[str], set[str]]:
    entries = [
        entry
        for entry in placeholder_map.get("fields", [])
        if entry.get("replacement_mode") == "table_cell"
    ]
    filled = {entry["field_id"] for entry in entries if content.get(entry["field_id"]) is not None}
    missing = {entry["field_id"] for entry in entries} - filled

    fallback: dict[str, JsonValue] = {}
    if missing and on_missing in ("unknown", "sample"):
        fallback = _missing_fallback(template_dir, missing, on_missing)

    section_ordinals: Mapping[str, int] | None = None
    fills = []
    for entry in entries:
        field_id = entry["field_id"]
        value = content.get(field_id)
        if value is None:
            value = fallback.get(field_id)
            if value is None:
                continue
        if "section_index" not in entry and section_ordinals is None:
            section_ordinals = _section_ordinals(template_dir / "source.hwpx")
        fills.append(
            HwpxTableCellFill(
                section=_table_cell_section_index(entry, section_ordinals),
                table=int(entry["table"]),
                row=int(entry["row"]),
                col=int(entry["col"]),
                value=str(value),
            )
        )
    return fills, filled, missing


def _table_cell_section_index(
    field: Mapping[str, JsonValue],
    section_ordinals: Mapping[str, int] | None,
) -> int:
    if "section_index" in field:
        return int(field["section_index"])
    section = field.get("section")
    if not isinstance(section, str):
        raise HwpxTemplateRenderError(
            "table-cell field requires a section or section_index"
        )
    if section_ordinals is None:
        raise HwpxTemplateRenderError(
            "table-cell field without section_index requires source HWPX sections"
        )
    try:
        return section_ordinals[f"Contents/{section}"]
    except KeyError as exc:
        raise HwpxTemplateRenderError(
            f"table-cell field references a section missing from HWPX: {section}"
        ) from exc


def _section_ordinals(package_path: Path) -> dict[str, int]:
    with zipfile.ZipFile(package_path) as package:
        sections = sorted(
            (
                name
                for name in package.namelist()
                if _SECTION_PART_RE.fullmatch(name)
            ),
            key=_section_part_number,
        )
    return {section: index for index, section in enumerate(sections)}


def _section_part_number(path: str) -> int:
    match = re.search(r"section(\d+)\.xml$", path, re.IGNORECASE)
    if match is None:
        raise HwpxTemplateRenderError(f"cannot resolve section number from {path!r}")
    return int(match.group(1))


def _repeat_separator(
    xml: str,
    paragraph_spans: Mapping[int, tuple[int, int]],
    source_level: int,
) -> str:
    separator_start = paragraph_spans[source_level][1]
    following_starts = [
        span[0]
        for span in paragraph_spans.values()
        if span[0] > separator_start
    ]
    if not following_starts:
        raise HwpxTemplateRenderError(
            f"repeat separator after level {source_level} was not found"
        )

    between = xml[separator_start : min(following_starts)]
    candidates = list(re.finditer(r"<hp:p\b.*?</hp:p>", between, re.DOTALL))
    if (
        len(candidates) != 1
        or between[: candidates[0].start()].strip()
        or between[candidates[0].end() :].strip()
    ):
        raise HwpxTemplateRenderError(
            f"repeat separator after level {source_level} "
            "must be one safe blank paragraph"
        )

    separator = candidates[0].group(0)
    remainder = _REPEAT_SEPARATOR_ELEMENT_RE.sub("", separator)
    if unescape(remainder).strip():
        raise HwpxTemplateRenderError(
            f"repeat separator after level {source_level} "
            "must be one safe blank paragraph"
        )
    return separator


@dataclass(frozen=True, slots=True)
class _RepeatSource:
    paragraphs: dict[int, str]
    paragraph_spans: dict[int, tuple[int, int]]
    separators: dict[int, str]


def _load_repeat_source(
    xml: str,
    name: str,
    block: RepeatBlock,
) -> _RepeatSource:
    paragraphs: dict[int, str] = {}
    paragraph_spans: dict[int, tuple[int, int]] = {}
    for level, (field_id, _) in block.levels.items():
        pattern = re.compile(
            rf"<hp:p\b[^>]*>(?:(?!<hp:p\b).)*?"
            rf"\{{\{{{re.escape(field_id)}\}}\}}"
            rf"(?:(?!<hp:p\b).)*?</hp:p>",
            re.DOTALL,
        )
        matches = list(pattern.finditer(xml))
        if len(matches) != 1:
            raise HwpxTemplateRenderError(
                f"repeat block {name!r} requires one paragraph for {field_id!r}"
            )
        paragraphs[level] = matches[0].group(0)
        paragraph_spans[level] = matches[0].span()

    separator_source_levels = set(block.item_separator_levels)
    if block.section_transition is not None:
        separator_source_levels.add(block.section_transition[1])
    separators = {
        level: _repeat_separator(xml, paragraph_spans, level)
        for level in separator_source_levels
    }
    return _RepeatSource(paragraphs, paragraph_spans, separators)


def _render_repeat_items(
    items: list[JsonValue],
    block: RepeatBlock,
    source: _RepeatSource,
) -> tuple[str, set[str]]:
    rendered: list[str] = []
    filled: set[str] = set()
    next_number = 1
    for index, item in enumerate(items):
        level, text = item
        field_id, prefix = block.levels[level]
        if level == block.numbered_level:
            prefix = f"{next_number}. {prefix}"
            next_number += 1
        placeholder = "{{" + field_id + "}}"
        rendered.append(
            source.paragraphs[level].replace(
                placeholder,
                escape(prefix + text),
                1,
            )
        )
        filled.add(field_id)
        if index == len(items) - 1:
            continue

        next_level = items[index + 1][0]
        separator_level: int | None = None
        if block.section_transition is not None:
            to_level, source_level = block.section_transition
            if next_level == to_level:
                separator_level = source_level
        if separator_level is None and level in block.item_separator_levels:
            separator_level = level
        if separator_level is not None:
            rendered.append(source.separators[separator_level])
    return "".join(rendered), filled


def _repeat_replacement_span(
    xml: str,
    name: str,
    source: _RepeatSource,
) -> tuple[int, int]:
    start = min(span[0] for span in source.paragraph_spans.values())
    end = max(span[1] for span in source.paragraph_spans.values())
    # 이 구간은 통째로 대체되므로 지워도 되는 것(레벨 문단·빈 줄)만 있어야 한다.
    for gap in re.finditer(r"<hp:p\b.*?</hp:p>", xml[start:end], re.DOTALL):
        paragraph = gap.group(0)
        if paragraph in source.paragraphs.values():
            continue
        text = re.sub(r"<[^>]+>", "", paragraph).strip()
        if text or _REPEAT_OBJECT_RE.search(paragraph):
            raise HwpxTemplateRenderError(
                f"repeat block {name!r} would delete content between its "
                f"level paragraphs: {text or 'object'!r}"
            )
    return start, end


def render_repeat_block(
    xml: str,
    content: Mapping[str, JsonValue],
    blocks: Mapping[str, RepeatBlock],
) -> tuple[str, set[str], list[tuple[int, int, int]]]:
    """Expand each repeat block. Also reports the paragraph ranges it rebuilt.

    Each range is ``(source paragraph index, source paragraph count, rendered
    paragraph count)`` in the *template's* paragraph numbering, so the layout
    contract can follow anchors across an expansion.
    """
    filled: set[str] = set()
    rewritten: list[tuple[int, int, int]] = []
    for name, block in blocks.items():
        items = content.get(block.anchor)
        if not isinstance(items, list):
            continue

        source = _load_repeat_source(xml, name, block)
        rendered, block_filled = _render_repeat_items(items, block, source)
        start, end = _repeat_replacement_span(xml, name, source)
        current_start = _paragraph_count_in(xml[:start])
        # 앞서 확장한 블록이 이미 문단을 늘렸다면 그만큼 빼야 원본 좌표가 된다.
        source_start = current_start - sum(
            rendered_count - source_count
            for previous_start, source_count, rendered_count in rewritten
            if previous_start < current_start
        )
        rewritten.append(
            (
                source_start,
                _paragraph_count_in(xml[start:end]),
                _paragraph_count_in(rendered),
            )
        )
        xml = xml[:start] + rendered + xml[end:]
        filled.update(block_filled)

    return xml, filled, sorted(rewritten)


def _paragraph_count_in(xml: str) -> int:
    return len(_PARAGRAPH_START_RE.findall(xml))


def _validate_fit_constraints(
    template_dir: Path,
    content: Mapping[str, JsonValue],
    constraints: Mapping[str, FitConstraint],
) -> None:
    if not constraints:
        return

    roots = [
        ElementTree.fromstring(path.read_bytes())
        for path in sorted(
            (template_dir / "template").glob("section*.template.xml")
        )
    ]
    header = ElementTree.fromstring(
        (template_dir / "template" / "header.xml").read_bytes()
    )
    for field_id in constraints:
        value = content.get(field_id)
        if value is None:
            continue
        if not isinstance(value, str):
            raise HwpxTemplateRenderError(
                f"field {field_id!r} "
                "must be a string"
            )

        placeholder = "{{" + field_id + "}}"
        cells = [
            cell
            for root in roots
            for cell in root.findall(".//hp:tc", _XML_NAMESPACES)
            if any(
                placeholder in (node.text or "")
                for node in cell.findall(".//hp:t", _XML_NAMESPACES)
            )
        ]
        if len(cells) != 1:
            raise HwpxTemplateRenderError(
                f"fit constraint for {field_id!r} requires one source cell"
            )

        cell = cells[0]
        paragraphs = [
            paragraph
            for paragraph in cell.findall(".//hp:p", _XML_NAMESPACES)
            if any(
                placeholder in (node.text or "")
                for node in paragraph.findall(".//hp:t", _XML_NAMESPACES)
            )
        ]
        if len(paragraphs) != 1:
            raise HwpxTemplateRenderError(
                f"fit constraint for {field_id!r} requires one source paragraph"
            )
        paragraph = paragraphs[0]
        paragraph_text = "".join(
            node.text or ""
            for node in paragraph.findall(".//hp:t", _XML_NAMESPACES)
        )
        if paragraph_text.count(placeholder) != 1:
            raise HwpxTemplateRenderError(
                f"fit constraint for {field_id!r} requires one placeholder"
            )
        full_text = paragraph_text.replace(placeholder, value, 1)

        size = cell.find("./hp:cellSz", _XML_NAMESPACES)
        margin = cell.find("./hp:cellMargin", _XML_NAMESPACES)
        if size is None or margin is None:
            raise HwpxTemplateRenderError(
                f"fit constraint for {field_id!r} requires cell size and margins"
            )
        available_width = (
            int(size.attrib["width"])
            - int(margin.attrib["left"])
            - int(margin.attrib["right"])
        )

        runs = [
            run
            for run in paragraph.findall("./hp:run", _XML_NAMESPACES)
            if run.find("./hp:t", _XML_NAMESPACES) is not None
        ]
        char_pr_ids = {run.get("charPrIDRef") for run in runs}
        if len(char_pr_ids) != 1 or None in char_pr_ids:
            raise HwpxTemplateRenderError(
                f"fit constraint for {field_id!r} requires one text style"
            )
        char_pr_id = next(iter(char_pr_ids))
        measured_width = _measure_text_hwpunit(header, char_pr_id, full_text)
        if measured_width > available_width:
            raise HwpxTemplateRenderError(
                f"field {field_id!r} "
                "does not fit in one line of the source cell"
            )


def _measure_text_hwpunit(
    header: ElementTree.Element,
    char_pr_id: str,
    text: str,
) -> float:
    char_pr = header.find(
        f".//hh:charPr[@id='{char_pr_id}']",
        _XML_NAMESPACES,
    )
    if char_pr is None:
        raise HwpxTemplateRenderError(
            f"source character style {char_pr_id!r} was not found"
        )

    font_ref = char_pr.find("./hh:fontRef", _XML_NAMESPACES)
    ratio = char_pr.find("./hh:ratio", _XML_NAMESPACES)
    spacing = char_pr.find("./hh:spacing", _XML_NAMESPACES)
    if font_ref is None or ratio is None or spacing is None:
        raise HwpxTemplateRenderError(
            f"source character style {char_pr_id!r} lacks font metrics"
        )
    font_ids = set(font_ref.attrib.values())
    ratios = {int(value) for value in ratio.attrib.values()}
    spacings = {int(value) for value in spacing.attrib.values()}
    if len(font_ids) != 1 or len(ratios) != 1 or len(spacings) != 1:
        raise HwpxTemplateRenderError(
            f"source character style {char_pr_id!r} uses mixed script metrics"
        )

    font_id = next(iter(font_ids))
    font_node = header.find(
        f".//hh:fontface[@lang='HANGUL']/hh:font[@id='{font_id}']",
        _XML_NAMESPACES,
    )
    if font_node is None or not font_node.get("face"):
        raise HwpxTemplateRenderError(
            f"source font {font_id!r} was not found"
        )
    face = font_node.attrib["face"]
    font_file = _FSS_FONT_FILES.get(face)
    if font_file is None:
        raise HwpxTemplateRenderError(
            f"source font {face!r} has no width metric mapping"
        )
    windows_dir = Path(os.environ.get("WINDIR", "C:/Windows"))
    font_path = windows_dir / "Fonts" / font_file
    if not font_path.is_file():
        raise HwpxTemplateRenderError(
            f"source font file for {face!r} was not found"
        )

    # 맑은 고딕에 없는 ☑·⇨는 Windows 기호 대체 글꼴 폭으로 계산한다.
    fallback_path = windows_dir / "Fonts" / _FSS_SYMBOL_FALLBACK
    if not fallback_path.is_file():
        raise HwpxTemplateRenderError(
            "source symbol fallback font was not found"
        )

    with (
        TTFont(font_path, lazy=True) as font,
        TTFont(fallback_path, lazy=True) as fallback,
    ):
        cmap = font.getBestCmap()
        fallback_cmap = fallback.getBestCmap()
        if cmap is None:
            raise HwpxTemplateRenderError(
                f"source font {face!r} has no Unicode character map"
            )
        if fallback_cmap is None:
            raise HwpxTemplateRenderError(
                "source symbol fallback font has no Unicode character map"
            )
        metrics = font["hmtx"].metrics
        fallback_metrics = fallback["hmtx"].metrics
        units_per_em = font["head"].unitsPerEm
        fallback_units_per_em = fallback["head"].unitsPerEm
        glyph_width = 0.0
        for character in text:
            glyph = cmap.get(ord(character))
            if glyph is not None:
                glyph_width += metrics[glyph][0] / units_per_em
                continue
            fallback_glyph = fallback_cmap.get(ord(character))
            if fallback_glyph is None:
                raise HwpxTemplateRenderError(
                    f"source font {face!r} cannot measure {character!r}"
                )
            glyph_width += (
                fallback_metrics[fallback_glyph][0]
                / fallback_units_per_em
            )

    height = int(char_pr.attrib["height"])
    ratio_percent = next(iter(ratios))
    spacing_percent = next(iter(spacings))
    # charPr height는 13pt를 1300으로 저장하므로 결과가 바로 HWPUNIT가 된다.
    glyph_width *= height * ratio_percent / 100
    character_spacing = (
        max(len(text) - 1, 0)
        * height
        * spacing_percent
        / 100
    )
    return glyph_width + character_spacing


def _fill_xml(
    xml: str,
    content: Mapping[str, JsonValue],
    filled: set[str],
    missing: set[str],
) -> str:
    def replace(match: re.Match) -> str:
        field_id = match.group(1)
        value = content.get(field_id)
        if value is not None:
            filled.add(field_id)
            return escape(str(value))
        missing.add(field_id)
        return match.group(0)  # keep {{field_id}} unfilled (never invented)

    return _PLACEHOLDER_RE.sub(replace, xml)


def _ensure_hwpunitchar_namespace(payload: bytes) -> bytes:
    if _HWPUNITCHAR_DECLARATION_RE.search(payload):
        return payload
    return _HWPML_ROOT_START_RE.sub(
        lambda match: match.group(0) + b" " + _HWPUNITCHAR_DECLARATION,
        payload,
        count=1,
    )
