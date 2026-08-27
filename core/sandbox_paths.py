"""Repository-local root for QA/registration temp artifacts.

AGENTS.md requires pytest and QA temp output to live under ``sandbox/`` only,
and to stop rather than silently pick another location when that path is
missing or unusable. ``tempfile.TemporaryDirectory()`` with no ``dir=``
argument creates its directory under the OS temp volume instead, which is
exactly the fallback this module exists to refuse.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SandboxUnavailableError(RuntimeError):
    pass


def require_sandbox_temp_root() -> Path:
    """Return ``<repo root>/sandbox``; raise rather than fall back if it is missing.

    Pass the result as ``tempfile.TemporaryDirectory(dir=...)`` so QA-time
    artifacts land inside the repository's own gitignored scratch space
    instead of the OS temp volume.
    """
    root = ROOT / "sandbox"
    if not root.is_dir():
        raise SandboxUnavailableError(
            f"sandbox/ is required for QA temp artifacts and does not exist: {root}"
        )
    return root
