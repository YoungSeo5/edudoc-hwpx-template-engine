"""승인된 HWPX 템플릿 후보의 등록 동작을 확인한다.

등록 실행 → 정식 경로 생성 → status approved → registry.find() 성공 →
중복 등록 중단까지가 이 작업의 요구사항이다. 변경 전에는 이 경로를
수행하는 코드 자체가 없었다.

리뷰 후속: 되돌릴 수 없는 복사·승인 단계에 들어가기 전에 registry가 실제로
읽을 수 있는 후보인지 확인하고, 확인에 실패하면 후보를 그대로 남긴다.
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
from core.templates.registry import TemplateRegistry
from scripts.templates import register_hwpx_template


def _make_candidate(
    path: Path,
    *,
    institution: str = "울산광역시",
    document_type: str = "입법예고",
    template_id: str = "ulsan_legislative_notice",
    status: str = "candidate",
    omit_reference_path: bool = False,
) -> Path:
    """분리 단계가 남기는 후보 폴더의 최소 형태를 만든다."""
    (path / "raw").mkdir(parents=True)
    (path / "template").mkdir(parents=True)
    (path / "raw" / "section0.xml").write_text("<sec/>", encoding="utf-8")
    (path / "template" / "section0.template.xml").write_text("<sec/>", encoding="utf-8")
    (path / "placeholder_map.json").write_text("{}", encoding="utf-8")
    (path / "content.sample.json").write_text("{}", encoding="utf-8")
    (path / "template.review.md").write_text("# review\n", encoding="utf-8")
    # source.hwpx는 렌더의 self-contained 기반이라 실제 패키지여야 한다.
    with zipfile.ZipFile(path / "source.hwpx", "w") as package:
        package.writestr("mimetype", "application/hwp+zip")
    data = {
        "identity": {
            "institution": institution,
            "document_type": document_type,
            "extends": None,
            "template_id": template_id,
            "template_name": document_type,
        },
        "reference_format": "hwpx",
        "status": status,
    }
    if not omit_reference_path:
        data["reference_path"] = "reference.hwpx"
    (path / "template.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_registration_creates_official_path_and_registry_finds_it(tmp_path: Path) -> None:
    candidate = _make_candidate(tmp_path / "sandbox" / "ulsan")
    registry_root = tmp_path / "institutions"

    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    destination = registry_root / "울산광역시" / "입법예고"
    assert result.destination == destination
    assert result.template_id == "ulsan_legislative_notice"
    assert not candidate.exists()
    assert (destination / "source.hwpx").is_file()
    assert (destination / "raw" / "section0.xml").is_file()

    data = json.loads((destination / "template.json").read_text(encoding="utf-8"))
    assert data["status"] == "approved"

    registered = TemplateRegistry(registry_root).find("울산광역시", "입법예고")
    assert registered is not None
    assert registered.identity.template_id == "ulsan_legislative_notice"


def test_duplicate_destination_path_stops_registration(tmp_path: Path) -> None:
    registry_root = tmp_path / "institutions"
    register_hwpx_template_candidate(
        _make_candidate(tmp_path / "first"),
        registry_root=registry_root,
        approve=True,
    )
    second = _make_candidate(tmp_path / "second", template_id="ulsan_other_notice")

    with pytest.raises(TemplateRegistrationError, match="destination path already exists"):
        register_hwpx_template_candidate(
            second,
            registry_root=registry_root,
            approve=True,
        )

    assert second.is_dir()
    data = json.loads((second / "template.json").read_text(encoding="utf-8"))
    assert data["status"] == "candidate"


def test_duplicate_template_id_stops_registration(tmp_path: Path) -> None:
    registry_root = tmp_path / "institutions"
    register_hwpx_template_candidate(
        _make_candidate(tmp_path / "first"),
        registry_root=registry_root,
        approve=True,
    )
    same_id = _make_candidate(
        tmp_path / "second",
        institution="부산광역시",
        document_type="입법예고",
    )

    with pytest.raises(TemplateRegistrationError, match="already registered"):
        register_hwpx_template_candidate(
            same_id,
            registry_root=registry_root,
            approve=True,
        )

    assert not (registry_root / "부산광역시").exists()
    assert same_id.is_dir()


def test_registration_requires_explicit_approval(tmp_path: Path) -> None:
    candidate = _make_candidate(tmp_path / "ulsan")
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="explicit approval"):
        register_hwpx_template_candidate(candidate, registry_root=registry_root)

    assert candidate.is_dir()
    assert not registry_root.exists()


@pytest.mark.parametrize(
    ("break_candidate", "message"),
    [
        (lambda path: (path / "source.hwpx").unlink(), "missing required files"),
        (lambda path: (path / "raw" / "section0.xml").unlink(), "missing required files"),
    ],
)
def test_incomplete_candidate_stops_registration(
    tmp_path: Path,
    break_candidate,
    message: str,
) -> None:
    candidate = _make_candidate(tmp_path / "ulsan")
    break_candidate(candidate)
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match=message):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert not registry_root.exists()


def test_already_approved_candidate_stops_registration(tmp_path: Path) -> None:
    candidate = _make_candidate(tmp_path / "ulsan", status="approved")
    registry_root = tmp_path / "institutions"

    with pytest.raises(TemplateRegistrationError, match="status='approved'"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert not registry_root.exists()


# --- 리뷰 후속: 되돌릴 수 없는 단계 전에 걸러야 하는 것들 ---


def test_candidate_unreadable_by_registry_is_rejected_before_copying(
    tmp_path: Path,
) -> None:
    """결함 1: registry가 못 읽는 후보가 복사·승인 뒤에야 드러나면 안 된다.

    수정 전에는 `reference_path` 없는 후보가 검증을 통과해 이동·approved까지
    끝난 뒤 registry.find()에서 KeyError가 났고, 후보는 사라지고 정식 경로에는
    approved가 남았다.
    """
    candidate = _make_candidate(tmp_path / "ulsan", omit_reference_path=True)
    registry_root = tmp_path / "institutions"

    with pytest.raises(
        TemplateRegistrationError,
        match="cannot be read as a template candidate",
    ):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert candidate.is_dir()
    assert (candidate / "template.json").is_file()
    assert not registry_root.exists()


def test_cli_reports_an_unreadable_candidate_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """결함 2: CLI가 traceback 대신 JSON 요약으로 보고해야 한다."""
    candidate = _make_candidate(tmp_path / "ulsan", omit_reference_path=True)

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
    assert summary["registered"] is None
    assert "cannot be read as a template candidate" in summary["error"]


def test_unreadable_existing_template_names_the_offending_file(tmp_path: Path) -> None:
    """결함 3: 무관한 깨진 template.json이 원인을 밝히지 않은 채 등록을 막으면 안 된다."""
    registry_root = tmp_path / "institutions"
    broken = registry_root / "남의기관" / "남의유형" / "template.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{ broken", encoding="utf-8")
    candidate = _make_candidate(tmp_path / "ulsan")

    with pytest.raises(TemplateRegistrationError) as error:
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    message = str(error.value)
    assert "template_id conflict" in message
    assert "남의기관" in message
    assert candidate.is_dir()


def test_non_package_source_hwpx_stops_registration(tmp_path: Path) -> None:
    """결함 4: 렌더 불가한 source.hwpx가 approved로 등록되면 안 된다."""
    candidate = _make_candidate(tmp_path / "ulsan")
    (candidate / "source.hwpx").write_bytes(b"")
    registry_root = tmp_path / "institutions"

    with pytest.raises(
        TemplateRegistrationError,
        match="not a readable HWPX package",
    ):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert not registry_root.exists()


def test_failed_confirmation_keeps_the_candidate_and_removes_the_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """결함 1의 나머지 절반: 확인 실패 시 후보가 남고 정식 경로가 깨끗해야 한다."""
    candidate = _make_candidate(tmp_path / "ulsan")
    registry_root = tmp_path / "institutions"
    monkeypatch.setattr(
        "core.templates.hwpx_template_registration.TemplateRegistry.find",
        lambda self, institution, document_type: None,
    )

    with pytest.raises(TemplateRegistrationError, match="could not be confirmed"):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert (candidate / "template.json").is_file()
    assert not (registry_root / "울산광역시" / "입법예고").exists()
