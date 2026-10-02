"""Register an explicitly approved HWPX template candidate into the registry path."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .registry import TemplateRegistry
from .serialization import load_candidate
from .hwpx_template_storage import (
    TemplateRegistrationError,
    audit_destination,
    copy_registration_artifacts,
    reject_template_id_conflict,
    require_within_candidate_root,
    write_approved_status,
)
from ..adapters.hwpx_semantic_contract import (
    bind_semantic_contract,
    load_semantic_contract,
    validate_candidate_field_identity,
)
from ..adapters.hwpx_template_authoring import load_template_spec
from ..adapters.hwpx_template_input import prepare_hwpx_template_input
from ..adapters.hwpx_template_input import HwpxTemplateInputError
from ..adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    render_candidate_roundtrip,
)

# 이 모듈의 경계:
# hwpx_content_separator가 남긴 candidate 폴더
# → 필수 파일·패키지·status 검증 → template_id·대상 경로 충돌 확인
# → runtime은 정식 경로, evidence는 audit 경로로 복사 → status를 approved로 변경
# → registry.find로 등록 확인
# → 확인된 뒤에야 후보 원본을 지운다.
# 승인 판단은 호출자(사람)의 approve 인자이며, 이 모듈이 스스로 승인하지 않는다.

REQUIRED_FILES = (
    "template.json",
    "placeholder_map.json",
    "content.sample.json",
    "template.review.md",
    "source.hwpx",
)

CONTRACT_COMPLETE_FILES = (
    "template_request.json",
    "semantic_contract.json",
    "template_spec.json",
    "institution_design.provenance.json",
    "resolved_authoring_contract.json",
    "qa.report.json",
    "human_review.json",
)

EVIDENCE_FILES = frozenset({"qa.report.json", "human_review.json"})

_UNKNOWN = "확인 필요"


@dataclass(frozen=True, slots=True)
class TemplateRegistrationResult:
    institution: str
    document_type: str
    template_id: str
    destination: Path


def register_hwpx_template_candidate(
    candidate_dir: Path | str,
    *,
    registry_root: Path | str,
    approve: bool = False,
) -> TemplateRegistrationResult:
    """Register one candidate from this external registry after explicit approval."""
    # 흐름 1: 승인은 사람의 명시적 의사여야 한다. 코드가 스스로 승격하지 않는다.
    if not approve:
        raise TemplateRegistrationError(
            "registration requires explicit approval (approve=True)"
        )

    root = Path(registry_root)
    source = Path(candidate_dir)
    require_within_candidate_root(source, root / "candidates")
    temporary_root = root / "_tmp"
    identity = _validate_candidate(source, temporary_root)
    institution = identity["institution"]
    document_type = identity["document_type"]
    template_id = identity["template_id"]

    # 흐름 2: 대상 경로와 template_id 충돌을 복사 전에 모두 확인한다.
    approved_root = root / "approved"
    registry = TemplateRegistry(approved_root)
    destination = registry.template_path(institution, document_type).parent
    audit = audit_destination(root, template_id)
    if destination.exists():
        if destination.resolve() == source.resolve():
            raise TemplateRegistrationError(
                f"candidate already occupies its official path: {destination}"
            )
        active = registry.find(institution, document_type)
        if active is None:
            raise TemplateRegistrationError(
                f"destination exists but is not an approved template: {destination}"
            )
    reject_template_id_conflict(approved_root, template_id)
    if audit.exists():
        raise TemplateRegistrationError(f"audit path already exists: {audit}")

    # 흐름 3: 새 runtime/audit 사본을 먼저 staging에 완성한다. 기존 active는 이
    # 시점까지 전혀 건드리지 않는다.
    destination.parent.mkdir(parents=True, exist_ok=True)
    audit.parent.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    staging = _temporary_directory(temporary_root, destination.name, "staging")
    audit_staging = _temporary_directory(temporary_root, audit.name, "staging")
    backup = _temporary_backup_path(temporary_root, destination.name) if destination.exists() else None
    new_active = False
    try:
        copy_registration_artifacts(source, staging, audit_staging)
        write_approved_status(staging / "template.json")
        if backup is not None:
            _move_directory(destination, backup)
        _move_directory(staging, destination)
        new_active = True

        # 흐름 4: canonical path로 이동한 새 revision이 registry에서 실제로
        # 선택되는지 확인한다. 실패하면 이전 active를 즉시 복구한다.
        registered = registry.find(institution, document_type)
        if registered is None or registered.identity.template_id != template_id:
            raise TemplateRegistrationError(
                "registration could not be confirmed by TemplateRegistry; "
                f"the candidate was kept at {source}"
            )
        _move_directory(audit_staging, audit)
    except (OSError, TemplateRegistrationError) as exc:
        try:
            _restore_previous_active(destination, backup, new_active)
        except OSError as rollback_error:
            raise TemplateRegistrationError(
                "registration replacement failed and rollback could not restore "
                f"the previous approved template: {rollback_error}"
            ) from rollback_error
        raise TemplateRegistrationError(f"registration replacement failed: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(audit_staging, ignore_errors=True)

    # 흐름 5: 성공한 swap의 temporary backup과 candidate 원본을 그 순서로
    # 정리한다. audit은 persistent evidence이므로 절대 지우지 않는다.
    if backup is not None:
        shutil.rmtree(backup)
    shutil.rmtree(source)
    return TemplateRegistrationResult(
        institution=institution,
        document_type=document_type,
        template_id=template_id,
        destination=destination,
    )


def _temporary_directory(parent: Path, name: str, purpose: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f".{name}.{purpose}-", dir=parent))


def _temporary_backup_path(temporary_root: Path, name: str) -> Path:
    return temporary_root / f".{name}.backup-{uuid4().hex}"


def _move_directory(source: Path, destination: Path) -> None:
    source.rename(destination)


def _restore_previous_active(
    destination: Path,
    backup: Path | None,
    new_active: bool,
) -> None:
    if new_active and destination.exists():
        shutil.rmtree(destination)
    if backup is not None and backup.exists():
        _move_directory(backup, destination)
def _validate_candidate(source: Path, temporary_root: Path) -> dict[str, str]:
    if not source.is_dir():
        raise TemplateRegistrationError(f"candidate directory not found: {source}")

    missing = [name for name in REQUIRED_FILES if not (source / name).is_file()]
    if not any((source / "raw").glob("section*.xml")):
        missing.append("raw/section*.xml")
    if not any((source / "template").glob("section*.template.xml")):
        missing.append("template/section*.template.xml")
    if missing:
        raise TemplateRegistrationError(
            f"candidate is missing required files: {', '.join(missing)}"
        )

    # source.hwpx는 렌더의 self-contained 기반이므로 실제 패키지여야 한다.
    if not zipfile.is_zipfile(source / "source.hwpx"):
        raise TemplateRegistrationError(
            f"source.hwpx is not a readable HWPX package: {source / 'source.hwpx'}"
        )

    # 등록 뒤 registry가 읽을 수 있는지를 되돌릴 수 없는 단계 전에 확인한다.
    try:
        candidate = load_candidate(source / "template.json")
    except (KeyError, TypeError, ValueError) as exc:
        raise TemplateRegistrationError(
            f"template.json cannot be read as a template candidate: {exc}"
        ) from exc

    if candidate.status != "candidate":
        raise TemplateRegistrationError(
            "only a candidate template.json can be registered, "
            f"got status={candidate.status!r}"
        )

    # semantic 메타데이터가 있는 후보만 확인한다. semantic 메타데이터가 없는
    # legacy 후보는 기존 검증만 적용해 하위 호환을 유지한다.
    semantic_status = candidate.content_separation.get("semantic_status")
    if semantic_status is not None and semantic_status != "resolved":
        raise TemplateRegistrationError(
            "candidate has unresolved semantic ambiguity "
            f"(content_separation.semantic_status={semantic_status!r}); "
            "resolve every AMBIGUOUS decision before registration"
        )

    if (source / "semantic_contract.json").is_file():
        _validate_contract_complete_candidate(source)
    else:
        _validate_legacy_candidate_renders(source, temporary_root)

    values = {}
    for name in ("institution", "document_type", "template_id"):
        value = getattr(candidate.identity, name)
        if not isinstance(value, str) or not value.strip() or value.strip() == _UNKNOWN:
            raise TemplateRegistrationError(
                f"template.json identity.{name} must be a known value, got {value!r}"
            )
        values[name] = value.strip()
    return values


def _validate_legacy_candidate_renders(source: Path, temporary_root: Path) -> None:
    """source-extracted/legacy 후보(semantic_contract.json 없음)도 승인 전에
    자신의 content.sample.json으로 실제 round-trip 렌더가 되는지 확인한다.

    self-authored/contract-complete 후보는 `_validate_contract_complete_candidate`가
    이미 렌더 가능성을 확인하지만, semantic_contract.json이 없는 legacy 경로는
    지금까지 등록 시점에 아무 렌더 가능성도 확인하지 않았다. 이 함수는 legacy
    경로에 Semantic Contract를 요구하지 않고, 후보가 이미 갖고 있는
    content.sample.json만으로 확인한다.

    field가 없는 최소 후보(단위 테스트 스텁 등)는 확인할 렌더 대상이 없으므로
    건너뛴다.
    """
    try:
        sample = json.loads((source / "content.sample.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TemplateRegistrationError(
            f"content.sample.json cannot be read: {exc}"
        ) from exc
    fields = sample.get("fields") if isinstance(sample, dict) else None
    if not isinstance(fields, dict) or not fields:
        return
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary_root) as tmp:
        try:
            result = render_candidate_roundtrip(
                source, fields, Path(tmp) / "registration_renderability_check.hwpx",
                temporary_root=temporary_root,
            )
        except (HwpxTemplateRenderError, OSError, ValueError) as exc:
            raise TemplateRegistrationError(
                f"legacy candidate cannot render its own sample content: {exc}"
            ) from exc
    if result.leftover_placeholders:
        raise TemplateRegistrationError(
            "legacy candidate would leave unresolved placeholders when rendered "
            f"from its own sample content: {result.leftover_placeholders}"
        )


def _validate_contract_complete_candidate(source: Path) -> None:
    if not (source / "human_review.json").is_file():
        raise TemplateRegistrationError(
            "contract-complete candidate has no human visual approval evidence"
        )
    missing = [name for name in CONTRACT_COMPLETE_FILES if not (source / name).is_file()]
    if missing:
        raise TemplateRegistrationError(
            f"contract-complete candidate is missing required files: {', '.join(missing)}"
        )
    try:
        semantic = load_semantic_contract(source / "semantic_contract.json")
        spec = load_template_spec(source / "template_spec.json")
        bind_semantic_contract(semantic, spec)
        validate_candidate_field_identity(semantic, source)
        qa = json.loads((source / "qa.report.json").read_text(encoding="utf-8"))
        review = json.loads((source / "human_review.json").read_text(encoding="utf-8"))
        sample = json.loads((source / "content.sample.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise TemplateRegistrationError(f"cannot validate contract-complete candidate: {exc}") from exc
    if qa.get("ok") is not True:
        raise TemplateRegistrationError("contract-complete candidate has no machine QA PASS evidence")
    candidate_digest = candidate_artifact_digest(source)
    if qa.get("candidate_digest") != candidate_digest:
        raise TemplateRegistrationError(
            "contract-complete candidate machine QA evidence does not match current candidate"
        )
    if review.get("reviewed") is not True or review.get("approved") is not True:
        raise TemplateRegistrationError("contract-complete candidate has no human visual approval evidence")
    if review.get("candidate_digest") != candidate_digest:
        raise TemplateRegistrationError(
            "contract-complete candidate human visual approval evidence does not match current candidate"
        )
    fields = sample.get("fields")
    if not isinstance(fields, dict):
        raise TemplateRegistrationError("content.sample.json requires a fields object")
    try:
        prepare_hwpx_template_input(source, fields)
    except HwpxTemplateInputError as exc:
        raise TemplateRegistrationError(
            f"approved package cannot prepare final rendering: {exc}"
        ) from exc


def candidate_artifact_digest(candidate_dir: Path | str) -> str:
    candidate = Path(candidate_dir)
    digest = sha256()
    for artifact in sorted(path for path in candidate.rglob("*") if path.is_file()):
        relative = artifact.relative_to(candidate).as_posix()
        if relative in EVIDENCE_FILES:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(artifact.read_bytes()).digest())
    return digest.hexdigest()
