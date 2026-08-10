from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import hwpx

from core.adapters.hwpx_template_renderer import (
    RenderExecutionContext,
    orchestrate_hwpx_render,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
)
CONTENT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "template-content"
    / "fss_director_report.input.json"
)
LINESEGARRAY_RE = re.compile(
    r"<hp:linesegarray\b[^>]*/>|<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>",
    re.DOTALL,
)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


def _paragraph_with(xml: str, text: str) -> str:
    match = re.search(
        rf"<hp:p\b[^>]*>(?:(?!<hp:p\b).)*?{re.escape(text)}"
        rf"(?:(?!<hp:p\b).)*?</hp:p>",
        xml,
        re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _style_xml(paragraph: str) -> str:
    without_cache = LINESEGARRAY_RE.sub("", paragraph)
    return re.sub(
        r"(<hp:t\b[^>]*>).*?(</hp:t>)",
        r"\1{{text}}\2",
        without_cache,
        flags=re.DOTALL,
    )


def test_fss_body_numbers_multiple_section_titles_and_preserves_styles(
    tmp_path: Path,
) -> None:
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    content.pop("항목제목", None)
    content["본문"] = [
        [0, "추진 배경"],
        [1, "첫 번째 본문"],
        [2, "세부 내용"],
        [0, "주요 내용"],
        [1, "두 번째 본문"],
    ]
    output = tmp_path / "금감원_원장보고_다중항목.hwpx"

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    source = (TEMPLATE_DIR / "template" / "section0.template.xml").read_text(
        encoding="utf-8"
    )
    visible = [
        re.sub(r"<[^>]+>", "", text)
        for text in re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", section, re.DOTALL)
    ]
    expected = [
        "1. 추진 배경",
        "□ 첫 번째 본문",
        "◦ 세부 내용",
        "2. 주요 내용",
        "□ 두 번째 본문",
    ]

    positions = [visible.index(text) for text in expected]
    assert positions == sorted(positions)
    assert visible.count("1. 추진 배경") == 1
    assert "1. 추진 배경(HY헤드라인M 16)" not in visible
    assert "{{" not in section

    title_style = _style_xml(_paragraph_with(source, "{{content_01}}"))
    square_style = _style_xml(_paragraph_with(source, "{{body_paragraph_01}}"))
    circle_style = _style_xml(_paragraph_with(source, "{{body_bullet_01}}"))
    assert _style_xml(_paragraph_with(section, expected[0])) == title_style
    assert _style_xml(_paragraph_with(section, expected[3])) == title_style
    assert _style_xml(_paragraph_with(section, expected[1])) == square_style
    assert _style_xml(_paragraph_with(section, expected[4])) == square_style
    assert _style_xml(_paragraph_with(section, expected[2])) == circle_style

    validation = hwpx.validate_package(output)
    assert validation.ok is True
    assert list(validation.errors) == []
