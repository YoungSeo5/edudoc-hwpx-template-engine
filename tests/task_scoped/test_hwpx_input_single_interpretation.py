"""입력 준비가 원본 content를 한 번만 해석하는지 확인한다.

렌더 값과 content.hpf 메타데이터는 같은 flatten 결과에서 나와야 한다.
변경 전에는 메타데이터가 원본 content를 다시 flatten/read 했다.
"""
from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path

from core.adapters.hwpx_template_input import resolve_hwpx_template_input

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


class _CountingContent(Mapping):
    """원본 입력을 몇 번 훑었는지 세는 매핑."""

    def __init__(self, data: dict) -> None:
        self._data = data
        self.scan_count = 0

    def __getitem__(self, key: str):
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        self.scan_count += 1
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def _content() -> dict:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def test_metadata_reuses_the_single_flattened_input() -> None:
    content = _CountingContent(_content())

    resolved = resolve_hwpx_template_input(TEMPLATE_DIR, content)

    assert content.scan_count == 1
    assert resolved.metadata is not None
    assert resolved.metadata.keywords == (
        "언론보도, 디지털금융국, 추진 배경, 주요 내용"
    )
    assert resolved.render_plan.field_values["checkbox_line_01"] == (
        "□ 현안검토  ☑ 언론보도  □ 국회 등  □ 금융위·증선위  □ 기타(현황파악)"
    )


def test_field_id_keyed_input_reaches_metadata_from_the_same_scan() -> None:
    raw = _content()
    del raw["보고일"]
    raw["date_01"] = "2026. 7. 31."
    content = _CountingContent(raw)

    resolved = resolve_hwpx_template_input(TEMPLATE_DIR, content)

    assert content.scan_count == 1
    assert resolved.metadata is not None
    assert resolved.metadata.report_date == "2026. 7. 31."
