"""Read a source content file into normalized Markdown text.

Feeds ``core.adapters.hwpx_source_content_mapper``. Three source formats are
supported, each reduced to the same Markdown text so the mapper never needs to
know where the text came from:

- ``.md`` / ``.markdown`` — read as UTF-8 text.
- ``.txt`` — read as UTF-8 text (no Markdown syntax expected; the mapper's
  heading/body-marker detection degrades gracefully on plain text).
- ``.hwpx`` — converted with ``python-hwpx``'s
  ``hwpx.tools.markdown_export.export_markdown`` (the same rich HWPX → Markdown
  logic python-hwpx ships).

Any other suffix is refused rather than guessed.
"""
from __future__ import annotations

from pathlib import Path

from .hwpx_template_input import HwpxTemplateInputError

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_HWPX_SUFFIX = ".hwpx"


def read_source_as_markdown(source_path: Path | str) -> str:
    """Read ``source_path`` and return its content as Markdown text.

    Raises ``HwpxTemplateInputError`` if the file is missing or its suffix is
    not one of the supported source formats.
    """
    path = Path(source_path)
    if not path.is_file():
        raise HwpxTemplateInputError(f"source file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8")
    if suffix == _HWPX_SUFFIX:
        return _read_hwpx_as_markdown(path)
    raise HwpxTemplateInputError(
        f"unsupported source file type {suffix!r}: {path}; "
        f"expected one of {sorted(_TEXT_SUFFIXES | {_HWPX_SUFFIX})}"
    )


def _read_hwpx_as_markdown(path: Path) -> str:
    try:
        from hwpx.tools.markdown_export import export_markdown
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise HwpxTemplateInputError(
            "reading a .hwpx source requires python-hwpx "
            "(pip install python-hwpx)"
        ) from exc
    return export_markdown(path)
