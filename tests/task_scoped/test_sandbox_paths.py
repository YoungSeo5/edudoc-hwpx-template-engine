"""core.sandbox_paths: repository-local QA temp root, no OS temp fallback.

AGENTS.md requires pytest/QA temp artifacts to live under `sandbox/` only and
to stop rather than silently pick another location when that path is missing
or unusable. Before this, `_validate_legacy_candidate_renders()`
(hwpx_template_registration.py) and `render_one_page_with_page_fit()`
(hwpx_page_fit.py) both called `tempfile.TemporaryDirectory()` with no `dir=`,
which creates its directory on the OS temp volume instead.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import sandbox_paths


def test_require_sandbox_temp_root_returns_the_repository_sandbox_directory() -> None:
    root = sandbox_paths.require_sandbox_temp_root()

    assert root == sandbox_paths.ROOT / "sandbox"
    assert root.is_dir()


def test_require_sandbox_temp_root_fails_closed_when_sandbox_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No OS-temp or other alternative path is ever chosen instead — a missing
    # sandbox/ is a hard stop, not a silent fallback.
    monkeypatch.setattr(sandbox_paths, "ROOT", tmp_path)

    with pytest.raises(sandbox_paths.SandboxUnavailableError, match="sandbox/"):
        sandbox_paths.require_sandbox_temp_root()
