from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import hwpx
import pytest

from core.adapters.hwpx_alias_map import AliasMapError
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    JsonValue,
    RenderExecutionContext,
    orchestrate_hwpx_render,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
)
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


def _content() -> dict[str, JsonValue]:
    return {
        "보고일": "2026. 7. 30.",
        "제목": "가상자산 이상거래 대응 진행현황",
        "보고구분": "언론보도",
        "요약": "가상자산 시장 변동성이 확대되어 주요 동향을 점검할 필요가 있음.",
        "본문": [
            [0, "추진 배경"],
            [1, "최근 가상자산 시장 변동성이 확대됨"],
        ],
        "결론": "상시감시 체계 고도화를 추진한다.",
        "담당": {
            "국": "정보보호",
            "국장": {"이름": "홍길동", "전화": "1111"},
            "팀장": {"이름": "김철수", "전화": "2222"},
        },
    }


def _section_root(path: Path) -> ElementTree.Element:
    with zipfile.ZipFile(path) as package:
        return ElementTree.fromstring(package.read("Contents/section0.xml"))


def _cell_text(cell: ElementTree.Element) -> str:
    return "".join(text.text or "" for text in cell.findall(".//hp:t", NS))


def _cell_layout(cell: ElementTree.Element) -> tuple:
    size = cell.find("./hp:cellSz", NS)
    margin = cell.find("./hp:cellMargin", NS)
    paragraph = cell.find(".//hp:p", NS)
    assert size is not None
    assert margin is not None
    assert paragraph is not None
    return (
        dict(cell.attrib),
        dict(size.attrib),
        dict(margin.attrib),
        paragraph.get("paraPrIDRef"),
    )


def test_fss_report_renders_fixed_form_text_around_variable_values(
    tmp_path: Path,
) -> None:
    # Given: 입력값은 양식에 고정된 기호·직책·접미사를 포함하지 않는다.
    output = tmp_path / "금감원_원장보고_고정문구_분리.hwpx"

    # When: 실제 승인 템플릿으로 HWPX를 렌더링한다.
    result = orchestrate_hwpx_render(
        TEMPLATE_DIR,
        _content(),
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    # Then: 고정 문구와 입력값이 합쳐지고 원본 셀 구조는 유지된다.
    rendered = _section_root(output)
    source = _section_root(TEMPLATE_DIR / "source.hwpx")
    rendered_tables = rendered.findall(".//hp:tbl", NS)
    source_tables = source.findall(".//hp:tbl", NS)

    assert _cell_text(rendered_tables[1].find(".//hp:tc", NS)) == (
        "☑ 가상자산 시장 변동성이 확대되어 주요 동향을 점검할 필요가 있음."
    )
    assert _cell_text(rendered_tables[2].find(".//hp:tc", NS)) == (
        "⇨ 상시감시 체계 고도화를 추진한다."
    )
    contact_cells = rendered_tables[3].findall(".//hp:tc", NS)
    assert [_cell_text(cell) for cell in contact_cells] == [
        "정보보호국",
        "국장 홍길동(☎1111)",
        "팀장 김철수(☎2222)",
    ]

    for table_index in (1, 2, 3):
        rendered_cells = rendered_tables[table_index].findall(".//hp:tc", NS)
        source_cells = source_tables[table_index].findall(".//hp:tc", NS)
        assert [_cell_layout(cell) for cell in rendered_cells] == [
            _cell_layout(cell) for cell in source_cells
        ]

    section_text = "".join(rendered.itertext())
    assert "요약 또는 배경" not in section_text
    assert "{{" not in section_text
    assert result.unknown_keys == []
    assert result.leftover_placeholders == []
    validation = hwpx.validate_package(output)
    assert validation.ok is True
    assert list(validation.errors) == []


@pytest.mark.parametrize("alias", ["요약", "결론"])
def test_fss_report_rejects_text_without_one_terminal_mark(
    alias: str,
    tmp_path: Path,
) -> None:
    # Given: 한 문장 필드의 마지막 종결부호가 빠져 있다.
    content = _content()
    content[alias] = "종결부호가 없는 문장"

    # When/Then: 문서 생성 전에 입력 계약 위반으로 중단한다.
    with pytest.raises(AliasMapError, match="one sentence"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            content,
            tmp_path / "unused-terminal-mark-test.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )


@pytest.mark.parametrize(
    ("alias", "field_id"),
    [("요약", "summary_01"), ("결론", "conclusion_01")],
)
def test_fss_report_applies_sentence_rule_to_direct_field_ids(
    alias: str,
    field_id: str,
    tmp_path: Path,
) -> None:
    # Given: 사람용 alias 대신 field ID로 종결부호 없는 값을 전달한다.
    content = _content()
    del content[alias]
    content[field_id] = "종결부호가 없는 문장"

    # When/Then: 입력 경로와 관계없이 같은 문장 계약으로 중단한다.
    with pytest.raises(AliasMapError, match="one sentence"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            content,
            tmp_path / "unused-direct-field-test.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )


@pytest.mark.parametrize("alias", ["요약", "결론"])
def test_fss_report_rejects_multiline_box_text(
    alias: str,
    tmp_path: Path,
) -> None:
    # Given: 한 줄 박스 입력에 줄바꿈이 포함돼 있다.
    content = _content()
    content[alias] = "첫 번째 문장.\n두 번째 문장."

    # When/Then: 폭 측정 전에 단일 문단 계약 위반으로 중단한다.
    with pytest.raises(AliasMapError, match="single paragraph"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            content,
            tmp_path / "unused-multiline-test.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )


@pytest.mark.parametrize(
    ("alias", "field_id"),
    [("요약", "summary_01"), ("결론", "conclusion_01")],
)
def test_fss_report_rejects_text_wider_than_source_cell(
    alias: str,
    field_id: str,
    tmp_path: Path,
) -> None:
    # Given: 입력값만은 맞지만 고정 기호까지 더하면 박스 폭을 넘는다.
    content = _content()
    content[alias] = f"{'가' * 35}."

    # When/Then: 글꼴이나 셀을 바꾸지 않고 렌더링 오류로 중단한다.
    with pytest.raises(
        HwpxTemplateRenderError,
        match=rf"field {field_id!r} does not fit in one line",
    ):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            content,
            tmp_path / "unused-width-test.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )


def test_fss_report_rejects_department_name_with_fixed_suffix(
    tmp_path: Path,
) -> None:
    # Given: 입력값이 양식에 고정된 "국" 접미사를 중복해서 포함한다.
    content = _content()
    content["담당"]["국"] = "정보보호국"

    # When/Then: "정보보호국국"을 만들지 않고 계약 위반으로 중단한다.
    with pytest.raises(AliasMapError, match="must not include suffix '국'"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            content,
            tmp_path / "unused-department-suffix-test.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )
