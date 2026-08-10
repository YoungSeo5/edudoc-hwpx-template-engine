"""``Contents/content.hpf`` 메타데이터 갱신 계약.

최종 문서는 템플릿이 선언한 메타데이터 계약대로 9개 값을 모두 갱신한다.
계약이 없는 템플릿은 문서를 만들지 못하며, 제작 중 후보 왕복 검사는
``content.hpf``를 아예 건드리지 않는다. 이 두 경로의 분리는
``tests/task_scoped/test_hwpx_render_requires_metadata.py``에서 검증한다.

매니페스트는 갱신 대상이 아니므로 원본 그대로 유지한다.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderExecutionContext,
    orchestrate_hwpx_render,
)

ROOT = Path(__file__).resolve().parent.parent
FSS_DIR = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
CONTENT = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_director_report.input.json"
)
_TITLE_RE = re.compile(r"<opf:title(?:\s*/>|>(.*?)</opf:title>)", re.DOTALL)
_MANIFEST_RE = re.compile(r"<opf:manifest>.*?</opf:manifest>", re.DOTALL)
REQUESTED_AT = datetime(2026, 8, 3, 5, 49, 12, tzinfo=timezone.utc)
EXECUTION_CONTEXT = RenderExecutionContext("오영서", REQUESTED_AT)


def _hpf(package: Path) -> str:
    with zipfile.ZipFile(package) as archive:
        return archive.read("Contents/content.hpf").decode("utf-8")


def _meta(xml: str, name: str) -> str | None:
    match = re.search(
        rf'<opf:meta name="{name}"[^>]*>(.*?)</opf:meta>', xml, re.DOTALL
    )
    return match.group(1) if match else None


def _render_fss(tmp_path: Path):
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    output = tmp_path / "금감원_원장보고.hwpx"
    return output, orchestrate_hwpx_render(
        FSS_DIR,
        content,
        output,
        execution_context=EXECUTION_CONTEXT,
    )


def test_content_hpf_title_matches_the_rendered_document_title(tmp_path: Path) -> None:
    output, result = _render_fss(tmp_path)

    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    assert result.title_updated is True
    assert _TITLE_RE.search(_hpf(output)).group(1) == content["제목"]


def test_content_hpf_dates_use_the_execution_request_time(tmp_path: Path) -> None:
    output, _ = _render_fss(tmp_path)

    filled = _hpf(output)
    for name in ("CreatedDate", "ModifiedDate"):
        assert _meta(filled, name) == "2026-08-03T05:49:12Z"


def test_content_hpf_uses_requester_and_report_date(tmp_path: Path) -> None:
    output, _ = _render_fss(tmp_path)

    filled = _hpf(output)
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    assert _meta(filled, "creator") == "오영서"
    assert _meta(filled, "lastsaveby") == "오영서"
    assert _meta(filled, "date") == content["보고일"]


def test_content_hpf_manifest_is_not_reformatted(tmp_path: Path) -> None:
    output, _ = _render_fss(tmp_path)

    assert (
        _MANIFEST_RE.search(_hpf(output)).group(0)
        == _MANIFEST_RE.search(_hpf(FSS_DIR / "source.hwpx")).group(0)
    )


def test_missing_created_date_meta_is_reported_not_ignored(tmp_path: Path) -> None:
    broken = tmp_path / "broken-base.hwpx"
    with zipfile.ZipFile(FSS_DIR / "source.hwpx") as source, zipfile.ZipFile(
        broken, "w"
    ) as destination:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/content.hpf":
                payload = re.sub(
                    rb'<opf:meta name="CreatedDate".*?</opf:meta>',
                    b"",
                    payload,
                    flags=re.DOTALL,
                )
            destination.writestr(info, payload)

    with pytest.raises(HwpxTemplateRenderError, match="CreatedDate"):
        orchestrate_hwpx_render(
            FSS_DIR,
            json.loads(CONTENT.read_text(encoding="utf-8")),
            tmp_path / "출력.hwpx",
            base_hwpx=broken,
            execution_context=EXECUTION_CONTEXT,
        )
