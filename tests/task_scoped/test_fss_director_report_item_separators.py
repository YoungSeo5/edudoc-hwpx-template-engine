from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import hwpx
import pytest

from core.adapters.hwpx_alias_map import (
    AliasMap,
    AliasMapError,
    RepeatBlock,
    load_alias_map,
)
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderExecutionContext,
    orchestrate_hwpx_render,
    render_repeat_block,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
)
CONTENT_PATH = ROOT / "tests" / "fixtures" / "template-content" / "fss_director_report.input.json"
PARAGRAPH_RE = re.compile(r"<hp:p\b.*?</hp:p>", re.DOTALL)
LINESEGARRAY_RE = re.compile(
    r"<hp:linesegarray\b[^>]*/>|<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>",
    re.DOTALL,
)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


def _paragraph_text(paragraph: str) -> str:
    return re.sub(r"<[^>]+>", "", paragraph)


def _paragraph_index(paragraphs: list[str], text: str) -> int:
    return next(
        index
        for index, paragraph in enumerate(paragraphs)
        if text in _paragraph_text(paragraph)
    )


def _paragraph_style(paragraph: str) -> tuple[str, str]:
    para = re.search(r'paraPrIDRef="([^"]+)"', paragraph)
    char = re.search(r'charPrIDRef="([^"]+)"', paragraph)
    assert para is not None
    assert char is not None
    return para.group(1), char.group(1)


def _repeat_alias_map(
    *,
    section_transition: tuple[int, int] | None = None,
) -> AliasMap:
    return AliasMap(
        template_id="separator_test",
        aliases={},
        blocks={
            "본문": RepeatBlock(
                anchor="content_01",
                levels={
                    0: ("content_01", ""),
                    1: ("body_paragraph_01", "□ "),
                    2: ("body_bullet_01", " ◦ "),
                    3: ("stat_note_01", "      * "),
                    4: ("detail_note_01", "         † "),
                },
                numbered_level=0,
                item_separator_levels=(0, 1, 2, 3),
                section_transition=section_transition,
            )
        },
    )


def _repeat_xml(separator_zero: str | None = None) -> str:
    separators = {
        0: separator_zero
        or '<hp:p paraPrIDRef="s0"><hp:run charPrIDRef="c0"/></hp:p>',
        1: '<hp:p paraPrIDRef="s1"><hp:run charPrIDRef="c1"/></hp:p>',
        2: '<hp:p paraPrIDRef="s2"><hp:run charPrIDRef="c2"/></hp:p>',
        3: '<hp:p paraPrIDRef="s3"><hp:run charPrIDRef="c3"/></hp:p>',
    }
    field_ids = (
        "content_01",
        "body_paragraph_01",
        "body_bullet_01",
        "stat_note_01",
        "detail_note_01",
    )
    paragraphs: list[str] = []
    for level, field_id in enumerate(field_ids):
        paragraphs.append(
            f'<hp:p paraPrIDRef="p{level}"><hp:run charPrIDRef="r{level}">'
            f"<hp:t>{{{{{field_id}}}}}</hp:t></hp:run></hp:p>"
        )
        if level in separators:
            paragraphs.append(separators[level])
    return "".join(paragraphs)


