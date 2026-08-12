"""core.adapters.hwpx_source_content_mapper: source Markdown -> template fields.

Proves the deterministic mapper fills only unambiguous fields (date, title,
department, contact), leaves judgment fields as 확인 필요 (never invented), picks
the reporting department from the contact context (not the agency header), and
keeps a field bound to an alias_map choice rule unresolved even if its category
would otherwise be deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.adapters.hwpx_alias_map import ChoiceRule, load_alias_map
from core.adapters.hwpx_source_content_mapper import map_source_to_content
from core.adapters.hwpx_template_renderer import UNKNOWN

ROOT = Path(__file__).resolve().parents[2]
FSS_DIR = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고 가상자산"
PLACEHOLDER_MAP = json.loads((FSS_DIR / "placeholder_map.json").read_text(encoding="utf-8"))

DIRECTOR_REPORT_DIR = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
DIRECTOR_REPORT_PLACEHOLDER_MAP = json.loads(
    (DIRECTOR_REPORT_DIR / "placeholder_map.json").read_text(encoding="utf-8")
)

SOURCE = """# 가상자산 이상거래 관련 현황 점검 진행상황

(2026. 7. 9.) 금융감독원 보도자료

□ 최근 가상자산 시장에서 이상매매 정황이 다수 포착됨에 따라 대응방안을 마련하고자 함
 ◦ FDS 및 거래소 제보를 통해 특정 종목에서 단기간 거래량이 급증하는 사례가 확인됨
※ 세부 수치는 관계기관 확인 후 업데이트 예정

문의: 가상자산감독국 국장 김도윤(☎02-3145-5501), 팀장 박서연(☎02-3145-5502)
"""


def test_deterministic_fields_are_filled() -> None:
    result = map_source_to_content(SOURCE, PLACEHOLDER_MAP)

    assert result.content["date_01"] == "2026. 7. 9."
    assert result.content["document_title_01"] == "가상자산 이상거래 관련 현황 점검 진행상황"
    assert result.content["department_01"] == "가상자산감독국"      # from 문의 context
    assert result.content["contact_01"] == "국장 김도윤(☎02-3145-5501)"
    assert result.content["contact_02"] == "팀장 박서연(☎02-3145-5502)"
    assert set(result.filled_fields) == {
        "date_01", "document_title_01", "department_01", "contact_01", "contact_02",
    }


def test_department_prefers_contact_context_over_agency_header() -> None:
    facts = map_source_to_content(SOURCE, PLACEHOLDER_MAP).source_facts
    assert facts["departments"] == ["가상자산감독국"]        # not 금융감독원
    assert "금융감독원" in facts["all_departments"]           # still surfaced for review


def test_judgment_fields_stay_unknown_with_source_facts() -> None:
    result = map_source_to_content(SOURCE, PLACEHOLDER_MAP)

    for field_id in ("body_paragraph_01", "conclusion_01", "checkbox_line_01", "stat_note_01"):
        assert result.content[field_id] == UNKNOWN
        assert field_id in result.unresolved_fields
    assert len(result.source_facts["body_lines"]) == 3


def test_choice_bound_field_stays_unresolved_even_if_category_is_deterministic() -> None:
    """A field an alias_map binds to a choice rule can't take freeform source text."""
    alias_map = _alias_map_with_choice_on("department_01")

    result = map_source_to_content(SOURCE, PLACEHOLDER_MAP, alias_map)

    assert result.content["department_01"] == UNKNOWN
    assert "department_01" in result.unresolved_fields
    assert "department_01" not in result.filled_fields


def test_contact_fields_split_across_name_and_phone_stay_unresolved() -> None:
    """fss_director_report binds one contact to 담당.국장.이름/전화 separately.

    A single extracted "국장 김도윤(☎02-3145-5501)" string cannot be split into
    a name-only and a phone-only field without guessing, so the mapper must
    leave both unresolved instead of writing the same undivided text into both.
    """
    field_ids = frozenset(
        entry["field_id"] for entry in DIRECTOR_REPORT_PLACEHOLDER_MAP["fields"]
    )
    alias_map = load_alias_map(
        DIRECTOR_REPORT_DIR,
        field_ids=field_ids,
        template_id=DIRECTOR_REPORT_PLACEHOLDER_MAP.get("template_id"),
    )

    result = map_source_to_content(SOURCE, DIRECTOR_REPORT_PLACEHOLDER_MAP, alias_map)

    for field_id in (
        "director_name_01", "director_phone_01",
        "manager_name_01", "manager_phone_01",
    ):
        assert result.content[field_id] == UNKNOWN
        assert field_id in result.unresolved_fields
        assert field_id not in result.filled_fields
    # department has no split-group conflict, so it still fills deterministically
    assert result.content["department_name_01"] == "가상자산감독국"


def _alias_map_with_choice_on(field_id: str):
    from core.adapters.hwpx_alias_map import AliasMap

    return AliasMap(
        template_id=None,
        aliases={"부서선택": field_id},
        choices={
            "부서선택": ChoiceRule(
                options=("가상자산감독국", "기타"),
                checked_prefix="■ ",
                unchecked_prefix="□ ",
                separator=" ",
            )
        },
    )
