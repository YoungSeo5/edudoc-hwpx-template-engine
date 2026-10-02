from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import registry_config
from core.templates.registry import TemplateRegistry
from scripts.templates import (
    author_hwpx_template,
    qa_hwpx_template,
    register_hwpx_template,
    render_hwpx_template,
    render_hwpx_template_from_source,
)


WORKFLOWS = [
    (author_hwpx_template.main, ["--template-request", "missing", "--semantic-contract", "missing", "--template-spec", "missing", "--institution-design", "missing", "--institution", "edudoc", "--document-type", "report"]),
    (qa_hwpx_template.main, ["--source", "missing", "--institution", "edudoc", "--document-type", "report"]),
    (register_hwpx_template.main, ["--candidate", "missing", "--approve"]),
    (render_hwpx_template.main, ["--institution", "edudoc", "--document-type", "report", "--content", "missing", "--output", "missing", "--requester-name", "tester"]),
    (render_hwpx_template_from_source.main, ["--institution", "edudoc", "--document-type", "report", "--source", "missing", "--output", "missing", "--requester-name", "tester"]),
]


@pytest.mark.parametrize(("entrypoint", "arguments"), WORKFLOWS)
def test_workflow_cli_requires_registry_before_accessing_inputs(
    entrypoint, arguments: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(registry_config, "default_config_path", lambda: tmp_path / "missing-config.json")

    assert entrypoint(arguments) == 1
    assert "registry" in json.loads(capsys.readouterr().out)["error"]
    assert not (tmp_path / "missing-config.json").exists()


@pytest.mark.parametrize(("entrypoint", "arguments"), WORKFLOWS)
def test_cli_rejects_package_internal_registry_before_creating_candidate(
    entrypoint, arguments: list[str], capsys: pytest.CaptureFixture[str],
) -> None:
    package_root = Path(__file__).resolve().parents[2]
    target = package_root / "sandbox" / "should-not-be-created"

    assert entrypoint([*arguments, "--registry-root", str(target)]) == 1
    assert "저장소 또는 스킬 설치 폴더 밖" in json.loads(capsys.readouterr().out)["error"]
    assert not target.exists()


def test_template_registry_has_no_relative_default() -> None:
    with pytest.raises(TypeError):
        TemplateRegistry()
