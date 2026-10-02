"""Registration accepts only candidates inside its external registry."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core.templates.hwpx_template_registration import (
    TemplateRegistrationError,
    register_hwpx_template_candidate,
)
from scripts.templates import register_hwpx_template


def _make_candidate(
    path: Path,
    *,
    institution: str = "울산광역시",
    document_type: str = "입법예고",
    template_id: str = "ulsan_legislative_notice",
) -> Path:
    """분리 단계가 남기는 후보 폴더의 최소 형태를 만든다."""
    (path / "raw").mkdir(parents=True)
    (path / "template").mkdir(parents=True)
    (path / "raw" / "section0.xml").write_text("<sec/>", encoding="utf-8")
    (path / "template" / "section0.template.xml").write_text("<sec/>", encoding="utf-8")
    (path / "placeholder_map.json").write_text("{}", encoding="utf-8")
    (path / "content.sample.json").write_text("{}", encoding="utf-8")
    (path / "template.review.md").write_text("# review\n", encoding="utf-8")
    with zipfile.ZipFile(path / "source.hwpx", "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
    (path / "template.json").write_text(
        json.dumps(
            {
                "identity": {
                    "institution": institution,
                    "document_type": document_type,
                    "extends": None,
                    "template_id": template_id,
                    "template_name": document_type,
                },
                "reference_format": "hwpx",
                "reference_path": "reference.hwpx",
                "status": "candidate",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_candidate_inside_root_registers_normally(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate = _make_candidate(candidate_root / "cand_ok")

    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    assert result.template_id == "ulsan_legislative_notice"
    assert not candidate.exists()


def test_candidate_outside_registry_is_rejected_without_opt_out(tmp_path: Path) -> None:
    candidate = _make_candidate(tmp_path / "anywhere" / "cand")
    registry_root = tmp_path / "registry"
    (registry_root / "candidates").mkdir(parents=True)

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(candidate, registry_root=registry_root, approve=True)


def test_candidate_from_another_registry_is_rejected(tmp_path: Path) -> None:
    candidate = _make_candidate(tmp_path / "first" / "candidates" / "cand")
    target = tmp_path / "second"
    (target / "candidates").mkdir(parents=True)

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(candidate, registry_root=target, approve=True)

    assert candidate.is_dir()
    assert not (target / "approved").exists()


def test_dot_dot_escape_is_rejected_before_copying(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate_root.mkdir(parents=True)
    outside = _make_candidate(tmp_path / "outside" / "cand")
    escape_path = candidate_root / ".." / ".." / "outside" / "cand"

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            escape_path,
            registry_root=registry_root,
            approve=True,
        )

    assert outside.is_dir()
    assert not (registry_root / "approved").exists()


def test_unrelated_absolute_path_is_rejected_before_copying(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate_root.mkdir(parents=True)
    candidate = _make_candidate(tmp_path / "elsewhere" / "cand")

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert candidate.is_dir()
    assert not (registry_root / "approved").exists()


def test_symlink_pointing_outside_root_is_rejected(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate_root.mkdir(parents=True)
    real_candidate = _make_candidate(tmp_path / "real-outside" / "cand")
    link_path = candidate_root / "cand_link"
    try:
        link_path.symlink_to(real_candidate, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted in this environment")

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            link_path,
            registry_root=registry_root,
            approve=True,
        )

    assert real_candidate.is_dir()
    assert not (registry_root / "approved").exists()


def test_missing_candidate_root_itself_fails_closed(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate = _make_candidate(tmp_path / "cand")

    with pytest.raises(TemplateRegistrationError, match="candidate root does not exist"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )


def test_cli_default_candidate_root_rejects_a_candidate_outside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 저장소 내부 registry는 설정 단계에서 거부되어야 한다.
    candidate = _make_candidate(tmp_path / "cand")

    exit_code = register_hwpx_template.main(
        [
            "--candidate",
            str(candidate),
            "--registry-root",
            str(tmp_path / "institutions"),
            "--approve",
        ]
    )

    assert exit_code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is False
    assert "저장소 또는 스킬 설치 폴더 밖" in summary["error"]
    assert candidate.is_dir()


def test_cli_uses_resolved_registry_candidate_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_root = tmp_path / "registry"
    candidate_root = registry_root / "candidates"
    candidate = _make_candidate(candidate_root / "cand")
    monkeypatch.setattr(register_hwpx_template, "resolve_registry_root", lambda explicit: registry_root)
    monkeypatch.setattr(register_hwpx_template, "connect_registry", lambda root: None)

    exit_code = register_hwpx_template.main(
        [
            "--candidate",
            str(candidate),
            "--registry-root",
            str(registry_root),
            "--approve",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["registered"]["template_id"] == "ulsan_legislative_notice"
