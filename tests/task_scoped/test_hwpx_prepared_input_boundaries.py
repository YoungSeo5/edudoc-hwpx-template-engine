from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.adapters.hwpx_template_input import prepare_hwpx_template_input
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderExecutionContext,
    fill_template_sections,
    render_prepared_hwpx_template,
)
from scripts.templates import render_hwpx_template as render_cli

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


def _content() -> dict:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_input_preparation_requires_validated_execution_context() -> None:
    context = RenderExecutionContext("오영서", REQUESTED_AT)

    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        _content(),
        execution_context=context,
    )

    assert prepared.package_metadata is not None
    assert prepared.package_metadata.creator == "오영서"


def test_prepared_renderer_rejects_another_template_id(tmp_path: Path) -> None:
    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        _content(),
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )
    other_template = tmp_path / "other-template"
    other_template.mkdir()
    (other_template / "placeholder_map.json").write_text(
        json.dumps({"template_id": "other_template", "fields": []}),
        encoding="utf-8",
    )

    with pytest.raises(HwpxTemplateRenderError, match="template_id mismatch"):
        render_prepared_hwpx_template(
            other_template,
            prepared,
            tmp_path / "mixed.hwpx",
            base_hwpx=TEMPLATE_DIR / "source.hwpx",
            validate=False,
        )


def test_fill_template_sections_keeps_render_error_contract(
    tmp_path: Path,
) -> None:
    with pytest.raises(HwpxTemplateRenderError) as caught:
        fill_template_sections(tmp_path, {})

    assert type(caught.value) is HwpxTemplateRenderError


def test_approved_template_cli_renders_after_boundary_refactor(
    tmp_path: Path,
) -> None:
    content_path = tmp_path / "content.json"
    content_path.write_text(
        json.dumps(
            {"template_id": "fss_director_report", "fields": _content()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "rendered.hwpx"
    exit_code = render_cli.main(
        [
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원장보고",
            "--content",
            str(content_path),
            "--output",
            str(output),
            "--requester-name",
            "오영서",
        ]
    )

    assert exit_code == 0
    assert output.is_file()
