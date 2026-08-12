"""core.adapters.hwpx_source_input: source file -> normalized Markdown text.

Proves each supported source format (.md, .txt, .hwpx) reduces to plain
Markdown text the mapper can read, and that an unsupported or missing source
is refused rather than silently skipped.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.adapters.hwpx_template_input import HwpxTemplateInputError
from core.adapters.hwpx_source_input import read_source_as_markdown

ROOT = Path(__file__).resolve().parents[2]
FSS_SOURCE_HWPX = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고" / "source.hwpx"
)


def test_reads_md_source_as_utf8_text(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("# 제목\n\n본문 내용", encoding="utf-8")

    assert read_source_as_markdown(source) == "# 제목\n\n본문 내용"


def test_reads_txt_source_as_utf8_text(tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    source.write_text("제목\n\n본문 내용", encoding="utf-8")

    assert read_source_as_markdown(source) == "제목\n\n본문 내용"


def test_reads_hwpx_source_via_python_hwpx_markdown_export() -> None:
    markdown = read_source_as_markdown(FSS_SOURCE_HWPX)

    assert markdown.strip() != ""
    assert "{{" not in markdown  # placeholder syntax never leaks into extracted text


def test_rejects_unsupported_source_suffix(tmp_path: Path) -> None:
    source = tmp_path / "report.docx"
    source.write_text("content", encoding="utf-8")

    with pytest.raises(HwpxTemplateInputError, match="unsupported source file type"):
        read_source_as_markdown(source)


def test_rejects_missing_source_file(tmp_path: Path) -> None:
    with pytest.raises(HwpxTemplateInputError, match="source file not found"):
        read_source_as_markdown(tmp_path / "missing.md")
