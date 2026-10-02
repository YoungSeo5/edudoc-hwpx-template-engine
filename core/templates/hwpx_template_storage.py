from __future__ import annotations

import json
import shutil
from pathlib import Path


_RUNTIME_ROOT_FILES = (
    "template.json",
    "source.hwpx",
    "placeholder_map.json",
)
_OPTIONAL_RUNTIME_ROOT_FILES = (
    "semantic_contract.json",
    "alias_map.json",
    "template_spec.json",
    "family_recipe.json",
    "content.sample.json",
)


class TemplateRegistrationError(ValueError):
    pass


def audit_destination(registry_root: Path, template_id: str) -> Path:
    """Keep approval evidence outside the active package in the external registry."""
    return registry_root / "_audit" / template_id


def require_within_candidate_root(candidate_dir: Path, candidate_root: Path) -> None:
    root = candidate_root.resolve()
    if not root.is_dir():
        raise TemplateRegistrationError(f"candidate root does not exist: {root}")
    try:
        resolved = candidate_dir.resolve(strict=True)
    except OSError as exc:
        raise TemplateRegistrationError(
            f"candidate directory not found: {candidate_dir} ({exc})"
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError:
        raise TemplateRegistrationError(
            f"candidate directory must be inside the candidate root {root}, got {resolved}"
        ) from None


def reject_template_id_conflict(registry_root: Path, template_id: str) -> None:
    for path in sorted(registry_root.glob("*/*/template.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = data.get("status")
            declared = (data.get("identity") or {}).get("template_id")
        except (OSError, ValueError, AttributeError) as exc:
            raise TemplateRegistrationError(
                "cannot read an existing template while checking for a "
                f"template_id conflict: {path} ({exc})"
            ) from exc
        if status == "approved" and declared == template_id:
            raise TemplateRegistrationError(
                f"template_id {template_id!r} is already registered at {path.parent}"
            )


def copy_registration_artifacts(
    source: Path,
    approved: Path,
    audit: Path,
) -> None:
    runtime = _runtime_artifacts(source)
    for relative in runtime:
        _copy(source / relative, approved / relative)
    for artifact in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = artifact.relative_to(source)
        if relative not in runtime:
            _copy(artifact, audit / relative)


def write_approved_status(template_json: Path) -> None:
    data = json.loads(template_json.read_text(encoding="utf-8"))
    data["status"] = "approved"
    template_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _runtime_artifacts(source: Path) -> frozenset[Path]:
    artifacts = {Path(name) for name in _RUNTIME_ROOT_FILES}
    artifacts.update(
        Path(name)
        for name in _OPTIONAL_RUNTIME_ROOT_FILES
        if (source / name).is_file()
    )
    artifacts.update(
        path.relative_to(source)
        for path in (source / "template").glob("section*.template.xml")
    )
    header = Path("template/header.xml")
    if (source / header).is_file():
        artifacts.add(header)
    return frozenset(artifacts)


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
