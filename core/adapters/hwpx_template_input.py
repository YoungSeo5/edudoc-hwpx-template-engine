from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .hwpx_alias_map import (
    AliasMap,
    BlockMetadataSource,
    FieldMetadataSource,
    FitConstraint,
    JsonValue,
    MetadataContract,
    RepeatBlock,
    RequestedAtMetadataSource,
    load_alias_map,
)
from .hwpx_fss_director_report import (
    FssPackageMetadata,
    build_fss_package_metadata,
)


class HwpxTemplateRenderError(RuntimeError):
    """Raised when a template cannot be rendered."""


class HwpxTemplateInputError(HwpxTemplateRenderError):
    pass


@dataclass(frozen=True, slots=True)
class RenderExecutionContext:
    requester_name: str
    requested_at: datetime

    def __post_init__(self) -> None:
        if not self.requester_name.strip():
            raise HwpxTemplateRenderError(
                "execution context requires requester_name"
            )
        if self.requested_at.utcoffset() != timedelta(0):
            raise HwpxTemplateRenderError(
                "execution context requested_at must be a UTC datetime"
            )


@dataclass(frozen=True, slots=True)
class ResolvedMetadata:
    title: str
    subject: str
    description: str
    report_date: str
    keywords: str


@dataclass(frozen=True, slots=True)
class ResolvedRenderPlan:
    field_values: dict[str, JsonValue]
    repeat_values: dict[str, list[JsonValue]]
    repeat_blocks: dict[str, RepeatBlock]
    fit_constraints: dict[str, FitConstraint]


@dataclass(frozen=True, slots=True)
class ResolvedTemplateContent:
    template_id: str | None
    placeholder_map: Mapping[str, JsonValue]
    render_plan: ResolvedRenderPlan
    unknown_keys: tuple[str, ...]
    metadata: ResolvedMetadata | None


@dataclass(frozen=True, slots=True)
class PreparedRenderContent:
    """Input for final document generation from an approved template.

    ``package_metadata`` is required: a finished document always carries the
    template's declared document metadata. A template still being built has no
    metadata contract and cannot be prepared — round-trip it with
    ``render_candidate_roundtrip`` instead.
    """

    template_id: str | None
    placeholder_map: Mapping[str, JsonValue]
    render_plan: ResolvedRenderPlan
    unknown_keys: tuple[str, ...]
    package_metadata: FssPackageMetadata


def load_placeholder_map(template_dir: Path | str) -> Mapping[str, JsonValue]:
    path = Path(template_dir) / "placeholder_map.json"
    if not path.is_file():
        raise HwpxTemplateInputError(
            f"placeholder_map.json not found in {template_dir}"
        )
    raw: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise HwpxTemplateInputError(
            f"placeholder_map.json root must be an object: {path}"
        )
    return raw


def _resolve_metadata(
    flattened: Mapping[str, JsonValue],
    alias_map: AliasMap,
    contract: MetadataContract,
    repeat_values: Mapping[str, list[JsonValue]],
    requested_at: datetime | None,
) -> ResolvedMetadata:
    """Read document metadata from the already-flattened input.

    The values are read before the choice and text rules run, so metadata keeps
    the human-authored option (``언론보도``) rather than the rendered checkbox
    line.
    """

    def read_field(alias: str, *, required: bool = False) -> str:
        value = flattened.get(alias)
        if value is None and alias not in alias_map.choices:
            value = flattened.get(alias_map.aliases[alias])
        if value is None and not required:
            return ""
        if not isinstance(value, str) or (required and not value.strip()):
            requirement = "a non-empty string" if required else "a string"
            raise HwpxTemplateInputError(
                f"metadata field {alias!r} must be {requirement}"
            )
        return value

    def resolve_source(
        source: FieldMetadataSource
        | BlockMetadataSource
        | RequestedAtMetadataSource,
    ) -> list[str]:
        if isinstance(source, FieldMetadataSource):
            value = read_field(source.alias)
            return [value + source.suffix] if value else []
        if isinstance(source, BlockMetadataSource):
            block = alias_map.blocks[source.block]
            return [
                item[1]
                for item in repeat_values.get(block.anchor, [])
                if item[0] == source.level and item[1]
            ]
        if requested_at is None:
            raise HwpxTemplateInputError(
                "metadata requested_at requires execution_context"
            )
        return [requested_at.isoformat().replace("+00:00", "Z")]

    def one_value(
        source: FieldMetadataSource | RequestedAtMetadataSource,
        name: str,
    ) -> str:
        values = resolve_source(source)
        if len(values) != 1 or not values[0].strip():
            raise HwpxTemplateInputError(
                f"metadata {name} must resolve to one non-empty string"
            )
        return values[0]

    def optional_value(source: FieldMetadataSource) -> str:
        values = resolve_source(source)
        if not values:
            return ""
        if len(values) != 1:
            raise HwpxTemplateInputError(
                "metadata description must resolve to at most one string"
            )
        return values[0]

    subject_values = resolve_source(contract.subject)
    keyword_values = [
        value
        for source in contract.keywords
        for value in resolve_source(source)
    ]
    return ResolvedMetadata(
        title=one_value(contract.title, "title"),
        subject=contract.subject_separator.join(subject_values),
        description=optional_value(contract.description),
        report_date=one_value(contract.report_date, "report_date"),
        keywords=contract.keyword_separator.join(keyword_values),
    )


