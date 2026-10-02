"""candidate QA는 sample/test roundtrip에 unresolved placeholder가 남으면
`ok: true`로 넘어가지 않고 실패해야 한다.

지금까지 `qa_hwpx_template.py`는 `leftover_placeholders`를 qa.report.json에
그대로 기록만 하고 `ok: true`로 통과시켰다. candidate QA는 승인 전 마지막
기계 검증 지점이므로, 여기서 걸러지지 않은 unresolved placeholder는 그대로
approved 경로로 넘어갈 수 있었다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _semantic_rules_helpers import write_content_rules_for_ambiguous_nodes  # noqa: E402
from scripts.templates import qa_hwpx_template  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (
    ROOT / "references" / "document-types" / "public-plan"
    / "브라더 공공기관 보고서 양식.hwpx"
)


def test_cli_fails_when_candidate_roundtrip_leaves_unresolved_placeholders(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    sandbox_qa_registry: Path,
) -> None:
    candidate = sandbox_qa_registry / "candidates" / "candidate"
    rules = write_content_rules_for_ambiguous_nodes(REFERENCE, tmp_path / "rules.json")

    real_render = qa_hwpx_template.render_candidate_roundtrip
    calls = {"count": 0}

    def _fake_render(template_dir, content, output_path, **kwargs):
        result = real_render(template_dir, content, output_path, **kwargs)
        calls["count"] += 1
        if calls["count"] == 2:  # test roundtrip: 후보 결함을 시뮬레이션한다.
            result.leftover_placeholders = ["ghost_field"]
        return result

    monkeypatch.setattr(qa_hwpx_template, "render_candidate_roundtrip", _fake_render)

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
            "--rules",
            str(rules),
            "--template-id",
            "brother_leftover_gate",
        ]
    )

    assert exit_code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is False
    assert summary["error_code"] == "unresolved_placeholder"
    assert "ghost_field" in summary["error"]
    # QA는 candidate를 approved로 승격시키지 않는다.
    assert (
        json.loads((candidate / "template.json").read_text(encoding="utf-8"))["status"]
        == "candidate"
    )


def test_cli_succeeds_when_candidate_roundtrip_has_no_leftover_placeholders(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    sandbox_qa_registry: Path,
) -> None:
    """대조군: 정상 candidate는 새 게이트가 생겨도 그대로 통과한다."""
    candidate = sandbox_qa_registry / "candidates" / "candidate"
    rules = write_content_rules_for_ambiguous_nodes(REFERENCE, tmp_path / "rules.json")

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
            "--rules",
            str(rules),
            "--template-id",
            "brother_leftover_gate_clean",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
