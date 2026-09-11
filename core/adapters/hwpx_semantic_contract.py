from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hwpx_template_authoring import (
    BodySection,
    ContentBoxSection,
    InfoTableSection,
    SimpleTableSection,
    TemplateSpec,
    TitleSection,
    load_template_spec,
)


class SemanticContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticElement:
    element_id: str
    role: str
    text: str | None
    field_id: str | None
    required: bool | None
    cardinality: str | None
    content_type: str | None
    item_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticContract:
    contract_id: str
    institution: str
    document_type: str
    elements: tuple[SemanticElement, ...]


@dataclass(frozen=True, slots=True)
class SemanticBinding:
    contract: SemanticContract
    placements: tuple[dict[str, str], ...]


def load_semantic_contract(path: Path | str) -> SemanticContract:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticContractError(f"cannot read semantic contract: {source} ({exc})") from exc
    if not isinstance(raw, dict):
        raise SemanticContractError("semantic contract root must be an object")
    if raw.get("semantic_contract_version") != "v1":
        raise SemanticContractError("semantic contract requires semantic_contract_version='v1'")
    contract_id = _required_string(raw, "contract_id")
    # Schema-required identity the runtime authoring path also enforces
    # (scripts/templates/author_hwpx_template.py cross-checks it against
    # TemplateRequest.request_id) but this loader never checked on its own.
    _required_string(raw, "template_request_id")
    institution = _required_string(raw, "institution")
    document_type = _required_string(raw, "document_type")
    entries = raw.get("elements")
    if not isinstance(entries, list) or not entries:
        raise SemanticContractError("semantic contract elements must be a non-empty list")
    elements = tuple(_parse_element(entry, index) for index, entry in enumerate(entries))
    _validate_unique(elements)
    return SemanticContract(contract_id, institution, document_type, elements)


def bind_semantic_contract(contract: SemanticContract, spec: TemplateSpec) -> SemanticBinding:
    if spec.semantic_contract_id != contract.contract_id:
        raise SemanticContractError(
            "template_spec semantic_contract_id does not match semantic contract contract_id"
        )
    by_element = {element.element_id: element for element in contract.elements}
    by_field = {element.field_id: element for element in contract.elements if element.field_id is not None}
    placements: list[dict[str, str]] = []
    for index, section in enumerate(spec.sections):
        match section:
            case TitleSection():
                placements.append(_fixed_placement(by_element, section.semantic_element_id, section.text, "FIXED_TEXT", index))
            case InfoTableSection():
                for row_index, row in enumerate(section.rows):
                    placements.append(_fixed_placement(by_element, row.label_element_id, row.label, "FIXED_LABEL", index, row_index))
                    placements.append(_content_placement(by_field, row.field_id, index, row_index))
            case SimpleTableSection():
                for header_index, (element_id, text) in enumerate(zip(section.header_element_ids, section.header, strict=True)):
                    placements.append(_fixed_placement(by_element, element_id, text, "FIXED_LABEL", index, header_index))
                placements.extend(
                    _collection_placement(by_field, section.collection_field_id, item_field, index, column_index)
                    for column_index, item_field in enumerate(section.item_fields)
                )
            case BodySection():
                if section.hierarchy_items:
                    for item_index, item in enumerate(section.hierarchy_items):
                        placement = _collection_placement(
                            by_field,
                            section.field_id,
                            section.hierarchy_item_field,
                            index,
                            item_index,
                        )
                        placement["prototype_level"] = str(item.level)
                        placements.append(placement)
                else:
                    if section.heading_text:
                        placements.append(_fixed_placement(by_element, section.heading_element_id, section.heading_text, "FIXED_LABEL", index))
                    placements.append(_content_placement(by_field, section.field_id, index))
            case ContentBoxSection():
                for item_index, box_item in enumerate(section.items):
                    placements.append(_content_placement(by_field, box_item.field_id, index, item_index))
    placed_elements = {placement["element_id"] for placement in placements}
    missing_required = [
        element.field_id
        for element in contract.elements
        if element.role == "CONTENT" and element.required and element.element_id not in placed_elements
    ]
    if missing_required:
        raise SemanticContractError(
            f"required semantic CONTENT field(s) are not placed by template_spec: {missing_required}"
        )
    missing_fixed = [
        element.element_id
        for element in contract.elements
        if element.role != "CONTENT" and element.element_id not in placed_elements
    ]
    if missing_fixed:
        raise SemanticContractError(
            f"semantic fixed element(s) are not placed by template_spec: {missing_fixed}"
        )
    return SemanticBinding(contract, tuple(placements))


