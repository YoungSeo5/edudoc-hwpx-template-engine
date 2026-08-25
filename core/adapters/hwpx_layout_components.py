"""Expand document-family component declarations into authoring sections."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_SUPPORTED_COMPONENTS = frozenset(
    {
        "masthead",
        "title_block",
        "header_info",
        "section",
        "bullet_list",
        "key_value_table",
        "status_table",
        "callout",
        "footer_note",
    }
)
_TABLE_COMPONENTS = frozenset({"header_info", "key_value_table", "status_table"})
_BODY_COMPONENTS = frozenset({"section", "bullet_list", "callout", "footer_note"})


class HwpxLayoutComponentError(RuntimeError):
    """Raised when a family recipe or component declaration is invalid."""


def expand_family_components(
    family: str, recipe_path: Path, components: object
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Validate a family recipe and lower its generic components to sections."""
    recipe = _load_recipe(recipe_path, family)
    if not isinstance(components, list) or not components:
        raise HwpxLayoutComponentError("template_spec.components must be a non-empty list")
    component_types: list[str] = []
    sections: list[dict[str, Any]] = []
    defaults = recipe["component_defaults"]
    for index, raw_component in enumerate(components):
        if not isinstance(raw_component, dict):
            raise HwpxLayoutComponentError(f"components[{index}] must be an object")
        component_type = raw_component.get("type")
        if not isinstance(component_type, str) or component_type not in _SUPPORTED_COMPONENTS:
            raise HwpxLayoutComponentError(f"components[{index}].type is not a supported layout component")
        component_types.append(component_type)
        values = {**defaults.get(component_type, {}), **raw_component}
        if component_type == "masthead":
            continue
        if component_type == "title_block":
            sections.append({**values, "type": "title"})
        elif component_type == "header_info":
            sections.extend(_expand_header_info(index, values))
        elif component_type == "status_table" and values.get("display") == "section":
            rows = values.get("rows")
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                raise HwpxLayoutComponentError(
                    f"components[{index}].rows must contain one status row when display='section'"
                )
            row = rows[0]
            sections.append(
                {
                    "type": "body_section",
                    "heading_style": values.get("heading_style"),
                    "heading_style_override": values.get("heading_style_override", {}),
                    "body_style": values.get("body_style"),
                    "body_style_override": values.get("body_style_override", {}),
                    "heading_element_id": row.get("label_element_id"),
                    "content_element_id": row.get("value_element_id"),
                    "heading_text": row.get("label"),
                    "field_id": row.get("field_id"),
                    "sample_value": row.get("sample_value"),
                }
            )
        elif component_type == "status_table" and values.get("display") == "simple_table":
            sections.append({**values, "type": "simple_table"})
        elif component_type in _TABLE_COMPONENTS:
            sections.append({**values, "type": "info_table"})
        elif component_type in _BODY_COMPONENTS:
            sections.append({**values, "type": "body_section"})
    missing = [name for name in recipe["required_components"] if name not in component_types]
    if missing:
        raise HwpxLayoutComponentError(f"template_spec.components is missing required family component(s): {missing}")
    return sections, tuple(component_types)


def _expand_header_info(index: int, values: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups = values.get("row_groups")
    if groups is None:
        return [{**values, "type": "info_table"}]
    rows = values.get("rows")
    if not isinstance(rows, list):
        raise HwpxLayoutComponentError(f"components[{index}].rows must be a list")
    if not isinstance(groups, list) or not groups:
        raise HwpxLayoutComponentError(f"components[{index}].row_groups must be a non-empty list")
    group_definitions: list[dict[str, Any]] = []
    row_counts: list[int] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise HwpxLayoutComponentError(
                f"components[{index}].row_groups[{group_index}] must be an object"
            )
        row_count = group.get("row_count")
        if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count <= 0:
            raise HwpxLayoutComponentError(
                f"components[{index}].row_groups[{group_index}].row_count must be a positive integer"
            )
        group_definitions.append(group)
        row_counts.append(row_count)
    if sum(row_counts) != len(rows):
        raise HwpxLayoutComponentError(
            f"components[{index}].row_groups must consume every metadata row exactly once"
        )
    offset = 0
    sections: list[dict[str, Any]] = []
    for group, row_count in zip(group_definitions, row_counts, strict=True):
        group_rows = rows[offset:offset + row_count]
        if len(group_rows) != row_count:
            raise HwpxLayoutComponentError(
                f"components[{index}].row_groups does not match the declared metadata rows"
            )
        sections.append(
            {
                **values,
                **group,
                "type": "info_table",
                "rows": group_rows,
            }
        )
        offset += row_count
    if offset != len(rows):
        raise HwpxLayoutComponentError(
            f"components[{index}].row_groups does not consume every metadata row"
        )
    for section in sections:
        section.pop("row_groups", None)
        section.pop("row_count", None)
    return sections


def _load_recipe(path: Path, family: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HwpxLayoutComponentError(f"cannot read family recipe {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("family") != family:
        raise HwpxLayoutComponentError(f"family recipe {path} does not declare family {family!r}")
    defaults = raw.get("component_defaults", {})
    required = raw.get("required_components", [])
    if not isinstance(defaults, dict) or not isinstance(required, list):
        raise HwpxLayoutComponentError("family recipe requires component_defaults and required_components")
    return {"component_defaults": defaults, "required_components": required}
