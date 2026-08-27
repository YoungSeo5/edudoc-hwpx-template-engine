"""Registration must reject any candidate outside its designated candidate root.

이 작업 전에는 ``register_hwpx_template_candidate()``와
``scripts/templates/register_hwpx_template.py``가 ``candidate_dir``/``--candidate``에
아무 root 검증도 하지 않았다(``docs/product-workflow-contract.md``가 명시한
implementation gap). 이 파일은 그 fail-closed 경계 하나만 검증한다 —
``candidate_root`` 인자를 생략하면 기존 동작(무제한)이 그대로 유지되는지, 명시
하면 ``..``/절대경로/symlink 우회를 전부 등록 전에 차단하는지, 정상 경로는
그대로 통과하는지를 확인한다.
"""
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
    candidate_root = tmp_path / "candidate-root"
    candidate = _make_candidate(candidate_root / "cand_ok")
    registry_root = tmp_path / "institutions"

    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
        candidate_root=candidate_root,
    )

    assert result.template_id == "ulsan_legislative_notice"
    assert not candidate.exists()


def test_omitting_candidate_root_keeps_prior_unrestricted_behavior(tmp_path: Path) -> None:
    # candidate_root를 생략하면(기본값 None) 기존 호출자(예: 기존 유닛테스트)의
    # 동작이 전혀 바뀌지 않는다 — 이 인자는 opt-in이다.
    candidate = _make_candidate(tmp_path / "anywhere" / "cand")
    registry_root = tmp_path / "institutions"

    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    assert result.template_id == "ulsan_legislative_notice"


def test_dot_dot_escape_is_rejected_before_copying(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate-root"
    candidate_root.mkdir()
    outside = _make_candidate(tmp_path / "outside" / "cand")
    escape_path = candidate_root / ".." / "outside" / "cand"
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            escape_path,
            registry_root=registry_root,
            approve=True,
            candidate_root=candidate_root,
        )

    assert outside.is_dir()
    assert not registry_root.exists()


def test_unrelated_absolute_path_is_rejected_before_copying(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate-root"
    candidate_root.mkdir()
    candidate = _make_candidate(tmp_path / "elsewhere" / "cand")
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
            candidate_root=candidate_root,
        )

    assert candidate.is_dir()
    assert not registry_root.exists()


def test_symlink_pointing_outside_root_is_rejected(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate-root"
    candidate_root.mkdir()
    real_candidate = _make_candidate(tmp_path / "real-outside" / "cand")
    link_path = candidate_root / "cand_link"
    try:
        link_path.symlink_to(real_candidate, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted in this environment")
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="must be inside the candidate root"):
        register_hwpx_template_candidate(
            link_path,
            registry_root=registry_root,
            approve=True,
            candidate_root=candidate_root,
        )

    assert real_candidate.is_dir()
    assert not registry_root.exists()


def test_missing_candidate_root_itself_fails_closed(tmp_path: Path) -> None:
    candidate_root = tmp_path / "does-not-exist"
    candidate = _make_candidate(tmp_path / "cand")
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="candidate root does not exist"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
            candidate_root=candidate_root,
        )


def test_cli_default_candidate_root_rejects_a_candidate_outside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # --candidate-root를 아예 주지 않으면 실제 운영 기본값
    # (sandbox/template-candidates)이 쓰인다 — 실사용 CLI 호출이 기본으로
    # fail-closed임을 보장한다.
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
    assert "must be inside the candidate root" in summary["error"]
    assert candidate.is_dir()


def test_cli_explicit_candidate_root_allows_a_candidate_inside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate_root = tmp_path / "candidate-root"
    candidate = _make_candidate(candidate_root / "cand")

    exit_code = register_hwpx_template.main(
        [
            "--candidate",
            str(candidate),
            "--registry-root",
            str(tmp_path / "institutions"),
            "--candidate-root",
            str(candidate_root),
            "--approve",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["registered"]["template_id"] == "ulsan_legislative_notice"
