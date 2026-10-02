from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Final


PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
BOUNDARIES: Final[tuple[str, ...]] = (
    "provision",
    "self-authored",
    "candidates",
    "approved",
    "_audit",
)


class RegistryConfigError(ValueError):
    pass


def default_config_path() -> Path:
    return Path.home() / ".edudoc-hwpx-template" / "config.json"


def _repository_containing(path: Path) -> Path | None:
    for parent in (path, *path.parents):
        if (parent / ".git").exists() and (parent / "docs" / "product-workflow-contract.md").is_file():
            return parent
    return None


def validate_registry_root(path: Path | str, *, package_root: Path = PACKAGE_ROOT) -> Path:
    selected = Path(path)
    if not selected.is_absolute():
        raise RegistryConfigError("registry_root는 절대 경로여야 합니다")
    resolved = selected.resolve()
    protected = [
        package_root.resolve(),
        Path.home().resolve() / ".agents" / "skills" / "hwpx-institution-template",
        Path.home().resolve() / ".claude" / "skills" / "hwpx-institution-template",
    ]
    repository = _repository_containing(resolved)
    if repository is not None:
        protected.append(repository)
    if any(resolved.is_relative_to(root.resolve()) for root in protected):
        raise RegistryConfigError("registry_root는 저장소 또는 스킬 설치 폴더 밖이어야 합니다")
    return resolved


def resolve_registry_root(
    explicit: Path | str | None = None,
    *,
    config_path: Path | None = None,
    package_root: Path = PACKAGE_ROOT,
) -> Path:
    if explicit is not None:
        return validate_registry_root(explicit, package_root=package_root)
    config = config_path or default_config_path()
    if not config.is_file():
        raise RegistryConfigError("registry 설정이 필요합니다. configure_hwpx_registry.py로 연결하거나 초기화하세요")
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryConfigError(f"registry 설정을 읽을 수 없습니다: {config} ({exc})") from exc
    if not isinstance(data, dict) or set(data) != {"registry_root"} or not isinstance(data["registry_root"], str):
        raise RegistryConfigError("registry 설정은 registry_root 절대 경로 하나만 포함해야 합니다")
    return validate_registry_root(data["registry_root"], package_root=package_root)


def connect_registry(root: Path) -> None:
    if not root.is_dir():
        raise RegistryConfigError(f"기존 registry 폴더가 없습니다: {root}")
    missing = [name for name in BOUNDARIES if not (root / name).is_dir()]
    design = root / "provision" / "edudoc" / "_design" / "design.json"
    families = root / "provision" / "edudoc" / "_families"
    if not design.is_file():
        missing.append(str(design.relative_to(root)))
    if not families.is_dir():
        missing.append(str(families.relative_to(root)))
    if missing:
        raise RegistryConfigError("registry 필수 경계 누락: " + ", ".join(missing))
    resolved_root = root.resolve()
    if any(not (root / name).resolve().is_relative_to(resolved_root) for name in (*BOUNDARIES, "_tmp")):
        raise RegistryConfigError("registry 필수 경계가 registry 밖을 가리킵니다")
    paths = [(root / name).resolve() for name in ("candidates", "approved", "_audit", "_tmp")]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
           for index, a in enumerate(paths) for b in paths[index + 1:]):
        raise RegistryConfigError("registry candidates/approved/_audit/_tmp 경계가 겹칩니다")


def initialize_registry(root: Path, *, provision_source: Path) -> None:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise RegistryConfigError(f"registry 대상 경로가 비어 있지 않습니다: {root}")
    for name in ("_design", "_families"):
        if not (provision_source / name).is_dir():
            raise RegistryConfigError(f"edudoc provision 원본 누락: {provision_source / name}")
    for name in BOUNDARIES:
        (root / name).mkdir(parents=True, exist_ok=True)
    destination = root / "provision" / "edudoc"
    for name in ("_design", "_families"):
        shutil.copytree(provision_source / name, destination / name)


def save_registry_root(
    root: Path | str,
    *,
    config_path: Path | None = None,
    package_root: Path = PACKAGE_ROOT,
) -> Path:
    selected = validate_registry_root(root, package_root=package_root)
    config = config_path or default_config_path()
    config.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="config-", suffix=".tmp",
        dir=config.parent, delete=False,
    ) as temporary:
        temporary.write(json.dumps({"registry_root": str(selected)}, ensure_ascii=False) + "\n")
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, config)
    finally:
        temporary_path.unlink(missing_ok=True)
    return selected
