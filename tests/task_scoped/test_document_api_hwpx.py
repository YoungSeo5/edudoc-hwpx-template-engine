from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.adapters.hwpx_template_input import RenderExecutionContext
from core.adapters.hwpx_template_renderer import HwpxTemplateRenderError, JsonValue
from core.document_api import (
    get_template_contract,
    list_approved_templates,
    render_approved_document,
    validate_template_content,
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
EXECUTION_CONTEXT = RenderExecutionContext(
    requester_name="오영서",
    requested_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
)


def _content() -> dict[str, JsonValue]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_document_api_lists_only_approved_hwpx_templates() -> None:
    approved = list_approved_templates()
    template_ids = {candidate.identity.template_id for candidate in approved}

    assert "fss_director_report" in template_ids
    assert "fss_one_page" not in template_ids
    assert "fss_virtual_asset_report" not in template_ids
    assert all(candidate.status == "approved" for candidate in approved)
    assert all(candidate.reference_format == "hwpx" for candidate in approved)


def test_document_api_returns_existing_template_contract() -> None:
    placeholder_map, alias_map = get_template_contract(
        "금융감독원",
        "금감원 원장보고",
    )

    assert placeholder_map["template_id"] == "fss_director_report"
    assert alias_map is not None
    assert alias_map.aliases["제목"] == "document_title_01"
    assert alias_map.choices["보고구분"].options == (
        "현안검토",
        "언론보도",
        "국회 등",
        "금융위·증선위",
        "기타(현황파악)",
    )
    assert alias_map.metadata is not None


def test_document_api_validates_with_existing_input_preparation() -> None:
    prepared = validate_template_content(
        "금융감독원",
        "금감원 원장보고",
        _content(),
        EXECUTION_CONTEXT,
    )

    assert prepared.template_id == "fss_director_report"
    assert prepared.render_plan.field_values["document_title_01"] == (
        "가상자산 이상거래 대응 진행현황"
    )
    assert prepared.package_metadata.creator == "오영서"


def test_document_api_renders_with_existing_orchestrator(tmp_path: Path) -> None:
    output = tmp_path / "document-api.hwpx"

    result = render_approved_document(
        "금융감독원",
        "금감원 원장보고",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(result.output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
        metadata = package.read("Contents/content.hpf").decode("utf-8")

    assert "{{" not in section
    assert "<opf:title>가상자산 이상거래 대응 진행현황</opf:title>" in metadata
    assert result.title_updated is True


def test_document_api_preserves_source_overwrite_guard() -> None:
    with pytest.raises(
        HwpxTemplateRenderError,
        match="output_path must not reference the source HWPX",
    ):
        render_approved_document(
            "금융감독원",
            "금감원 원장보고",
            _content(),
            TEMPLATE_DIR / "source.hwpx",
            EXECUTION_CONTEXT,
        )
