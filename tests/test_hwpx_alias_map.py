"""core.adapters.hwpx_alias_map: human-authored names -> extracted field_ids.

Proves the alias map flattens a nested content contract onto ``field_id`` keys,
refuses a binding that no longer matches the placeholder map, and reports content
keys it cannot place instead of dropping them.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.adapters.hwpx_alias_map import (
    AliasMap,
    AliasMapError,
    flatten,
    load_alias_map,
)

ROOT = Path(__file__).resolve().parent.parent
DIRECTOR_REPORT = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"

FIELD_IDS = frozenset(
    {
        "date_01",
        "document_title_01",
        "checkbox_line_01",
        "content_01",
        "body_paragraph_01",
        "body_bullet_01",
        "stat_note_01",
        "detail_note_01",
        "summary_01",
        "conclusion_01",
        "department_name_01",
        "director_name_01",
        "director_phone_01",
        "manager_name_01",
        "manager_phone_01",
    }
)


def _write_alias_map(tmp: Path, payload: dict) -> Path:
    (tmp / "alias_map.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return tmp


def test_flatten_expands_nested_objects_and_arrays() -> None:
    flat = flatten(
        {
            "제목": "현황",
            "담당": {"국": "디지털금융국", "국장": "홍길동"},
            "부제": ["첫째", "둘째"],
        }
    )

    assert flat == {
        "제목": "현황",
        "담당.국": "디지털금융국",
        "담당.국장": "홍길동",
        "부제[0]": "첫째",
        "부제[1]": "둘째",
    }


def test_flatten_drops_empty_containers() -> None:
    # an omitted branch must stay missing, not become an empty value
    assert flatten({"담당": {}, "부제": [], "제목": "현황"}) == {"제목": "현황"}


def test_resolve_maps_nested_paths_to_field_ids() -> None:
    alias_map = AliasMap(
        template_id="fss_director_report",
        aliases={"제목": "document_title_01", "담당.국": "department_name_01"},
    )

    resolved, unknown = alias_map.resolve(
        {"제목": "현황보고", "담당": {"국": "디지털금융국"}}, FIELD_IDS
    )

    assert resolved == {
        "document_title_01": "현황보고",
        "department_name_01": "디지털금융국",
    }
    assert unknown == []


def test_resolve_passes_field_ids_through_and_is_idempotent() -> None:
    alias_map = AliasMap(template_id=None, aliases={"제목": "document_title_01"})

    once, _ = alias_map.resolve({"제목": "현황", "date_01": "(2026. 7. 9.)"}, FIELD_IDS)
    twice, unknown = alias_map.resolve(once, FIELD_IDS)

    assert once == {"document_title_01": "현황", "date_01": "(2026. 7. 9.)"}
    assert twice == once  # the renderer may resolve more than once
    assert unknown == []


def test_resolve_reports_unknown_keys() -> None:
    alias_map = AliasMap(template_id=None, aliases={"제목": "document_title_01"})

    resolved, unknown = alias_map.resolve({"제목": "현황", "제목오타": "x"}, FIELD_IDS)

    assert resolved == {"document_title_01": "현황"}
    assert unknown == ["제목오타"]  # reported, never silently dropped


def test_resolve_raises_on_conflicting_alias_and_field_id() -> None:
    alias_map = AliasMap(template_id=None, aliases={"제목": "document_title_01"})

    with pytest.raises(AliasMapError, match="conflicting values"):
        alias_map.resolve({"제목": "A", "document_title_01": "B"}, FIELD_IDS)


def test_resolve_allows_same_value_from_alias_and_field_id() -> None:
    alias_map = AliasMap(template_id=None, aliases={"제목": "document_title_01"})

    resolved, unknown = alias_map.resolve(
        {"제목": "같은 값", "document_title_01": "같은 값"}, FIELD_IDS
    )

    assert resolved == {"document_title_01": "같은 값"}
    assert unknown == []


def test_load_returns_none_without_alias_map() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert load_alias_map(Path(tmp), field_ids=FIELD_IDS) is None


def test_load_rejects_alias_pointing_at_unknown_field_id() -> None:
    # this is the renumbering guard: content_99 no longer exists after re-extraction
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_alias_map(Path(tmp), {"aliases": {"제목": "content_99"}})
        with pytest.raises(AliasMapError, match="unknown field_id"):
            load_alias_map(path, field_ids=FIELD_IDS)


def test_load_rejects_two_aliases_claiming_one_field() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_alias_map(
            Path(tmp),
            {"aliases": {"제목": "document_title_01", "표제": "document_title_01"}},
        )
        with pytest.raises(AliasMapError, match="claimed by both"):
            load_alias_map(path, field_ids=FIELD_IDS)


def test_load_rejects_template_id_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_alias_map(
            Path(tmp), {"template_id": "other_template", "aliases": {}}
        )
        with pytest.raises(AliasMapError, match="does not match"):
            load_alias_map(path, field_ids=FIELD_IDS, template_id="fss_director_report")


def test_load_rejects_non_object_aliases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_alias_map(Path(tmp), {"aliases": ["제목"]})
        with pytest.raises(AliasMapError, match="aliases must be an object"):
            load_alias_map(path, field_ids=FIELD_IDS)


def test_shipped_director_report_alias_map_matches_its_placeholder_map() -> None:
    mapping = json.loads(
        (DIRECTOR_REPORT / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field_ids = frozenset(entry["field_id"] for entry in mapping["fields"])

    alias_map = load_alias_map(
        DIRECTOR_REPORT, field_ids=field_ids, template_id=mapping.get("template_id")
    )

    assert alias_map is not None
    assert alias_map.aliases["제목"] == "document_title_01"
    assert alias_map.aliases["담당.국"] == "department_name_01"
    assert set(alias_map.aliases.values()) <= field_ids
