from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.adapters.hwpx_authoring_resolve import HwpxAuthoringResolveError, resolve
from core.adapters.hwpx_semantic_contract import (
    SemanticContractError,
    bind_semantic_contract,
    load_semantic_contract,
)
from core.adapters.hwpx_template_authoring import load_template_spec
from core.adapters.hwpx_template_input import (
    HwpxTemplateInputError,
    prepare_hwpx_template_input,
)
from core.templates.hwpx_template_registration import (
    TemplateRegistrationError,
    candidate_artifact_digest,
    register_hwpx_template_candidate,
)
from scripts.templates import author_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
REQUEST = ROOT / "tests/fixtures/template-contracts/weekly-report.template_request.json"
SEMANTIC = ROOT / "tests/fixtures/template-contracts/weekly-report.semantic_contract.json"
SPEC = ROOT / "tests/fixtures/template-spec/weekly_report.template_spec.json"
DESIGN = ROOT / "tests/fixtures/template-contracts/edudoc.institution_design.json"


def _candidate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    candidate = tmp_path / "candidate"
    assert author_hwpx_template.main(
        [
            "--template-request", str(REQUEST),
            "--semantic-contract", str(SEMANTIC),
            "--template-spec", str(SPEC),
            "--institution-design", str(DESIGN),
            "--output-dir", str(candidate),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--template-id", "tpl_semantic_runtime_test",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    return candidate


def _review(candidate: Path, approved: bool = True) -> None:
    (candidate / "human_review.json").write_text(
        json.dumps(
            {
                "reviewed": True,
                "approved": approved,
                "reviewed_at": "2026-08-18T00:00:00Z",
                "candidate_digest": candidate_artifact_digest(candidate),
            }
        ),
        encoding="utf-8",
    )


def test_semantic_binding_rejects_unknown_fields_missing_required_fields_and_fixed_conflicts(
    tmp_path: Path,
) -> None:
    semantic = load_semantic_contract(SEMANTIC)
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    raw["sections"][2]["field_id"] = "this_week"
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SemanticContractError, match="absent"):
        bind_semantic_contract(semantic, load_template_spec(unknown))
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    raw["sections"] = raw["sections"][:-1]
    missing = tmp_path / "missing.json"
    missing.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SemanticContractError, match="required"):
        bind_semantic_contract(semantic, load_template_spec(missing))
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    raw["sections"][2]["heading_text"] = "다른 제목"
    conflict = tmp_path / "conflict.json"
    conflict.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SemanticContractError, match="conflicts"):
        bind_semantic_contract(semantic, load_template_spec(conflict))


def test_resolve_rejects_unresolved_visual_property(tmp_path: Path) -> None:
    raw = json.loads(DESIGN.read_text(encoding="utf-8"))
    del raw["defaults"]["styles"]["body"]["color"]
    design = tmp_path / "design.json"
    design.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(HwpxAuthoringResolveError, match="color"):
        resolve(design, load_template_spec(SPEC), bind_semantic_contract(load_semantic_contract(SEMANTIC), load_template_spec(SPEC)))


def test_contract_complete_approval_requires_evidence_and_prepares_without_alias_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _candidate(tmp_path, capsys)
    registry = tmp_path / "registry"
    with pytest.raises(TemplateRegistrationError, match="human visual approval"):
        register_hwpx_template_candidate(candidate, registry_root=registry, approve=True)
    _review(candidate)
    result = register_hwpx_template_candidate(candidate, registry_root=registry, approve=True)
    content = json.loads((result.destination / "content.sample.json").read_text(encoding="utf-8"))
    prepared = prepare_hwpx_template_input(result.destination, content["fields"])
    assert prepared.package_metadata is None


@pytest.mark.parametrize("artifact", ["resolved_authoring_contract.json", "qa.report.json"])
def test_contract_complete_approval_rejects_missing_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], artifact: str
) -> None:
    candidate = _candidate(tmp_path, capsys)
    _review(candidate)
    (candidate / artifact).unlink()
    with pytest.raises(TemplateRegistrationError, match="missing required files"):
        register_hwpx_template_candidate(candidate, registry_root=tmp_path / "registry", approve=True)


def test_required_canonical_content_is_rejected_before_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    candidate = _candidate(tmp_path, capsys)
    with pytest.raises(HwpxTemplateInputError, match="required canonical"):
        prepare_hwpx_template_input(candidate, {"report_period": "2026-08-18"})
