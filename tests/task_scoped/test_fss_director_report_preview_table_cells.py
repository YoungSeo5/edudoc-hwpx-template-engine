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


def test_fss_preview_text_wraps_each_table_cell_with_angle_brackets(
    tmp_path: Path,
) -> None:
    content: dict[str, JsonValue] = json.loads(
        CONTENT_PATH.read_text(encoding="utf-8")
    )
    output = tmp_path / "금감원_표_셀_미리보기.hwpx"

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=RenderExecutionContext(
            "미리보기 표 테스트 요청자",
            datetime(2026, 8, 4, tzinfo=timezone.utc),
        ),
    )

    with zipfile.ZipFile(output) as package:
        lines = package.read("Preview/PrvText.txt").decode("utf-8").splitlines()

    assert lines[0] == (
        "<현안(이슈)보고2026. 7. 30.><><가상자산 이상거래 대응 진행현황>"
    )
    assert lines[1] == (
        "<><><□ 현안검토  ☑ 언론보도  □ 국회 등  □ 금융위·증선위  "
        "□ 기타(현황파악)>"
    )
    assert "<☑ 가상자산 시장 변동성이 확대되어 주요 동향을 점검할 필요가 있음.>" in lines
    assert (
        "<디지털금융국><국장 홍길동(☎3000)><팀장 김철수(☎3001)>" in lines
    )
    assert "1. 추진 배경" in lines
    assert "<1. 추진 배경>" not in lines
