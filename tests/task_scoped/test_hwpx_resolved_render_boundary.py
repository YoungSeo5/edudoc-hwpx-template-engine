from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import hwpx
import pytest

from core.adapters.hwpx_alias_map import AliasMapError, JsonValue, load_alias_map
from core.adapters.hwpx_template_input import (
    RenderExecutionContext,
    prepare_hwpx_template_input,
    resolve_hwpx_template_input,
)
from core.adapters.hwpx_template_renderer import orchestrate_hwpx_render

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
REQUESTED_AT = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _content() -> dict[str, JsonValue]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_resolved_content_separates_semantic_metadata_from_render_plan() -> None:
    resolved = resolve_hwpx_template_input(TEMPLATE_DIR, _content())

    assert resolved.metadata is not None
    assert resolved.metadata.title == "가상자산 이상거래 대응 진행현황"
    assert resolved.metadata.subject == "추진 배경, 주요 내용"
    assert resolved.metadata.description == (
        "3분기 중 상시감시 체계 고도화를 추진한다."
    )
    assert resolved.metadata.report_date == "2026. 7. 30."
    assert resolved.metadata.keywords == (
        "언론보도, 디지털금융국, 추진 배경, 주요 내용"
    )
    assert resolved.render_plan.field_values["checkbox_line_01"].startswith(
        "□ 현안검토  ☑ 언론보도"
    )
    assert "content_01" not in resolved.render_plan.field_values
    assert resolved.render_plan.repeat_values["content_01"][0] == [
        0,
        "추진 배경",
    ]
    assert set(resolved.render_plan.repeat_blocks) == {"content_01"}
    assert not hasattr(resolved.render_plan, "alias_map")


def test_prepared_content_keeps_only_finished_metadata_and_render_plan() -> None:
    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        _content(),
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )

    assert prepared.package_metadata is not None
    assert prepared.package_metadata.creator == "오영서"
    assert prepared.package_metadata.subject == "추진 배경, 주요 내용"
    assert prepared.package_metadata.keywords == (
        "언론보도, 디지털금융국, 추진 배경, 주요 내용"
    )
    assert prepared.render_plan.repeat_values["content_01"][0] == [
        0,
        "추진 배경",
    ]
    assert not hasattr(prepared, "alias_map")


def test_alias_map_rejects_metadata_field_outside_fields() -> None:
    invalid_contract = (
        ROOT
        / "tests"
        / "fixtures"
        / "alias-maps"
        / "fss_invalid_metadata_field"
    )

    with pytest.raises(AliasMapError, match="metadata.*없는필드"):
        load_alias_map(
            invalid_contract,
            field_ids=frozenset(
                {"date_01", "title_01", "conclusion_01", "content_01"}
            ),
            template_id="fss_director_report",
        )


def test_fss_renderer_route_uses_the_thin_orchestrator() -> None:
    template_config = json.loads(
        (TEMPLATE_DIR / "template.json").read_text(encoding="utf-8")
    )

    assert template_config["renderer"]["route"] == (
        "core.adapters.hwpx_template_renderer:orchestrate_hwpx_render"
    )


def test_resolved_boundary_renders_a_strict_fss_package(tmp_path: Path) -> None:
    output = tmp_path / "resolved-boundary.hwpx"

    result = orchestrate_hwpx_render(
        TEMPLATE_DIR,
        _content(),
        output,
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
        metadata = package.read("Contents/content.hpf").decode("utf-8")
        preview = package.read("Preview/PrvText.txt").decode("utf-8")
    validation = hwpx.validate_package(output)
    assert result.leftover_placeholders == []
    assert "{{" not in section
    assert (
        '<opf:meta name="subject" content="text">'
        "추진 배경, 주요 내용</opf:meta>"
    ) in metadata
    assert "1. 추진 배경" in preview
    assert validation.ok is True
    assert list(validation.errors) == []
