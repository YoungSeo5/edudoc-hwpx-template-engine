from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .hwpx_alias_map import (
    AliasMap,
    BlockMetadataSource,
    FieldMetadataSource,
    JsonValue,
    MetadataContract,
    RequestedAtMetadataSource,
)


class MetadataResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedMetadata:
    title: str
    subject: str
    description: str
    report_date: str
    keywords: str


def resolve_metadata(
    flattened: Mapping[str, JsonValue],
    alias_map: AliasMap,
    contract: MetadataContract,
    repeat_values: Mapping[str, list[JsonValue]],
    requested_at: datetime | None,
) -> ResolvedMetadata:
    def read_field(alias: str, *, required: bool = False) -> str:
        value = flattened.get(alias)
        if value is None and alias not in alias_map.choices:
            value = flattened.get(alias_map.aliases[alias])
        if value is None and not required:
            return ""
        if not isinstance(value, str) or (required and not value.strip()):
            requirement = "a non-empty string" if required else "a string"
            raise MetadataResolutionError(f"metadata field {alias!r} must be {requirement}")
        return value

    def resolve_source(
        source: FieldMetadataSource | BlockMetadataSource | RequestedAtMetadataSource,
    ) -> list[str]:
        match source:
            case FieldMetadataSource():
                value = read_field(source.alias)
                return [value + source.suffix] if value else []
            case BlockMetadataSource():
                block = alias_map.blocks[source.block]
                return [
                    item[1]
                    for item in repeat_values.get(block.anchor, [])
                    if item[0] == source.level and item[1]
                ]
            case RequestedAtMetadataSource():
                if requested_at is None:
                    raise MetadataResolutionError("metadata requested_at requires execution_context")
                return [requested_at.isoformat().replace("+00:00", "Z")]

    def one_value(source: FieldMetadataSource | RequestedAtMetadataSource, name: str) -> str:
        values = resolve_source(source)
        if len(values) != 1 or not values[0].strip():
            raise MetadataResolutionError(f"metadata {name} must resolve to one non-empty string")
        return values[0]

    def optional_value(source: FieldMetadataSource) -> str:
        values = resolve_source(source)
        if not values:
            return ""
        if len(values) != 1:
            raise MetadataResolutionError("metadata description must resolve to at most one string")
        return values[0]

    subject_values = resolve_source(contract.subject)
    keyword_values = [value for source in contract.keywords for value in resolve_source(source)]
    return ResolvedMetadata(
        title=one_value(contract.title, "title"),
        subject=contract.subject_separator.join(subject_values),
        description=optional_value(contract.description),
        report_date=one_value(contract.report_date, "report_date"),
        keywords=contract.keyword_separator.join(keyword_values),
    )