def semantic_contract_payload(binding: SemanticBinding) -> dict[str, Any]:
    return {
        "semantic_contract_id": binding.contract.contract_id,
        "institution": binding.contract.institution,
        "document_type": binding.contract.document_type,
        "placements": list(binding.placements),
    }


def write_resolved_authoring_contract(resolved: object, output_path: Path | str) -> Path:
    output = Path(output_path)
    output.write_text(
        json.dumps(asdict(resolved), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def validate_candidate_field_identity(contract: SemanticContract, candidate_dir: Path | str) -> None:
    source = Path(candidate_dir) / "placeholder_map.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    fields = raw.get("fields") if isinstance(raw, dict) else None
    if not isinstance(fields, list):
        raise SemanticContractError("candidate placeholder_map.json requires a fields list")
    actual = {item.get("field_id") for item in fields if isinstance(item, dict) and isinstance(item.get("field_id"), str)}
    scalar_fields = {
        element.field_id
        for element in contract.elements
        if element.role == "CONTENT" and not element.item_fields
    }
    collection_fields = {
        element.field_id: set(element.item_fields)
        for element in contract.elements
        if element.role == "CONTENT" and element.item_fields
    }
    projected = {
        field_id
        for field_id in actual
        if any(field_id.startswith(f"{collection_id}[") for collection_id in collection_fields)
    }
    invalid_projected = {
        field_id
        for field_id in projected
        if not any(
            field_id.startswith(f"{collection_id}[") and field_id.rsplit(".", 1)[-1] in item_fields
            for collection_id, item_fields in collection_fields.items()
        )
    }
    missing_collections = {
        collection_id
        for collection_id in collection_fields
        if not any(field_id.startswith(f"{collection_id}[") for field_id in projected)
    }
    if actual - projected != scalar_fields or invalid_projected or missing_collections:
        raise SemanticContractError(
            f"candidate placeholder field IDs do not match semantic contract: scalar={sorted(scalar_fields)}, got={sorted(actual)}"
        )


def persist_candidate_contract_artifacts(staging_dir: Path | str, candidate_dir: Path | str) -> dict[str, str]:
    staging = Path(staging_dir)
    candidate = Path(candidate_dir)
    required = (
        "template_request.json",
        "semantic_contract.json",
        "template_spec.json",
        "institution_design.json",
        "institution_design.provenance.json",
        "resolved_authoring_contract.json",
        "separation_rules.json",
    )
    missing = [name for name in required if not (staging / name).is_file()]
    if missing:
        raise SemanticContractError(f"self-authored candidate is missing contract artifact(s): {missing}")
    semantic = load_semantic_contract(staging / "semantic_contract.json")
    bind_semantic_contract(semantic, load_template_spec(staging / "template_spec.json"))
    validate_candidate_field_identity(semantic, candidate)
    for name in required:
        shutil.copy2(staging / name, candidate / name)
    provenance = staging / "authoring_input.provenance.json"
    if provenance.is_file():
        shutil.copy2(provenance, candidate / provenance.name)
    family_recipe = staging / "family_recipe.json"
    if family_recipe.is_file():
        shutil.copy2(family_recipe, candidate / family_recipe.name)
    artifacts = {name.removesuffix(".json"): str(candidate / name) for name in required}
    if provenance.is_file():
        artifacts[provenance.name.removesuffix(".json")] = str(candidate / provenance.name)
    return artifacts


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SemanticContractError(f"semantic contract {key} must be a non-empty string")
    return value


def _parse_element(raw: object, index: int) -> SemanticElement:
    if not isinstance(raw, dict):
        raise SemanticContractError(f"semantic contract elements[{index}] must be an object")
    element_id = _required_string(raw, "element_id")
    role = raw.get("role")
    if role == "CONTENT":
        field_id = _required_string(raw, "field_id")
        required = raw.get("required")
        cardinality = raw.get("cardinality")
        content_type = raw.get("content_type")
        item_fields_raw = raw.get("item_fields", [])
        if not isinstance(required, bool) or cardinality not in {"one", "many"}:
            raise SemanticContractError(f"invalid CONTENT semantic element: {element_id}")
        if content_type == "object" and cardinality == "many" and isinstance(item_fields_raw, list) and item_fields_raw and all(isinstance(value, str) and value for value in item_fields_raw):
            return SemanticElement(element_id, role, None, field_id, required, cardinality, content_type, tuple(item_fields_raw))
        if content_type in {"text", "date", "choice"} and not item_fields_raw:
            return SemanticElement(element_id, role, None, field_id, required, cardinality, content_type)
        raise SemanticContractError(f"invalid CONTENT semantic element: {element_id}")
    if role not in {"FIXED_LABEL", "FIXED_TEXT"}:
        raise SemanticContractError(f"semantic element {element_id!r} has unsupported role {role!r}")
    return SemanticElement(element_id, role, _required_string(raw, "text"), None, None, None, None)


def _validate_unique(elements: tuple[SemanticElement, ...]) -> None:
    element_ids = [element.element_id for element in elements]
    if len(set(element_ids)) != len(element_ids):
        raise SemanticContractError("semantic contract has duplicate element_id")
    field_ids = [element.field_id for element in elements if element.field_id is not None]
    if len(set(field_ids)) != len(field_ids):
        raise SemanticContractError("semantic contract has duplicate CONTENT field_id")


def _fixed_placement(
    by_element: dict[str, SemanticElement],
    element_id: str,
    text: str,
    role: str,
    section_index: int,
    row_index: int | None = None,
) -> dict[str, str]:
    element = by_element.get(element_id)
    if element is None:
        raise SemanticContractError(f"template_spec references unknown semantic element {element_id!r}")
    if element.role != role:
        raise SemanticContractError(f"semantic role conflict for {element_id!r}: expected {role}, got {element.role}")
    if element.text != text:
        raise SemanticContractError(f"template_spec fixed text conflicts with semantic element {element_id!r}")
    placement = {"element_id": element_id, "role": role, "section_index": str(section_index)}
    if row_index is not None:
        placement["row_index"] = str(row_index)
    return placement


def _content_placement(
    by_field: dict[str, SemanticElement], field_id: str, section_index: int, row_index: int | None = None
) -> dict[str, str]:
    element = by_field.get(field_id)
    if element is None:
        raise SemanticContractError(f"template_spec CONTENT field_id is absent from semantic contract: {field_id!r}")
    placement = {"element_id": element.element_id, "role": "CONTENT", "field_id": field_id, "section_index": str(section_index)}
    if row_index is not None:
        placement["row_index"] = str(row_index)
    return placement


def _collection_placement(
    by_field: dict[str, SemanticElement], field_id: str, item_field: str, section_index: int, materialized_index: int
) -> dict[str, str]:
    element = by_field.get(field_id)
    if element is None or item_field not in element.item_fields:
        raise SemanticContractError(f"template_spec collection binding is absent from semantic contract: {field_id!r}.{item_field}")
    return {"element_id": element.element_id, "role": "CONTENT", "field_id": field_id, "item_field": item_field, "section_index": str(section_index), "materialized_index": str(materialized_index)}
