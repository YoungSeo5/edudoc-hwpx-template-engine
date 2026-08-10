"""Deterministic plain-text access to a legacy .hwp binary (via pyhwp).

``extract_style`` / ``extract_structure`` only support HWPX (a zip of XML). A
legacy .hwp is an OLE binary, so those return unknown. We can still read the
document's plain text deterministically with pyhwp and observe what the text
itself states.

Any font/size wording found in the text is returned as *reference-text evidence*
only — it is the document describing itself, NOT a parsed style record. It must
never be written into a parsed ``style_profile``.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# runs pyhwp's hwp5txt in a child process so its stdout is captured cleanly
_HWP5TXT = "import sys; sys.argv=['hwp5txt', sys.argv[1]]; from hwp5.hwp5txt import main; main()"

_FONT_HINT = re.compile(r"(휴먼명조|헤드라인M|중고딕|신명조|맑은\s*고딕|굴림|바탕|돋움|명조|고딕)")
_SIZE_HINT = re.compile(r"\d+\s*p(t)?\b")


def hwp_to_text(path: Path | str) -> str | None:
    """Return the .hwp plain text via pyhwp, or None if it cannot be read."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _HWP5TXT, str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except Exception:  # noqa: BLE001 - pyhwp missing / unreadable binary
        return None
    text = result.stdout or ""
    return text if text.strip() else None


def style_mentions_in_text(text: str) -> list[str]:
    """Lines where the reference text itself names a font or point size.

    Evidence only — these are the document's textual descriptions, not parsed
    style values. Never promote these into style_profile.
    """
    mentions: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and (_FONT_HINT.search(stripped) or _SIZE_HINT.search(stripped)):
            mentions.append(stripped)
    return mentions
