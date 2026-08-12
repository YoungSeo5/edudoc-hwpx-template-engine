"""core.document_api.render_document_from_source: source file -> approved HWPX.

Proves the new source-content entry point connects source reading, mapping
against the approved template's contract, and final rendering — and that it
refuses to render (never touching ``orchestrate_hwpx_render``) when the
deterministic mapper leaves any field unresolved, instead of shipping a
document with visible ``확인 필요`` placeholders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.adapters.hwpx_template_input import RenderExecutionContext
from core.document_api import HwpxUnresolvedFieldsError, render_document_from_source

EXECUTION_CONTEXT = RenderExecutionContext(
    requester_name="오영서",
    requested_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
)

# No 문의/department/contact block, so only date/title resolve deterministically;
# every judgment field (body, conclusion, ...) and every contact field stays 확인 필요.
MINIMAL_SOURCE = """# 가상자산 이상거래 관련 현황 점검 진행상황

(2026. 7. 9.) 금융감독원 보도자료
"""


def test_render_from_source_refuses_final_render_when_fields_are_unresolved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.md"
    source.write_text(MINIMAL_SOURCE, encoding="utf-8")
    output = tmp_path / "output.hwpx"

    with pytest.raises(HwpxUnresolvedFieldsError) as excinfo:
        render_document_from_source(
            "금융감독원",
            "금감원 원장보고",
            source,
            output,
            EXECUTION_CONTEXT,
        )

    assert "checkbox_line_01" in excinfo.value.unresolved_fields
    assert "conclusion_01" in excinfo.value.unresolved_fields
    assert "director_name_01" in excinfo.value.unresolved_fields
    assert not output.exists()  # the boundary never reached orchestrate_hwpx_render
