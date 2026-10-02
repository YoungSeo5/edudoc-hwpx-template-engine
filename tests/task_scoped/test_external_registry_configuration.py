from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.registry_config import (
    RegistryConfigError,
    connect_registry,
    initialize_registry,
    resolve_registry_root,
    save_registry_root,
    validate_registry_root,
)
from scripts.templates import configure_hwpx_registry


ROOT = Path(__file__).resolve().parents[2]
PROVISION = ROOT / "templates" / "institutions" / "edudoc"
BOUNDARIES = ("provision", "self-authored", "candidates", "approved", "_audit")


def _empty_registry(path: Path) -> Path:
    for name in BOUNDARIES:
        (path / name).mkdir(parents=True)
    return path


def _manifest(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.rglob("*")
        if item.is_file()
    }


def test_missing_configuration_fails_without_fallback(tmp_path: Path) -> None:
    with pytest.raises(RegistryConfigError, match="registry 설정이 필요"):
        resolve_registry_root(config_path=tmp_path / "missing.json", package_root=ROOT)


def test_external_absolute_path_is_accepted() -> None:
    external = Path.home() / "edudoc-external-registry-validate-only"
    assert validate_registry_root(external, package_root=ROOT) == external.resolve()


@pytest.mark.parametrize("path", [Path("relative-registry"), ROOT / "sandbox" / "registry"])
def test_relative_or_repository_path_is_rejected(path: Path) -> None:
    with pytest.raises(RegistryConfigError):
        validate_registry_root(path, package_root=ROOT)


def test_installed_skill_path_is_rejected() -> None:
    installed = Path.home() / ".agents" / "skills" / "hwpx-institution-template" / "data"
    with pytest.raises(RegistryConfigError):
        validate_registry_root(installed, package_root=ROOT)


@pytest.mark.parametrize(
    ("running", "other"),
    [
        (".agents", ".claude"),
        (".claude", ".agents"),
    ],
)
def test_other_installed_skill_path_is_rejected(running: str, other: str) -> None:
    running_root = Path.home() / running / "skills" / "hwpx-institution-template"
    other_root = Path.home() / other / "skills" / "hwpx-institution-template"
    with pytest.raises(RegistryConfigError):
        validate_registry_root(other_root / "data", package_root=running_root)


def test_source_repository_is_rejected_even_when_package_root_is_installed() -> None:
    installed = Path.home() / ".agents" / "skills" / "hwpx-institution-template"
    with pytest.raises(RegistryConfigError):
        validate_registry_root(ROOT / "sandbox" / "registry", package_root=installed)


def test_explicit_registry_precedes_saved_configuration(tmp_path: Path) -> None:
    configured = Path.home() / "configured-edudoc-registry"
    explicit = Path.home() / "explicit-edudoc-registry"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"registry_root": str(configured)}), encoding="utf-8")

    assert resolve_registry_root(explicit, config_path=config, package_root=ROOT) == explicit.resolve()


def test_saved_repository_path_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"registry_root": str(ROOT / "sandbox")}), encoding="utf-8")
    with pytest.raises(RegistryConfigError):
        resolve_registry_root(config_path=config, package_root=ROOT)


def test_connect_existing_registry_does_not_change_files(tmp_path: Path) -> None:
    registry = _empty_registry(tmp_path / "registry")
    design = registry / "provision" / "edudoc" / "_design" / "design.json"
    design.parent.mkdir(parents=True)
    design.write_text("{}", encoding="utf-8")
    (registry / "provision" / "edudoc" / "_families").mkdir()
    marker = registry / "approved" / "existing.json"
    marker.write_text("existing", encoding="utf-8")
    before = _manifest(registry)

    connect_registry(registry)

    assert _manifest(registry) == before
    assert marker.read_text(encoding="utf-8") == "existing"


