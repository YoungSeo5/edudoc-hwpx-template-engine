from __future__ import annotations

import hashlib
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


def test_arbitrary_hwpx_generates_stable_template_id_in_all_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: no template ID is supplied for a new source and identity pair.
    candidate = tmp_path / "candidate"
    institution = "테스트기관"
    document_type = "공공계획 ID 계약"
    source_hash = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    identity = "\0".join((institution, document_type, source_hash))
    expected_template_id = (
        f"tpl_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
    )

    # When: the public QA entrypoint creates the candidate.
    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(REFERENCE),
            "--output-dir",
            str(candidate),
            "--institution",
            institution,
            "--document-type",
            document_type,
        ]
    )

    # Then: the deterministic ID is recorded consistently in every content contract.
    summary = json.loads(capsys.readouterr().out)
    template = json.loads((candidate / "template.json").read_text(encoding="utf-8"))
    sample = json.loads(
        (candidate / "content.sample.json").read_text(encoding="utf-8")
    )
    test_content = json.loads(
        (candidate / "content.test.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert summary["template_id_source"] == "generated"
    assert summary["template_id"] == expected_template_id
    assert template["identity"]["template_id"] == expected_template_id
    assert sample["template_id"] == expected_template_id
    assert test_content["template_id"] == expected_template_id
