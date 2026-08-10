"""Register an explicitly approved HWPX template candidate into the registry path."""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .registry import TemplateRegistry
from .serialization import load_candidate

# 이 모듈의 경계:
# hwpx_content_separator가 남긴 candidate 폴더
# → 필수 파일·패키지·status 검증 → template_id·대상 경로 충돌 확인
# → 정식 경로로 복사 → status를 approved로 변경 → registry.find로 등록 확인
# → 확인된 뒤에야 후보 원본을 지운다.
# 승인 판단은 호출자(사람)의 approve 인자이며, 이 모듈이 스스로 승인하지 않는다.

REQUIRED_FILES = (
    "template.json",
    "placeholder_map.json",
    "content.sample.json",
    "template.review.md",
    "source.hwpx",
)

_UNKNOWN = "확인 필요"


class TemplateRegistrationError(ValueError):
    pass


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
    """Move an approved candidate to its official path and confirm registration."""
    # 흐름 1: 승인은 사람의 명시적 의사여야 한다. 코드가 스스로 승격하지 않는다.
    if not approve:
        raise TemplateRegistrationError(
            "registration requires explicit approval (approve=True)"
        )

    source = Path(candidate_dir)
    identity = _validate_candidate(source)
    institution = identity["institution"]
    document_type = identity["document_type"]
    template_id = identity["template_id"]

    # 흐름 2: 대상 경로와 template_id 충돌을 복사 전에 모두 확인한다.
    registry = TemplateRegistry(registry_root)
    destination = registry.template_path(institution, document_type).parent
    if destination.exists():
        if destination.resolve() == source.resolve():
            raise TemplateRegistrationError(
                f"candidate already occupies its official path: {destination}"
            )
        raise TemplateRegistrationError(
            f"destination path already exists: {destination}"
        )
    _reject_template_id_conflict(Path(registry_root), template_id)

    # 흐름 3: 복사본으로 먼저 등록을 성립시킨다. 확인 전까지 후보 원본은 손대지
    # 않으므로, 어느 단계에서 실패해도 후보는 그대로 남는다.
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    _write_approved_status(destination / "template.json")

    # 흐름 4: 등록 성공은 registry가 실제로 찾을 수 있는지로만 확인한다.
    # 확인에 실패하면 복사본을 지워 정식 경로에 미확인 결과를 남기지 않는다.
    registered = registry.find(institution, document_type)
    if registered is None or registered.identity.template_id != template_id:
        shutil.rmtree(destination, ignore_errors=True)
        raise TemplateRegistrationError(
            "registration could not be confirmed by TemplateRegistry; "
            f"the candidate was kept at {source}"
        )

    # 흐름 5: 등록이 확인된 뒤에야 후보 원본을 지운다.
    shutil.rmtree(source)
    return TemplateRegistrationResult(
        institution=institution,
        document_type=document_type,
        template_id=template_id,
        destination=destination,
    )


def _validate_candidate(source: Path) -> dict[str, str]:
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

    values = {}
    for name in ("institution", "document_type", "template_id"):
        value = getattr(candidate.identity, name)
        if not isinstance(value, str) or not value.strip() or value.strip() == _UNKNOWN:
            raise TemplateRegistrationError(
                f"template.json identity.{name} must be a known value, got {value!r}"
            )
        values[name] = value.strip()
    return values


def _reject_template_id_conflict(registry_root: Path, template_id: str) -> None:
    for path in sorted(registry_root.glob("*/*/template.json")):
        # 읽지 못한 파일이 있으면 충돌 없음을 증명할 수 없으므로,
        # 어느 파일이 문제인지 밝히고 중단한다.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = data.get("status")
            declared = (data.get("identity") or {}).get("template_id")
        except (OSError, ValueError, AttributeError) as exc:
            raise TemplateRegistrationError(
                f"cannot read an existing template while checking for a "
                f"template_id conflict: {path} ({exc})"
            ) from exc
        if status != "approved":
            continue
        if declared == template_id:
            raise TemplateRegistrationError(
                f"template_id {template_id!r} is already registered at {path.parent}"
            )


def _write_approved_status(template_json: Path) -> None:
    data = json.loads(template_json.read_text(encoding="utf-8"))
    data["status"] = "approved"
    template_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
