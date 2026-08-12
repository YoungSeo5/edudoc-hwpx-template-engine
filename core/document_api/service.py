from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from core.adapters.hwpx_alias_map import AliasMap, JsonValue, load_alias_map
from core.adapters.hwpx_source_content_mapper import map_source_to_content
from core.adapters.hwpx_source_input import read_source_as_markdown
from core.adapters.hwpx_template_input import (
    PreparedRenderContent,
    RenderExecutionContext,
    load_placeholder_map,
    prepare_hwpx_template_input,
)
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderResult,
    orchestrate_hwpx_render,
)
from core.templates.models import TemplateCandidate
from core.templates.registry import TemplateRegistry

_TEMPLATE_ROOT: Final = (
    Path(__file__).resolve().parents[2] / "templates" / "institutions"
)


class HwpxUnresolvedFieldsError(HwpxTemplateRenderError):
    """Raised when source mapping leaves fields unresolved.

    A field the deterministic source mapper could not fill stays ``확인 필요``
    (see ``core.adapters.hwpx_source_content_mapper``). Rendering that value
    into a final approved-template document would silently ship a placeholder
    as if it were real content, so final render is refused here instead.
    """

    def __init__(self, unresolved_fields: list[str]) -> None:
        self.unresolved_fields = unresolved_fields
        super().__init__(
            "source mapping left unresolved fields; refusing final render: "
            f"{unresolved_fields}"
        )


def list_approved_templates() -> tuple[TemplateCandidate, ...]:
    registry = TemplateRegistry(_TEMPLATE_ROOT)
    approved: list[TemplateCandidate] = []
    for path in sorted(_TEMPLATE_ROOT.glob("*/*/template.json")):
        relative = path.relative_to(_TEMPLATE_ROOT)
        institution, document_type = relative.parts[:2]
        candidate = registry.find(institution, document_type)
        if candidate is not None and candidate.reference_format == "hwpx":
            approved.append(candidate)
    return tuple(approved)


def get_template_contract(
    institution: str,
    document_type: str,
) -> tuple[Mapping[str, JsonValue], AliasMap | None]:
    template_dir = _approved_template_dir(institution, document_type)
    placeholder_map = load_placeholder_map(template_dir)
    fields_raw = placeholder_map.get("fields", [])
    field_ids = frozenset(
        entry["field_id"]
        for entry in fields_raw
        if isinstance(entry, dict) and isinstance(entry.get("field_id"), str)
    )
    template_id_raw = placeholder_map.get("template_id")
    template_id = template_id_raw if isinstance(template_id_raw, str) else None
    return (
        placeholder_map,
        load_alias_map(
            template_dir,
            field_ids=field_ids,
            template_id=template_id,
        ),
    )


def validate_template_content(
    institution: str,
    document_type: str,
    content: Mapping[str, JsonValue],
    execution_context: RenderExecutionContext,
) -> PreparedRenderContent:
    return prepare_hwpx_template_input(
        _approved_template_dir(institution, document_type),
        content,
        execution_context=execution_context,
    )


def render_approved_document(
    institution: str,
    document_type: str,
    content: Mapping[str, JsonValue],
    output_path: Path,
    execution_context: RenderExecutionContext,
) -> RenderResult:
    return orchestrate_hwpx_render(
        _approved_template_dir(institution, document_type),
        content,
        output_path,
        execution_context=execution_context,
    )


def render_document_from_source(
    institution: str,
    document_type: str,
    source_path: Path | str,
    output_path: Path,
    execution_context: RenderExecutionContext,
) -> RenderResult:
    """Render an approved document from a source content file (.md/.txt/.hwpx).

    Reads ``source_path`` as Markdown, maps it onto the approved template's
    ``placeholder_map.json`` (with ``alias_map.json`` when declared), and
    refuses to render if any field is left unresolved
    (``HwpxUnresolvedFieldsError``). This is stricter than
    ``render_approved_document``, which renders whatever content it is given.
    """
    placeholder_map, alias_map = get_template_contract(institution, document_type)
    markdown = read_source_as_markdown(source_path)
    mapping = map_source_to_content(markdown, placeholder_map, alias_map)
    if mapping.unresolved_fields:
        raise HwpxUnresolvedFieldsError(mapping.unresolved_fields)
    return render_approved_document(
        institution,
        document_type,
        mapping.content,
        output_path,
        execution_context,
    )


def _approved_template_dir(institution: str, document_type: str) -> Path:
    registry = TemplateRegistry(_TEMPLATE_ROOT)
    candidate = registry.find(institution, document_type)
    if candidate is None:
        raise HwpxTemplateRenderError(
            "approved institution template not found: "
            f"{institution} / {document_type}"
        )
    return registry.template_path(institution, document_type).parent
