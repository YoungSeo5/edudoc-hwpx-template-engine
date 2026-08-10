from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.adapters.hwpx_template_input import (
    RenderExecutionContext,
    prepare_hwpx_template_input,
)
from core.adapters.hwpx_template_renderer import (
    JsonValue,
    render_prepared_hwpx_template,
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
REQUESTED_AT = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _content() -> dict[str, JsonValue]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_fss_input_preparation_separates_render_values_and_metadata() -> None:
    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        _content(),
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )

    assert "제목" not in prepared.render_plan.field_values
    assert prepared.render_plan.field_values["document_title_01"] == (
        "가상자산 이상거래 대응 진행현황"
    )
    assert "content_01" not in prepared.render_plan.field_values
    assert prepared.render_plan.repeat_values["content_01"][0] == [
        0,
        "추진 배경",
    ]
    assert prepared.package_metadata is not None
    assert prepared.package_metadata.subject == "추진 배경, 주요 내용"
    assert prepared.package_metadata.keywords == (
        "언론보도, 디지털금융국, 추진 배경, 주요 내용"
    )


def test_prepared_renderer_does_not_need_human_input_keys(tmp_path: Path) -> None:
    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        _content(),
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )
    output = tmp_path / "prepared.hwpx"

    render_prepared_hwpx_template(
        TEMPLATE_DIR,
        prepared,
        output,
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
        metadata = package.read("Contents/content.hpf").decode("utf-8")
        preview = package.read("Preview/PrvText.txt").decode("utf-8")

    assert "{{" not in section
    assert "<opf:title>가상자산 이상거래 대응 진행현황</opf:title>" in metadata
    assert "1. 추진 배경" in preview
