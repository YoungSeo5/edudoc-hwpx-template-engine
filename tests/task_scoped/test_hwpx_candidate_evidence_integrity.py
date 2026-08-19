from __future__ import annotations

import json
import shutil
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from core.templates.hwpx_template_registration import (
    TemplateRegistrationError,
    candidate_artifact_digest,
    register_hwpx_template_candidate,
)
from scripts.templates import author_hwpx_template, qa_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
REQUEST = ROOT / "tests/fixtures/template-contracts/weekly-report.template_request.json"
SEMANTIC = ROOT / "tests/fixtures/template-contracts/weekly-report.semantic_contract.json"
SPEC = ROOT / "tests/fixtures/template-spec/weekly_report.template_spec.json"
DESIGN = ROOT / "tests/fixtures/template-contracts/edudoc.institution_design.json"


def _candidate(directory: Path, capsys: pytest.CaptureFixture[str], template_id: str) -> Path:
    candidate = directory / "candidate"
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(REQUEST),
            "--semantic-contract", str(SEMANTIC),
            "--template-spec", str(SPEC),
            "--institution-design", str(DESIGN),
            "--output-dir", str(candidate),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--template-id", template_id,
        ]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    return candidate


def _approve_review(candidate: Path, candidate_digest: str) -> None:
    (candidate / "human_review.json").write_text(
        json.dumps(
            {
                "reviewed": True,
                "approved": True,
                "reviewed_at": "2026-08-18T00:00:00Z",
                "candidate_digest": candidate_digest,
            }
        ),
        encoding="utf-8",
    )


def test_registration_rejects_qa_evidence_copied_from_another_candidate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate_a = _candidate(tmp_path / "a", capsys, "tpl_evidence_a")
    candidate_b = _candidate(tmp_path / "b", capsys, "tpl_evidence_b")
    shutil.copy2(candidate_a / "qa.report.json", candidate_b / "qa.report.json")
    _approve_review(candidate_b, candidate_artifact_digest(candidate_b))

    with pytest.raises(TemplateRegistrationError, match="machine QA evidence"):
        register_hwpx_template_candidate(
            candidate_b,
            registry_root=tmp_path / "registry",
            approve=True,
        )


def test_registration_rejects_candidate_changed_after_machine_qa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _candidate(tmp_path, capsys, "tpl_changed_after_qa")
    _approve_review(candidate, candidate_artifact_digest(candidate))
    template = candidate / "template" / "section0.template.xml"
    template.write_text(template.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(TemplateRegistrationError, match="machine QA evidence"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=tmp_path / "registry",
            approve=True,
        )


def test_registration_rejects_human_review_for_another_candidate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _candidate(tmp_path, capsys, "tpl_wrong_review")
    _approve_review(candidate, "different-candidate")

    with pytest.raises(TemplateRegistrationError, match="human visual approval evidence"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=tmp_path / "registry",
            approve=True,
        )


def test_authoring_makes_final_candidate_artifacts_available_before_qa_digest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    required = (
        "template_request.json",
        "semantic_contract.json",
        "institution_design.json",
        "template_spec.json",
        "separation_rules.json",
        "resolved_authoring_contract.json",
    )
    observed = False
    original_roundtrip = qa_hwpx_template.render_candidate_roundtrip

    def checked_roundtrip(*args, **kwargs):
        nonlocal observed
        assert all((candidate / name).is_file() for name in required)
        observed = True
        return original_roundtrip(*args, **kwargs)

    def in_process_qa(command: list[str]) -> subprocess.CompletedProcess[str]:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = qa_hwpx_template.main(command[2:])
        return subprocess.CompletedProcess(command, exit_code, output.getvalue(), "")

    monkeypatch.setattr(qa_hwpx_template, "render_candidate_roundtrip", checked_roundtrip)
    monkeypatch.setattr(author_hwpx_template, "run_skill_subprocess", in_process_qa)

    assert author_hwpx_template.main(
        [
            "--template-request", str(REQUEST),
            "--semantic-contract", str(SEMANTIC),
            "--template-spec", str(SPEC),
            "--institution-design", str(DESIGN),
            "--output-dir", str(candidate),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--template-id", "tpl_artifacts_before_qa",
        ]
    ) == 0
    assert observed is True
