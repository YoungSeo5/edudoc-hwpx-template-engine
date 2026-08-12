from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.templates import qa_hwpx_template  # noqa: E402


SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:run><hp:t>- 부제 -</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)
HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
    "<hh:beginNum/>"
    "</hh:head>"
)
CONTENT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
    "<opf:manifest>"
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    "</opf:manifest>"
    '<opf:spine><opf:itemref idref="section0"/></opf:spine>'
    "</opf:package>"
)


def _source_hwpx(tmp_path: Path) -> Path:
    source = tmp_path / "marker.hwpx"
    with zipfile.ZipFile(source, "w") as package:
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/section0.xml", SECTION)
    return source


def test_cli_reports_semantic_ambiguity_and_persists_qa_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "candidate"

    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(_source_hwpx(tmp_path)),
            "--output-dir",
            str(output_dir),
            "--institution",
            "demo",
            "--document-type",
            "marker",
            "--template-id",
            "marker_ambiguous_cli",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert summary["ok"] is False
    assert summary["error_code"] == "semantic_ambiguity"
    assert summary["unresolved_count"] == 1
    assert len(summary["resolution_skeleton"]) == 1

    persisted = json.loads((output_dir / "qa.report.json").read_text(encoding="utf-8"))
    assert persisted == summary
    assert not (output_dir / "placeholder_map.json").exists()
