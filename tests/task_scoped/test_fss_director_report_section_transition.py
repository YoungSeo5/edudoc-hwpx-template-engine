from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
PARAGRAPH_RE = re.compile(r"<hp:p\b.*?</hp:p>", re.DOTALL)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


def _paragraph_text(paragraph: str) -> str:
    return re.sub(r"<[^>]+>", "", paragraph)


def _paragraph_style(paragraph: str) -> tuple[str, str]:
    para = re.search(r'paraPrIDRef="([^"]+)"', paragraph)
    char = re.search(r'charPrIDRef="([^"]+)"', paragraph)
    assert para is not None
    assert char is not None
    return para.group(1), char.group(1)


@pytest.mark.parametrize("preceding_level", range(5))
def test_fss_report_uses_title_separator_before_level_zero(
    tmp_path: Path,
    preceding_level: int,
) -> None:
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    content["본문"] = [
        [preceding_level, "앞 항목"],
        [0, "다음 제목"],
    ]
    output = tmp_path / f"section-transition-{preceding_level}.hwpx"

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    paragraphs = PARAGRAPH_RE.findall(section)
    current_index = next(
        index
        for index, paragraph in enumerate(paragraphs)
        if "앞 항목" in _paragraph_text(paragraph)
    )
    next_index = next(
        index
        for index, paragraph in enumerate(paragraphs)
        if "다음 제목" in _paragraph_text(paragraph)
    )
    assert next_index == current_index + 2
    assert _paragraph_text(paragraphs[current_index + 1]).strip() == ""
    assert _paragraph_style(paragraphs[current_index + 1]) == ("22", "14")
