from __future__ import annotations

import json
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
from core.adapters.hwpx_template_authoring import (
    HwpxTemplateAuthoringError,
    load_template_spec,
)
from core.adapters.hancom_page_count import validate_native_page_count
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
    *,
    content_template_id: str,
) -> RenderResult:
    if not content_template_id:
        raise HwpxTemplateRenderError("content template_id is required for final rendering")
    template_dir = _approved_template_dir(
        institution,
        document_type,
        content_template_id=content_template_id,
    )
    expected_pages = _native_page_count_contract(template_dir)
    result = orchestrate_hwpx_render(
        template_dir,
        content,
        output_path,
        execution_context=execution_context,
    )
    if expected_pages is None:
        return result
    validation = validate_native_page_count(result.output, expected_pages)
    if not validation.passed:
        raise HwpxTemplateRenderError(
            "native page validation failed: "
            f"expected_pages={validation.expected_pages}, "
            f"observed_pages={validation.observed_pages}, "
            f"reason={validation.reason}"
        )
    return result


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
        content_template_id=_template_id_from_placeholder_map(placeholder_map),
    )


def _approved_template_dir(
    institution: str,
    document_type: str,
    *,
    content_template_id: str | None = None,
) -> Path:
    registry = TemplateRegistry(_TEMPLATE_ROOT)
    candidate = registry.find(institution, document_type)
    if candidate is None:
        raise HwpxTemplateRenderError(
            "approved institution template not found: "
            f"{institution} / {document_type}"
        )
    if content_template_id is not None and content_template_id != candidate.identity.template_id:
        raise HwpxTemplateRenderError(
            "template_id mismatch: "
            f"content={content_template_id!r}, "
            f"approved={candidate.identity.template_id!r}"
        )
    return registry.template_path(institution, document_type).parent


def _template_id_from_placeholder_map(placeholder_map: Mapping[str, JsonValue]) -> str:
    template_id = placeholder_map.get("template_id")
    if not isinstance(template_id, str) or not template_id:
        raise HwpxTemplateRenderError("approved template has no valid template_id")
    return template_id


def _native_page_count_contract(template_dir: Path) -> int | None:
    template_spec_path = template_dir / "template_spec.json"
    if not template_spec_path.is_file():
        return None
    try:
        spec = load_template_spec(template_spec_path)
    except (HwpxTemplateAuthoringError, OSError, ValueError) as exc:
        raise HwpxTemplateRenderError(
            f"cannot resolve approved native page-count contract: {exc}"
        ) from exc
    if not spec.family_recipe_path:
        return None
    recipe_path = Path(spec.family_recipe_path)
    try:
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HwpxTemplateRenderError(
            f"cannot read approved family recipe: {recipe_path} ({exc})"
        ) from exc
    if not isinstance(recipe, dict):
        raise HwpxTemplateRenderError(f"approved family recipe must be an object: {recipe_path}")
    native_page_count = recipe.get("native_page_count")
    if native_page_count is None:
        return None
    if (
        not isinstance(native_page_count, int)
        or isinstance(native_page_count, bool)
        or native_page_count <= 0
    ):
        raise HwpxTemplateRenderError(
            f"approved family recipe native_page_count must be a positive integer: {recipe_path}"
        )
    return native_page_count