def test_fss_report_inserts_each_preceding_level_separator(
    tmp_path: Path,
) -> None:
    # Given: the body exercises every general transition, including repeated level 1.
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    content["본문"] = [
        [0, "제목"],
        [1, "첫 번째 본문"],
        [1, "두 번째 본문"],
        [2, "세부 내용"],
        [3, "통계 주석"],
        [4, "상세 주석"],
    ]
    output = tmp_path / "금감원_원장보고_항목간격.hwpx"

    # When: the real FSS template renders the repeated body.
    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    # Then: each gap uses the source separator belonging to the preceding level.
    with zipfile.ZipFile(output) as package, zipfile.ZipFile(
        TEMPLATE_DIR / "source.hwpx"
    ) as source:
        section = package.read("Contents/section0.xml").decode("utf-8")
        assert (
            package.read("Contents/header.xml")
            == source.read("Contents/header.xml")
        )
    paragraphs = PARAGRAPH_RE.findall(section)
    template_xml = (TEMPLATE_DIR / "template" / "section0.template.xml").read_text(
        encoding="utf-8"
    )
    source_paragraphs = PARAGRAPH_RE.findall(template_xml)
    transitions = (
        ("1. 제목", "□ 첫 번째 본문", ("22", "14")),
        ("□ 첫 번째 본문", "□ 두 번째 본문", ("23", "16")),
        ("□ 두 번째 본문", "◦ 세부 내용", ("23", "16")),
        ("◦ 세부 내용", "* 통계 주석", ("24", "17")),
        ("* 통계 주석", "† 상세 주석", ("25", "19")),
    )
    for current, following, expected_style in transitions:
        current_index = _paragraph_index(paragraphs, current)
        following_index = _paragraph_index(paragraphs, following)
        assert following_index == current_index + 2
        assert _paragraph_text(paragraphs[current_index + 1]).strip() == ""
        assert _paragraph_style(paragraphs[current_index + 1]) == expected_style
        source_separator = next(
            p for p in source_paragraphs if _paragraph_style(p) == expected_style
        )
        assert paragraphs[current_index + 1] == LINESEGARRAY_RE.sub("", source_separator)

    assert "hp:linesegarray" not in section
    validation = hwpx.validate_package(output)
    assert validation.ok is True
    assert list(validation.errors) == []


def test_fss_report_uses_paragraph_styles_as_only_repeat_indentation(
    tmp_path: Path,
) -> None:
    # Given: the real report renders each nested marker level.
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    content["본문"] = [
        [0, "제목"],
        [1, "본문"],
        [2, "하위 항목"],
        [3, "통계 주석"],
        [4, "상세 주석"],
    ]
    output = tmp_path / "금감원_원장보고_문단서식_들여쓰기.hwpx"

    # When: the approved rendering path creates the final HWPX.
    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    # Then: marker text has no leading spaces and its original paragraph style remains.
    with zipfile.ZipFile(output) as package:
        section = ElementTree.fromstring(package.read("Contents/section0.xml"))
    expected = {
        "◦ 하위 항목": "24",
        "* 통계 주석": "25",
        "† 상세 주석": "26",
    }
    paragraphs = [
        paragraph
        for paragraph in section.iter()
        if paragraph.tag.rsplit("}", 1)[-1] == "p"
    ]
    for expected_text, expected_style in expected.items():
        paragraph = next(
            item for item in paragraphs if expected_text in "".join(item.itertext())
        )
        assert "".join(paragraph.itertext()) == expected_text
        assert paragraph.attrib["paraPrIDRef"] == expected_style


def test_repeat_block_omits_separator_after_last_item() -> None:
    # Given: the last item has no following item to separate.
    content = {"content_01": [[4, "마지막 상세"]]}

    # When: the block is rendered.
    rendered, _, _ = render_repeat_block(
        _repeat_xml(),
        content,
        _repeat_alias_map().blocks,
    )

    # Then: no separator is appended after the final paragraph.
    paragraphs = PARAGRAPH_RE.findall(rendered)
    assert len(paragraphs) == 1
    assert "         † 마지막 상세" in _paragraph_text(paragraphs[0])


def test_repeat_block_inserts_one_configured_section_transition() -> None:
    # Given: every transition to level 0 selects level 0's source separator.
    content = {"content_01": [[4, "마지막 상세"], [0, "다음 제목"]]}
    alias_map = _repeat_alias_map(section_transition=(0, 0))

    # When: the configured transition is rendered.
    rendered, _, _ = render_repeat_block(
        _repeat_xml(),
        content,
        alias_map.blocks,
    )

    # Then: exactly one level 0 separator is placed between the two items.
    paragraphs = PARAGRAPH_RE.findall(rendered)
    assert len(paragraphs) == 3
    assert _paragraph_style(paragraphs[1]) == ("s0", "c0")
    assert rendered.count('paraPrIDRef="s0"') == 1