def resolve_hwpx_template_input(
    template_dir: Path | str,
    content: Mapping[str, JsonValue],
    *,
    requested_at: datetime | None = None,
    resolve_metadata: bool = True,
) -> ResolvedTemplateContent:
    """Resolve human input into field IDs and separately held repeat values."""
    placeholder_map = load_placeholder_map(template_dir)
    template_id_raw = placeholder_map.get("template_id")
    template_id = template_id_raw if isinstance(template_id_raw, str) else None
    fields_raw = placeholder_map.get("fields", [])
    field_ids = frozenset(
        entry["field_id"]
        for entry in fields_raw
        if isinstance(entry, dict) and isinstance(entry.get("field_id"), str)
    )
    alias_map = load_alias_map(
        template_dir,
        field_ids=field_ids,
        template_id=template_id,
    )
    if alias_map is None:
        return ResolvedTemplateContent(
            template_id=template_id,
            placeholder_map=placeholder_map,
            render_plan=ResolvedRenderPlan(
                field_values=dict(content),
                repeat_values={},
                repeat_blocks={},
                fit_constraints={},
            ),
            unknown_keys=(),
            metadata=None,
        )

    flattened = alias_map.flatten_content(content, field_ids)
    field_values, unknown_keys = alias_map.resolve_flattened(flattened, field_ids)
    repeat_values: dict[str, list[JsonValue]] = {}
    for block in alias_map.blocks.values():
        value = field_values.pop(block.anchor, None)
        if value is None:
            continue
        if isinstance(value, list):
            repeat_values[block.anchor] = value
        else:
            field_values[block.anchor] = value

    metadata = (
        _resolve_metadata(
            flattened,
            alias_map,
            alias_map.metadata,
            repeat_values,
            requested_at,
        )
        if resolve_metadata and alias_map.metadata is not None
        else None
    )
    return ResolvedTemplateContent(
        template_id=template_id,
        placeholder_map=placeholder_map,
        render_plan=ResolvedRenderPlan(
            field_values=field_values,
            repeat_values=repeat_values,
            repeat_blocks={
                block.anchor: block for block in alias_map.blocks.values()
            },
            fit_constraints=alias_map.fit_constraints,
        ),
        unknown_keys=tuple(unknown_keys),
        metadata=metadata,
    )


def prepare_hwpx_template_input(
    template_dir: Path | str,
    content: Mapping[str, JsonValue],
    *,
    execution_context: RenderExecutionContext | None = None,
) -> PreparedRenderContent:
    """Finish input interpretation before visible HWPX rendering starts.

    Final document generation is only possible for a template whose
    ``alias_map.json`` declares a metadata contract, and only with an execution
    context to attribute the document to. Neither is inferred: a template that
    declares no contract is refused rather than rendered with partial metadata.
    """
    resolved = resolve_hwpx_template_input(
        template_dir,
        content,
        requested_at=(
            execution_context.requested_at
            if execution_context is not None
            else None
        ),
    )
    if resolved.metadata is None:
        raise HwpxTemplateInputError(
            f"template {resolved.template_id!r} declares no alias_map metadata "
            "contract, so it cannot produce a final document; round-trip a "
            "template that is still being built with render_candidate_roundtrip"
        )
    if execution_context is None:
        raise HwpxTemplateInputError(
            f"template {resolved.template_id!r} requires execution_context "
            "to record the requester and request time"
        )

    return PreparedRenderContent(
        template_id=resolved.template_id,
        placeholder_map=resolved.placeholder_map,
        render_plan=resolved.render_plan,
        unknown_keys=resolved.unknown_keys,
        package_metadata=build_fss_package_metadata(
            resolved.metadata,
            requester_name=execution_context.requester_name,
            requested_at=execution_context.requested_at,
        ),
    )
