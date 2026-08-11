from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.templates import qa_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (
    ROOT
    / "references"
    / "document-types"
    / "public-plan"
    / "브라더 공공기관 보고서 양식.hwpx"
)


def test_arbitrary_hwpx_creates_nonrepeat_candidate_and_strict_roundtrips(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: an HWPX that has no institution-specific alias or repeat contract.
    candidate = tmp_path / "candidate"

    # When: the public QA entrypoint creates a template candidate.
    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(REFERENCE),
            "--output-dir",
            str(candidate),
            "--institution",
            "테스트기관",
            "--document-type",
            "공공계획",
        ]
    )

    # Then: it produces a strictly checked candidate on the ordinary non-repeat path.
    summary = json.loads(capsys.readouterr().out)
    template = json.loads((candidate / "template.json").read_text(encoding="utf-8"))
    placeholder_map = json.loads(
        (candidate / "placeholder_map.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert summary["ok"] is True
    assert summary["strict_validation"] == {
        "roundtrip.sample.hwpx": True,
        "roundtrip.test.hwpx": True,
    }
    assert template["status"] == "candidate"
    assert placeholder_map["layout_contract"] == "layout-context-v1"
    assert placeholder_map["fields"]
    assert not (candidate / "alias_map.json").exists()
    assert (candidate / "roundtrip.sample.hwpx").is_file()
    assert (candidate / "roundtrip.test.hwpx").is_file()
