from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.adapters.hwpx_template_renderer import (
    JsonValue,
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
EXPECTED_PREVIEW_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "template-content"
    / "fss_director_report.expected_prvtext.txt"
)
EXECUTION_CONTEXT = RenderExecutionContext(
    "미리보기 테스트 요청자",
    datetime(2026, 8, 4, tzinfo=timezone.utc),
)


def _content() -> dict[str, JsonValue]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_fss_preview_text_matches_approved_expected_text(tmp_path: Path) -> None:
    # Given: 고정 문구와 입력값이 여러 hp:t로 나뉘는 실제 금감원 템플릿이다.
    output = tmp_path / "금감원_원장보고_미리보기.hwpx"

    # When: 담당자 표 치환까지 포함한 최종 HWPX를 생성한다.
    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        _content(),
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    # Then: 미리보기는 구현에서 다시 계산하지 않은 승인 예상 문단과 일치한다.
    with zipfile.ZipFile(output) as package:
        preview_data = package.read("Preview/PrvText.txt")

    expected_lines = EXPECTED_PREVIEW_PATH.read_text(encoding="utf-8").splitlines()
    assert preview_data.decode("utf-8").splitlines() == expected_lines
    assert preview_data.count(b"\r\n") == max(len(expected_lines) - 1, 0)
