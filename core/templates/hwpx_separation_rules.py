from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, assert_never

if TYPE_CHECKING:
    from .hwpx_semantic_contract import SemanticRole


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class TextRole(StrEnum):
    CONTENT = "content"
    FIXED_LABEL = "fixed_label"
    FIXED_TEXT = "fixed_text"


class SeparationRuleError(ValueError):
    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"invalid content-separation rules in {path}: {detail}")


@dataclass(frozen=True, slots=True)
class TextLocation:
    section: str
    text_node_index: int
    table: int | None
    row: int | None
    col: int | None
    paragraph_index: int | None = None


@dataclass(frozen=True, slots=True)
class LocationRule:
    role: TextRole
    section: str
    field_id: str | None = None
    text_node_index: int | None = None
    table: int | None = None
    row: int | None = None
    col: int | None = None

    def matches(self, location: TextLocation) -> bool:
        return (
            self.section == location.section
            and (self.text_node_index is None or self.text_node_index == location.text_node_index)
            and (self.table is None or self.table == location.table)
            and (self.row is None or self.row == location.row)
            and (self.col is None or self.col == location.col)
        )


@dataclass(frozen=True, slots=True)
class SeparationRules:
    rules: tuple[LocationRule, ...] = ()

    def role_for(self, location: TextLocation) -> TextRole | None:
        matched = {rule.role for rule in self.rules if rule.matches(location)}
        if len(matched) > 1:
            raise SeparationRuleError(Path(location.section), "conflicting location rules")
        return next(iter(matched), None)

    def field_id_for(self, location: TextLocation) -> str | None:
        matched = {
            rule.field_id for rule in self.rules if rule.matches(location) and rule.field_id is not None
        }
        if len(matched) > 1:
            raise SeparationRuleError(Path(location.section), "conflicting canonical field_id rules")
        return next(iter(matched), None)

    def semantic_role_for(
        self, location: TextLocation
    ) -> tuple[SemanticRole | None, tuple[str, ...]]:
        from .hwpx_semantic_contract import SemanticRole

        matched = {rule.role for rule in self.rules if rule.matches(location)}
        if not matched:
            return None, ()
        semantic_roles: set[SemanticRole] = set()
        reasons: list[str] = []
        for role in sorted(matched, key=lambda item: item.value):
            match role:
                case TextRole.CONTENT:
                    semantic_roles.add(SemanticRole.CONTENT)
                    reasons.append("legacy_override_content")
                case TextRole.FIXED_LABEL:
                    semantic_roles.add(SemanticRole.FIXED)
                    reasons.append("legacy_override_fixed_label")
                case TextRole.FIXED_TEXT:
                    semantic_roles.add(SemanticRole.FIXED)
                    reasons.append("legacy_override_fixed_text")
                case unreachable:
                    assert_never(unreachable)
        if len(semantic_roles) > 1:
            return SemanticRole.AMBIGUOUS, tuple(sorted(reasons))
        return next(iter(semantic_roles)), tuple(sorted(reasons))


def load_separation_rules(path: Path | str | None) -> SeparationRules:
    if path is None:
        return SeparationRules()
    source = Path(path)
    raw: JsonValue = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SeparationRuleError(source, "root must be an object")
    # "resolutions"만 있는 파일(사람이 AMBIGUOUS를 해소하려고 작성한 rules
    # 파일)도 읽을 수 있도록 "rules"는 생략 가능한 키로 남긴다.
    items = raw.get("rules", [])
    if not isinstance(items, list):
        raise SeparationRuleError(source, "rules must be a list")
    return SeparationRules(tuple(_parse_rule(source, item) for item in items))


def _parse_rule(path: Path, item: JsonValue) -> LocationRule:
    if not isinstance(item, dict):
        raise SeparationRuleError(path, "each rule must be an object")
    role_value = item.get("role")
    if not isinstance(role_value, str):
        raise SeparationRuleError(path, "role must be content, fixed_label, or fixed_text")
    try:
        role = TextRole(role_value)
    except ValueError:
        raise SeparationRuleError(
            path, "role must be content, fixed_label, or fixed_text"
        ) from None
    section = item.get("section")
    if not isinstance(section, str) or not section:
        raise SeparationRuleError(path, "section must be a non-empty string")
    selector = LocationRule(
        role=role,
        section=section,
        field_id=_optional_field_id(path, item.get("field_id"), role),
        text_node_index=_optional_int(path, item.get("text_node_index"), "text_node_index"),
        table=_optional_int(path, item.get("table"), "table"),
        row=_optional_int(path, item.get("row"), "row"),
        col=_optional_int(path, item.get("col"), "col"),
    )
    if all(value is None for value in (selector.text_node_index, selector.table, selector.row, selector.col)):
        raise SeparationRuleError(path, "a rule must include at least one location selector")
    return selector


def _optional_int(path: Path, value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SeparationRuleError(path, f"{name} must be a non-negative integer")
    return value


def _optional_field_id(path: Path, value: JsonValue, role: TextRole) -> str | None:
    if value is None:
        return None
    if role is not TextRole.CONTENT:
        raise SeparationRuleError(path, "field_id is valid only for a content rule")
    if not isinstance(value, str) or not value:
        raise SeparationRuleError(path, "field_id must be a non-empty string")
    return value