@pytest.mark.parametrize(
    "unsafe_separator",
    [
        '<hp:p paraPrIDRef="s0"><hp:run charPrIDRef="c0">'
        "<hp:t>삭제되면 안 되는 문장</hp:t></hp:run></hp:p>",
        '<hp:p paraPrIDRef="s0"><hp:run charPrIDRef="c0">'
        "<hp:tbl/></hp:run></hp:p>",
        '<hp:p paraPrIDRef="s0"><hp:run charPrIDRef="c0">'
        "<hp:ctrl/></hp:run></hp:p>",
    ],
    ids=("text", "table", "control"),
)
def test_repeat_block_rejects_unsafe_declared_separator(
    unsafe_separator: str,
) -> None:
    # Given: a declared separator contains content that must remain in the document.
    xml = _repeat_xml(separator_zero=unsafe_separator)
    content = {"content_01": [[0, "제목"], [1, "본문"]]}

    # When/Then: rendering fails at separator collection instead of deleting it.
    with pytest.raises(HwpxTemplateRenderError, match="safe blank paragraph"):
        render_repeat_block(xml, content, _repeat_alias_map().blocks)


def test_alias_map_normalizes_separator_contract(tmp_path: Path) -> None:
    # Given: the JSON contract declares general levels and an optional transition.
    contract = {
        "template_id": "separator_test",
        "fields": {},
        "blocks": {
            "본문": {
                "anchor": "content_01",
                "repeat": True,
                "table_scope": False,
                "numbered_level": 0,
                "item_separator_levels": [0, 1, 2, 3],
                "section_transition": {
                    "to_level": 0,
                    "separator_source_level": 0,
                },
                "levels": {
                    str(level): {"field": field_id, "prefix": ""}
                    for level, field_id in enumerate(
                        (
                            "content_01",
                            "body_paragraph_01",
                            "body_bullet_01",
                            "stat_note_01",
                            "detail_note_01",
                        )
                    )
                },
            }
        },
    }
    (tmp_path / "alias_map.json").write_text(
        json.dumps(contract, ensure_ascii=False),
        encoding="utf-8",
    )
    field_ids = frozenset(
        {
            "content_01",
            "body_paragraph_01",
            "body_bullet_01",
            "stat_note_01",
            "detail_note_01",
        }
    )

    # When: the JSON boundary parses the block contract.
    alias_map = load_alias_map(
        tmp_path,
        field_ids=field_ids,
        template_id="separator_test",
    )

    # Then: the renderer receives normalized integer levels and transition values.
    assert alias_map is not None
    block = alias_map.blocks["본문"]
    assert block.item_separator_levels == (0, 1, 2, 3)
    assert block.section_transition == (0, 0)


@pytest.mark.parametrize(
    "item_separator_levels", [[0, True], [0, 9], [0, 0]]
)
def test_alias_map_rejects_invalid_separator_levels(
    tmp_path: Path,
    item_separator_levels: list[int | bool],
) -> None:
    # Given: the separator list cannot be normalized to distinct supported levels.
    contract = {
        "fields": {},
        "blocks": {
            "본문": {
                "anchor": "content_01",
                "repeat": True,
                "table_scope": False,
                "item_separator_levels": item_separator_levels,
                "levels": {
                    "0": {"field": "content_01", "prefix": ""},
                    "1": {"field": "body_paragraph_01", "prefix": ""},
                },
            }
        },
    }
    (tmp_path / "alias_map.json").write_text(
        json.dumps(contract, ensure_ascii=False),
        encoding="utf-8",
    )

    # When/Then: invalid separator levels fail while loading the contract.
    with pytest.raises(AliasMapError, match="item_separator_levels"):
        load_alias_map(
            tmp_path,
            field_ids=frozenset({"content_01", "body_paragraph_01"}),
        )
