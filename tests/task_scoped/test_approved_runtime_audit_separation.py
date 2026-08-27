from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core.templates.hwpx_template_registration import (
    TemplateRegistrationError,
    register_hwpx_template_candidate,
)


def _candidate(path: Path) -> Path:
    (path / "raw").mkdir(parents=True)
    (path / "template").mkdir()
    (path / "raw" / "section0.xml").write_text("<sec/>", encoding="utf-8")
    (path / "template" / "section0.template.xml").write_text(
        "<sec/>", encoding="utf-8"
    )
    (path / "template" / "header.xml").write_text("<head/>", encoding="utf-8")
    (path / "template" / "content.hpf").write_text("evidence", encoding="utf-8")
    (path / "placeholder_map.json").write_text("{}", encoding="utf-8")
    (path / "alias_map.json").write_text('{"fields": {}}', encoding="utf-8")
    (path / "template_spec.json").write_text('{"kind": "runtime"}', encoding="utf-8")
    (path / "family_recipe.json").write_text('{"native_page_count": 1}', encoding="utf-8")
    for name in (
        "content.sample.json",
        "content.test.json",
        "qa.report.json",
        "human_review.json",
        "separation_rules.json",
        "semantic_classification.json",
        "resolved_authoring_contract.json",
        "institution_design.json",
        "institution_design.provenance.json",
        "template_request.json",
    ):
        (path / name).write_text("{}", encoding="utf-8")
    for name in ("extraction_report.md", "template.review.md"):
        (path / name).write_text("# evidence\n", encoding="utf-8")
    for name in ("roundtrip.sample.hwpx", "roundtrip.test.hwpx"):
        (path / name).write_bytes(b"evidence")
    with zipfile.ZipFile(path / "source.hwpx", "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
    (path / "template.json").write_text(
        json.dumps(
            {
                "identity": {
                    "institution": "edudoc",
                    "document_type": "runtime-audit-demo",
                    "extends": None,
                    "template_id": "runtime_audit_demo",
                    "template_name": "runtime-audit-demo",
                },
                "reference_format": "hwpx",
                "reference_path": "source.hwpx",
                "status": "candidate",
            }
        ),
        encoding="utf-8",
    )
    return path


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_registration_separates_approved_runtime_from_audit_evidence(
    tmp_path: Path,
) -> None:
    # Given: runtime artifacts and approval evidence share one candidate directory.
    candidate = _candidate(tmp_path / "candidate")
    registry_root = tmp_path / "institutions"

    # When: the candidate is explicitly approved.
    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    # Then: approved is runtime-only and every excluded artifact is in audit.
    assert _relative_files(result.destination) == {
        "alias_map.json",
        "content.sample.json",
        "family_recipe.json",
        "placeholder_map.json",
        "source.hwpx",
        "template.json",
        "template/header.xml",
        "template/section0.template.xml",
        "template_spec.json",
    }
    # audit lives inside registry_root (the private submodule boundary), never
    # beside it — a sibling directory would land in the public superproject.
    audit = registry_root / "_audit" / "runtime_audit_demo"
    assert _relative_files(audit) == {
        "content.test.json",
        "extraction_report.md",
        "human_review.json",
        "institution_design.json",
        "institution_design.provenance.json",
        "qa.report.json",
        "raw/section0.xml",
        "resolved_authoring_contract.json",
        "roundtrip.sample.hwpx",
        "roundtrip.test.hwpx",
        "semantic_classification.json",
        "separation_rules.json",
        "template/content.hpf",
        "template.review.md",
        "template_request.json",
    }
    assert json.loads((result.destination / "template.json").read_text())["status"] == "approved"
    assert not candidate.exists()
    # And: nothing lands beside registry_root, where a real registry_root is a
    # private submodule and a sibling directory would be public-repo-tracked.
    assert not (registry_root.parent / "audit").exists()


def test_failed_registration_confirmation_removes_runtime_and_audit_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid candidate whose final registry confirmation will fail.
    candidate = _candidate(tmp_path / "candidate")
    registry_root = tmp_path / "institutions"
    monkeypatch.setattr(
        "core.templates.hwpx_template_registration.TemplateRegistry.find",
        lambda self, institution, document_type: None,
    )

    # When: registration reaches final confirmation.
    with pytest.raises(TemplateRegistrationError, match="could not be confirmed"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    # Then: only the original candidate remains.
    assert candidate.is_dir()
    assert not (registry_root / "edudoc" / "runtime-audit-demo").exists()
    assert not (registry_root / "_audit" / "runtime_audit_demo").exists()
