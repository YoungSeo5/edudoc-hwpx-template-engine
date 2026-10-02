from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _semantic_rules_helpers import write_content_rules_for_ambiguous_nodes  # noqa: E402
from scripts.templates import qa_hwpx_template  # noqa: E402
from core.document_api import list_approved_templates  # noqa: E402


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
    registry_root = tmp_path / "registry"
    candidate = registry_root / "candidates" / "candidate"
    candidate.parent.mkdir(parents=True)
    rules = write_content_rules_for_ambiguous_nodes(REFERENCE, tmp_path / "rules.json")

    # When: the public QA entrypoint creates a template candidate.
    exit_code = qa_hwpx_template._run(argparse.Namespace(
        source=REFERENCE, output_dir=candidate, candidate_id=None,
        institution="테스트기관", document_type="공공계획", template_id=None,
        rules=rules, contract_artifact_dir=None, required_native_pages=None,
    ), registry_root)

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
    assert list_approved_templates(registry_root=registry_root / "approved") == ()
    assert placeholder_map["layout_contract"] == "layout-context-v1"
    assert placeholder_map["fields"]
    assert not (candidate / "alias_map.json").exists()
    assert (candidate / "roundtrip.sample.hwpx").is_file()
    assert (candidate / "roundtrip.test.hwpx").is_file()
    assert list((registry_root / "_tmp").iterdir()) == []


def test_arbitrary_hwpx_generates_stable_template_id_in_all_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: no template ID is supplied for a new source and identity pair.
    registry_root = tmp_path / "registry"
    candidate = registry_root / "candidates" / "candidate"
    candidate.parent.mkdir(parents=True)
    institution = "테스트기관"
    document_type = "공공계획 ID 계약"
    source_hash = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    identity = "\0".join((institution, document_type, source_hash))
    expected_template_id = (
        f"tpl_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
    )
    rules = write_content_rules_for_ambiguous_nodes(REFERENCE, tmp_path / "rules.json")

    # When: the public QA entrypoint creates the candidate.
    exit_code = qa_hwpx_template._run(argparse.Namespace(
        source=REFERENCE, output_dir=candidate, candidate_id=None,
        institution=institution, document_type=document_type, template_id=None,
        rules=rules, contract_artifact_dir=None, required_native_pages=None,
    ), registry_root)

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
