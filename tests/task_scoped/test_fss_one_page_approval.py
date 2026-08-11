from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.adapters.hwpx_template_input import RenderExecutionContext
from core.adapters.hwpx_template_renderer import validate_hwpx_output
from core.document_api import render_approved_document

ROOT = Path(__file__).resolve().parents[2]
CONTENT_PATH = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_one_page.input.json"
)


def test_approved_one_page_renders_through_public_document_api(
    tmp_path: Path,
) -> None:
    # Given: the reviewed one-page content contract and an explicit render context.
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    context = RenderExecutionContext(
        requester_name="오영서",
        requested_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    output = tmp_path / "approved-one-page.hwpx"

    # When: the production document API resolves and renders the checked-in template.
    result = render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        content,
        output,
        context,
    )

    # Then: the public approved route returns a complete, strictly valid HWPX.
    validate_hwpx_output(output)
    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")

    assert result.missing_fields == []
    assert result.leftover_placeholders == []
    assert result.unknown_keys == []
    assert "주요 현안 진행상황 및 대응방안" in section
