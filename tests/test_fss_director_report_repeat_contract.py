from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import hwpx
import pytest

from core.adapters.hwpx_alias_map import AliasMapError, load_alias_map
from core.adapters.hwpx_template_renderer import (
    RenderExecutionContext,
    orchestrate_hwpx_render,
)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
)
CONTENT = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_director_report.input.json"
)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([[1]], "must be \\[level, text\\]"),
        ([[9, "지원하지 않는 단계"]], "unknown level 9"),
    ],
)
def test_repeat_input_contract_is_validated_by_alias_map(
    body: list,
    message: str,
) -> None:
    placeholder_map = json.loads(
        (TEMPLATE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field_ids = frozenset(
        entry["field_id"] for entry in placeholder_map["fields"]
    )
    alias_map = load_alias_map(
        TEMPLATE_DIR,
        field_ids=field_ids,
        template_id=placeholder_map["template_id"],
    )

    assert alias_map is not None
    with pytest.raises(AliasMapError, match=message):
        alias_map.resolve({"본문": body}, field_ids)


def test_report_type_choice_renders_complete_checkbox_line(
    tmp_path: Path,
) -> None:
    output = tmp_path / "금감원_원장보고_보고구분.hwpx"
    content = json.loads(CONTENT.read_text(encoding="utf-8"))

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")

    assert (
        "□ 현안검토  ☑ 언론보도  □ 국회 등  "
        "□ 금융위·증선위  □ 기타(현황파악)"
    ) in section


def test_report_type_choice_rejects_unknown_option() -> None:
    placeholder_map = json.loads(
        (TEMPLATE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field_ids = frozenset(
        entry["field_id"] for entry in placeholder_map["fields"]
    )
    alias_map = load_alias_map(
        TEMPLATE_DIR,
        field_ids=field_ids,
        template_id=placeholder_map["template_id"],
    )

    assert alias_map is not None
    with pytest.raises(AliasMapError, match="unknown option"):
        alias_map.resolve({"보고구분": "임의구분"}, field_ids)


def test_raw_contract_renders_repeat_block_and_preserves_fixed_form(
    tmp_path: Path,
) -> None:
    output = tmp_path / "금감원_원장보고_반복.hwpx"
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    placeholder_map = json.loads(
        (TEMPLATE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field_ids = frozenset(
        entry["field_id"] for entry in placeholder_map["fields"]
    )
    alias_map = load_alias_map(
        TEMPLATE_DIR,
        field_ids=field_ids,
        template_id=placeholder_map["template_id"],
    )

    result = orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    assert alias_map is not None
    assert alias_map.blocks["본문"].anchor == "content_01"
    assert alias_map.blocks["본문"].numbered_level == 0
    assert alias_map.blocks["본문"].item_separator_levels == (0, 1, 2, 3)
    assert alias_map.blocks["본문"].section_transition == (0, 0)
    assert alias_map.text_rules["결론"].single_paragraph is True
    assert alias_map.text_rules["결론"].single_sentence is True
    assert alias_map.fit_constraints["summary_01"].max_lines == 1
    assert alias_map.fit_constraints["conclusion_01"].max_lines == 1
    assert alias_map.blocks["본문"].levels == {
        0: ("content_01", ""),
        1: ("body_paragraph_01", "□ "),
        2: ("body_bullet_01", "◦ "),
        3: ("stat_note_01", "* "),
        4: ("detail_note_01", "† "),
    }
    assert result.filled_fields == [
        "body_bullet_01",
        "body_paragraph_01",
        "checkbox_line_01",
        "conclusion_01",
        "content_01",
        "date_01",
        "department_name_01",
        "detail_note_01",
        "director_name_01",
        "director_phone_01",
        "document_title_01",
        "manager_name_01",
        "manager_phone_01",
        "stat_note_01",
        "summary_01",
    ]
    assert result.missing_fields == []
    assert result.leftover_placeholders == []
    assert result.unknown_keys == []

    with zipfile.ZipFile(output) as package, zipfile.ZipFile(
        TEMPLATE_DIR / "source.hwpx"
    ) as source:
        section = package.read("Contents/section0.xml").decode("utf-8")
        assert (
            package.read("Contents/header.xml")
            == source.read("Contents/header.xml")
        )

    visible = [
        re.sub(r"<[^>]+>", "", text)
        for text in re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", section, re.DOTALL)
    ]
    repeated = [
        "1. 추진 배경",
        "□ 최근 가상자산 시장 변동성이 확대됨",
        "◦ 이상거래 탐지 건수가 전분기 대비 증가",
        "◦ 미이행 사업자에 시정 조치를 요구함",
        "* 2026년 상반기 누적 1,204건",
        "† 자체 탐지 기준 적용",
        "2. 주요 내용",
        "□ 상시감시 체계 고도화 세부 방안을 마련함",
    ]
    positions = [visible.index(text) for text in repeated]
    assert positions == sorted(positions)
    square_paragraphs = [
        re.search(
            rf"<hp:p\b[^>]*>(?:(?!<hp:p\b).)*?{re.escape(text)}"
            rf"(?:(?!<hp:p\b).)*?</hp:p>",
            section,
            re.DOTALL,
        )
        for text in (repeated[1], repeated[7])
    ]
    first_match, second_match = square_paragraphs
    assert first_match is not None
    assert second_match is not None
    first_level_one = first_match.group(0)
    second_level_one = second_match.group(0)
    assert first_level_one.replace(repeated[1], "") == second_level_one.replace(
        repeated[7], ""
    )
    assert "2026. 7. 30." in visible
    assert (
        "□ 현안검토  ☑ 언론보도  □ 국회 등  "
        "□ 금융위·증선위  □ 기타(현황파악)"
    ) in visible
    assert "⇨ " in visible
    assert "3분기 중 상시감시 체계 고도화를 추진한다." in visible
    assert "현안(이슈)보고" in visible
    assert "☑ " in visible
    assert (
        "가상자산 시장 변동성이 확대되어 주요 동향을 점검할 필요가 있음."
        in visible
    )
    assert " ※ 1페이지 하단에 보고자 및 연락처 등 표시" in visible
    assert section.count("<hp:tbl") == 4
    assert "{{" not in section

    validation = hwpx.validate_package(output)
    assert validation.ok is True
    assert list(validation.errors) == []
