from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
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


def test_render_rejects_source_as_output_without_changing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.hwpx"
    shutil.copyfile(TEMPLATE_DIR / "source.hwpx", source)
    original = source.read_bytes()

    with pytest.raises(HwpxTemplateRenderError, match="source HWPX"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            json.loads(CONTENT_PATH.read_text(encoding="utf-8")),
            source,
            base_hwpx=source,
            execution_context=RenderExecutionContext(
                "원본 보호 테스트",
                datetime(2026, 8, 4, tzinfo=timezone.utc),
            ),
            validate=False,
        )

    assert source.read_bytes() == original
