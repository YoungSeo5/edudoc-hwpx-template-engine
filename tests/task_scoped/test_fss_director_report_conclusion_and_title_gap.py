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
PARAGRAPH_RE = re.compile(r"<hp:p\b.*?</hp:p>", re.DOTALL)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)


def _paragraph_text(paragraph: str) -> str:
    return re.sub(r"<[^>]+>", "", paragraph)


def _without_layout_cache(paragraph: str) -> str:
    return LINESEGARRAY_RE.sub("", paragraph)


def test_fss_report_prefixes_conclusion_and_preserves_title_gap(
    tmp_path: Path,
) -> None:
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    content["본문"] = [
        [0, "추진 배경"],
        [1, "첫 번째 본문"],
        [0, "주요 내용"],
        [1, "두 번째 본문"],
    ]
    content["결론"] = "검토 결과를 반영한다."
    output = tmp_path / "금감원_원장보고_결론_제목간격.hwpx"

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
    paragraphs = PARAGRAPH_RE.findall(section)
    source_paragraphs = PARAGRAPH_RE.findall(source)
    source_title_index = next(
        index
        for index, paragraph in enumerate(source_paragraphs)
        if "{{content_01}}" in paragraph
    )
    source_gap = _without_layout_cache(source_paragraphs[source_title_index + 1])

    for title, child in (
        ("1. 추진 배경", "□ 첫 번째 본문"),
        ("2. 주요 내용", "□ 두 번째 본문"),
    ):
        title_index = next(
            index
            for index, paragraph in enumerate(paragraphs)
            if title in _paragraph_text(paragraph)
        )
        assert _paragraph_text(paragraphs[title_index + 1]).strip() == ""
        assert _without_layout_cache(paragraphs[title_index + 1]) == source_gap
        assert child in _paragraph_text(paragraphs[title_index + 2])

    visible = [_paragraph_text(paragraph) for paragraph in paragraphs]
    assert "⇨ 검토 결과를 반영한다." in visible
    validation = hwpx.validate_package(output)
    assert validation.ok is True
    assert list(validation.errors) == []


def test_fss_report_rejects_multiline_conclusion() -> None:
    placeholder_map = json.loads(
        (TEMPLATE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field_ids = frozenset(
        entry["field_id"] for entry in placeholder_map["fields"]
    )
    alias_map = load_alias_map(
        TEMPLATE_DIR,
        field_ids=field_ids,
        template_id=placeholder_map.get("template_id"),
    )
    assert alias_map is not None

    with pytest.raises(AliasMapError, match="single paragraph"):
        alias_map.resolve({"결론": "첫째 문단\n둘째 문단"}, field_ids)
