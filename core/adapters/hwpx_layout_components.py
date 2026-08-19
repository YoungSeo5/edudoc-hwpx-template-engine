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
        elif component_type in _TABLE_COMPONENTS:
            sections.append({**values, "type": "info_table"})
        elif component_type in _BODY_COMPONENTS:
            sections.append({**values, "type": "body_section"})
    missing = [name for name in recipe["required_components"] if name not in component_types]
    if missing:
        raise HwpxLayoutComponentError(f"template_spec.components is missing required family component(s): {missing}")
    return sections, tuple(component_types)


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