def test_connect_rejects_overlapping_mutable_boundaries(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    initialize_registry(registry, provision_source=PROVISION)
    (registry / "approved").rmdir()
    try:
        (registry / "approved").symlink_to(registry / "candidates", target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(RegistryConfigError, match="경계가 겹칩니다"):
        connect_registry(registry)


def test_connect_rejects_resolved_boundary_overlap_without_symlink_privilege(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "registry"
    initialize_registry(registry, provision_source=PROVISION)
    resolve = Path.resolve

    def overlapping_resolve(path: Path, *args, **kwargs) -> Path:
        if path == registry / "approved":
            return registry / "candidates"
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", overlapping_resolve)
    with pytest.raises(RegistryConfigError, match="경계가 겹칩니다"):
        connect_registry(registry)


def test_connect_rejects_boundary_escaping_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "registry"
    initialize_registry(registry, provision_source=PROVISION)
    resolve = Path.resolve

    def escaped_resolve(path: Path, *args, **kwargs) -> Path:
        if path == registry / "approved":
            return tmp_path / "outside"
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escaped_resolve)
    with pytest.raises(RegistryConfigError, match="registry 밖"):
        connect_registry(registry)


def test_connect_rejects_missing_edudoc_provision_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _empty_registry(tmp_path / "registry")
    marker = registry / "approved" / "existing.json"
    marker.write_text("existing", encoding="utf-8")
    before = _manifest(registry)
    config = tmp_path / "config.json"
    from core import registry_config

    monkeypatch.setattr(registry_config, "_repository_containing", lambda _path: None)

    result = configure_hwpx_registry.main(
        ["connect", "--registry-root", str(registry)],
        config_path=config,
        package_root=tmp_path / "separate-package",
    )

    assert result == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert "provision/edudoc/_design/design.json" in error.replace("\\", "/")
    assert "provision/edudoc/_families" in error.replace("\\", "/")
    assert _manifest(registry) == before
    assert not config.exists()


@pytest.mark.parametrize("missing", ["design", "families"])
def test_connect_rejects_each_missing_provision_part(tmp_path: Path, missing: str) -> None:
    registry = _empty_registry(tmp_path / "registry")
    design = registry / "provision" / "edudoc" / "_design" / "design.json"
    families = registry / "provision" / "edudoc" / "_families"
    if missing != "design":
        design.parent.mkdir(parents=True)
        design.write_text("{}", encoding="utf-8")
    if missing != "families":
        families.mkdir(parents=True)

    with pytest.raises(RegistryConfigError, match=missing):
        connect_registry(registry)


def test_connect_reports_missing_boundaries(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    registry.mkdir()
    with pytest.raises(RegistryConfigError, match="provision.*self-authored.*candidates.*approved.*_audit"):
        connect_registry(registry)
    assert list(registry.iterdir()) == []


def test_initialize_copies_only_edudoc_provision(tmp_path: Path) -> None:
    registry = tmp_path / "registry"

    initialize_registry(registry, provision_source=PROVISION)

    assert all((registry / name).is_dir() for name in BOUNDARIES)
    assert not (registry / "_tmp").exists()
    assert _manifest(registry / "provision" / "edudoc") == {
        **{f"_design/{key}": value for key, value in _manifest(PROVISION / "_design").items()},
        **{f"_families/{key}": value for key, value in _manifest(PROVISION / "_families").items()},
    }
    assert not (registry / "provision" / "금융감독원").exists()


def test_initialize_rejects_nonempty_target(tmp_path: Path) -> None:
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RegistryConfigError, match="비어 있지"):
        initialize_registry(registry, provision_source=PROVISION)
    assert (registry / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_save_replaces_config_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"registry_root": "old"}', encoding="utf-8")
    external = Path.home() / "edudoc-atomic-registry"
    from core import registry_config

    real_replace = registry_config.os.replace
    calls: list[tuple[Path, Path]] = []

    def record_replace(source: str | Path, destination: str | Path) -> None:
        calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(registry_config.os, "replace", record_replace)
    save_registry_root(external, config_path=config, package_root=ROOT)

    assert json.loads(config.read_text(encoding="utf-8")) == {"registry_root": str(external.resolve())}
    assert len(calls) == 1
    assert calls[0][0].parent == calls[0][1].parent == config.parent
    assert list(config.parent.glob("*.tmp")) == []


def test_failed_replace_preserves_previous_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.json"
    original = '{"registry_root": "old"}'
    config.write_text(original, encoding="utf-8")
    from core import registry_config

    def fail_replace(_source: str | Path, _destination: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(registry_config.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        save_registry_root(Path.home() / "new-edudoc-registry", config_path=config, package_root=ROOT)
    assert config.read_text(encoding="utf-8") == original
    assert list(config.parent.glob("*.tmp")) == []


def test_cli_rejects_repository_sandbox_without_writing_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.json"
    result = configure_hwpx_registry.main(
        ["connect", "--registry-root", str(ROOT / "sandbox" / "registry")],
        config_path=config,
    )
    assert result == 1
    assert "registry" in capsys.readouterr().out
    assert not config.exists()


def test_cli_show_reports_missing_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = configure_hwpx_registry.main(["show"], config_path=tmp_path / "missing.json")
    assert result == 1
    assert "registry 설정이 필요" in capsys.readouterr().out
