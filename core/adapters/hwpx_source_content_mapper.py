"""Map a source report (Markdown) onto a template's ``placeholder_map.json`` fields.

Deterministic half of the source -> content flow. Fills ONLY the fields whose
``category`` a source document can answer unambiguously (``date``,
``document_title``, ``department``, ``contact``) and leaves every other field
(judgment content: body paragraphs, conclusions, checkbox lines, notes, ...) as
``확인 필요`` — this module never invents field values. It also returns the
parsed ``source_facts`` (title/date/body lines/departments/contacts) so a human
or agent can assign the judgment fields.

Both ``placeholder_map.json`` (field_id -> category) and ``alias_map.json``
(field_id -> human alias -> choice rule, when declared) are read together:

- A field bound to a choice rule cannot be filled from freeform extracted text
  (the renderer expects one of the declared option strings, not source text),
  so such fields are always left unresolved here regardless of category.
- A "contact" field whose alias shares its parent path with another "contact"
  field (e.g. ``담당.국장.이름`` and ``담당.국장.전화``) means the template
  expects that one contact split across multiple fields (name, phone, ...).
  One extracted ``"국장 김도윤(☎02-3145-5501)"`` string cannot be decomposed
  into those parts without guessing which substring is which, so every field
  in such a group is left unresolved rather than filled with the same
  undivided text.

Output feeds ``core.document_api.render_document_from_source`` /
``core.adapters.hwpx_template_renderer``.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .hwpx_alias_map import AliasMap
from .hwpx_template_renderer import UNKNOWN, JsonValue

# placeholder_map categories a deterministic reader can fill from source text
_DETERMINISTIC_CATEGORIES = {"date", "document_title", "department", "contact"}

_DATE_RE = re.compile(
    r"20\d{2}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?|20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일"
)
_PHONE = r"0\d{1,2}[-)]\s?\d{3,4}-\d{4}"
_DEPARTMENT_RE = re.compile(r"[가-힣A-Za-z0-9·]{2,20}(?:국|과|실|팀|원|센터|위원회)")
_CONTACT_RE = re.compile(
    r"(?:국장|팀장|과장|담당자?|반장)\s*[가-힣]{2,4}\s*\(?\s*☎?\s*" + _PHONE + r"\s*\)?"
)
_BODY_MARKERS = ("□", "○", "◦", "❍", "-", "※", "⇨", "*", "†")


@dataclass
class MappingResult:
    content: dict[str, JsonValue]          # field_id -> value (or 확인 필요)
    filled_fields: list[str] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)
    source_facts: dict[str, Any] = field(default_factory=dict)


def map_source_to_content(
    source_markdown: str,
    placeholder_map: Mapping[str, JsonValue],
    alias_map: AliasMap | None = None,
    *,
    unknown: str = UNKNOWN,
) -> MappingResult:
    """Map source Markdown onto ``placeholder_map`` fields (deterministic only)."""
    fields_raw = placeholder_map.get("fields", [])
    if not isinstance(fields_raw, list):
        raise ValueError("placeholder_map must contain a 'fields' list")

    choice_field_ids = _choice_bound_field_ids(alias_map)
    split_contact_field_ids = _split_contact_group_field_ids(alias_map, fields_raw)
    facts = extract_source_facts(source_markdown)
    departments = list(facts["departments"])
    contacts = list(facts["contacts"])

    content: dict[str, JsonValue] = {}
    filled: list[str] = []
    unresolved: list[str] = []
    for entry in fields_raw:
        if not isinstance(entry, dict):
            continue
        field_id = entry["field_id"]
        category = entry.get("category")
        value: str | None = None
        if field_id not in choice_field_ids:
            if category == "date":
                value = facts["date"]
            elif category == "document_title":
                value = facts["title"]
            elif category == "department":
                value = departments.pop(0) if departments else None
            elif category == "contact" and field_id not in split_contact_field_ids:
                value = contacts.pop(0) if contacts else None

        if category in _DETERMINISTIC_CATEGORIES and value:
            content[field_id] = value
            filled.append(field_id)
        else:
            content[field_id] = unknown  # judgment field or nothing extracted
            unresolved.append(field_id)

    return MappingResult(
        content=content,
        filled_fields=filled,
        unresolved_fields=unresolved,
        source_facts=facts,
    )


def extract_source_facts(markdown: str) -> dict[str, Any]:
    """Parse deterministic material from source Markdown for downstream mapping."""
    lines = [line.rstrip() for line in markdown.splitlines()]
    date_match = _DATE_RE.search(markdown)
    # department is taken from the contact/문의 context (avoids the agency name in the header)
    contact_lines = [line for line in lines if re.search(_PHONE, line)]
    departments = _unique(
        match for line in contact_lines for match in _DEPARTMENT_RE.findall(line)
    )
    return {
        "title": _first_title(lines),
        "date": _normalize(date_match.group(0)) if date_match else None,
        "departments": departments,
        "all_departments": _unique(_DEPARTMENT_RE.findall(markdown)),
        "contacts": _unique(_CONTACT_RE.findall(markdown)),
        "body_lines": [
            _normalize(line) for line in lines
            if line.strip() and line.strip()[:1] in _BODY_MARKERS
        ],
    }


def _choice_bound_field_ids(alias_map: AliasMap | None) -> frozenset[str]:
    if alias_map is None:
        return frozenset()
    return frozenset(
        alias_map.aliases[alias]
        for alias in alias_map.choices
        if alias in alias_map.aliases
    )


def _split_contact_group_field_ids(
    alias_map: AliasMap | None,
    fields_raw: list,
) -> frozenset[str]:
    if alias_map is None:
        return frozenset()
    contact_field_ids = {
        entry["field_id"]
        for entry in fields_raw
        if isinstance(entry, dict) and entry.get("category") == "contact"
    }
    alias_by_field = {
        field_id: alias for alias, field_id in alias_map.aliases.items()
    }
    groups: dict[str, list[str]] = {}
    for field_id in contact_field_ids:
        alias = alias_by_field.get(field_id)
        if alias is None or "." not in alias:
            continue
        parent = alias.rsplit(".", 1)[0]
        groups.setdefault(parent, []).append(field_id)
    return frozenset(
        field_id
        for group in groups.values()
        if len(group) > 1
        for field_id in group
    )


def _first_title(lines: list[str]) -> str | None:
    headings = [line.lstrip("#").strip() for line in lines if line.strip().startswith("#")]
    if headings:
        return headings[0]
    for line in lines:
        stripped = line.strip()
        if stripped and not _DATE_RE.search(stripped) and len(stripped) >= 4:
            return stripped
    return None


def _unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        norm = _normalize(value)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def _normalize(value: str) -> str:
    return " ".join(value.split())
