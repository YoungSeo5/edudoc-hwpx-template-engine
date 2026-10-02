from __future__ import annotations

import subprocess
import shutil
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from core.registry_config import initialize_registry
from scripts.templates import author_hwpx_template, qa_hwpx_template, render_hwpx_template


@pytest.fixture
def sandbox_qa_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Exercise candidate QA against one explicit sandbox registry."""
    root = tmp_path / "registry"
    provision = Path(__file__).resolve().parents[1] / "templates" / "institutions" / "edudoc"
    initialize_registry(root, provision_source=provision)
    monkeypatch.setattr(qa_hwpx_template, "resolve_registry_root", lambda explicit: root)
    return root


@pytest.fixture
def sandbox_author_registry(sandbox_qa_registry: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Exercise self-authoring and its QA subprocess against one registry."""
    root = sandbox_qa_registry
    monkeypatch.setattr(author_hwpx_template, "resolve_registry_root", lambda explicit: root)

    def in_process_qa(command: list[str]) -> subprocess.CompletedProcess[str]:
        assert Path(command[command.index("--registry-root") + 1]) == root
        output = StringIO()
        with redirect_stdout(output):
            exit_code = qa_hwpx_template.main(command[2:])
        return subprocess.CompletedProcess(command, exit_code, output.getvalue(), "")

    monkeypatch.setattr(author_hwpx_template, "run_skill_subprocess", in_process_qa)
    return root


@pytest.fixture
def sandbox_render_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep legacy Financial Supervisory Service packages as test-only copies."""
    root = tmp_path / "registry"
    package = Path(__file__).resolve().parents[1]
    initialize_registry(root, provision_source=package / "templates" / "institutions" / "edudoc")
    shutil.copytree(
        package / "templates" / "institutions" / "금융감독원",
        root / "approved" / "금융감독원",
    )
    monkeypatch.setattr(render_hwpx_template, "resolve_registry_root", lambda explicit: root)
    return root
