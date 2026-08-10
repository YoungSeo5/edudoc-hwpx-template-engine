"""HWPX template extraction preserves assets and reports structure safely."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.templates.hwpx_package_extractor import extract_hwpx_template

HEADER = b"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="urn:hh">
  <hh:fontface lang="HANGUL"><hh:font id="1" face="TestFont"/></hh:fontface>
  <hh:charPr id="0" height="1150"><hh:fontRef hangul="1"/></hh:charPr>
  <hh:paraPr id="0"><hh:lineSpacing type="PERCENT" value="160"/></hh:paraPr>
  <hh:borderFill id="1"/>
  <hh:style id="0"/>
</hh:head>
"""

SECTION = """<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="urn:hs" xmlns:hp="urn:hp">
  <hp:margin top="5669" bottom="5669" left="5669" right="5669"/>
  <hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>현안보고</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>2026. 7. 15.</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>추진 배경</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>담당자: 홍길동 062-123-4567</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 확인 항목 ○○○</hp:t></hp:run></hp:p>
  <hp:tbl rowCnt="2" colCnt="3" borderFillIDRef="1">
    <hp:tr><hp:tc><hp:p><hp:run charPrIDRef="0"><hp:t>표 내용</hp:t></hp:run></hp:p></hp:tc></hp:tr>
  </hp:tbl>
  <hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray>
</hs:sec>
""".encode("utf-8")

CONTENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<opf:package xmlns:opf="urn:opf">
  <opf:manifest>
    <opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>
    <opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine><opf:itemref idref="header"/><opf:itemref idref="section0"/></opf:spine>
</opf:package>
"""


def _write_hwpx(path: Path, *, malicious: bool = False) -> None:
    with ZipFile(path, "w", ZIP_STORED) as package:
        package.writestr("mimetype", "application/hwp+zip")
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/section0.xml", SECTION)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("settings.xml", b"<settings/>")
        package.writestr("Scripts/main.js", b"// exact script bytes")
        package.writestr("META-INF/manifest.xml", b"<manifest/>")
        package.writestr("BinData/image1.png", b"\x89PNG\r\n")
        package.writestr("Preview/PrvText.txt", "unselected preview")
        if malicious:
            package.writestr("../outside.txt", "must never be written")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extracts_exact_assets_and_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        _write_hwpx(source)
        source_hash = _sha256(source)

        fixtures = root / "fixtures" / "Contents"
        fixtures.mkdir(parents=True)
        (fixtures / "header.xml").write_bytes(HEADER)
        (fixtures / "content.hpf").write_bytes(CONTENT)
        (fixtures / "section0.xml").write_bytes(b"different fixture")

        output = root / "template-output"
        result = extract_hwpx_template(
            source,
            output,
            template_id="test_report",
            template_name="테스트 보고서",
            institution="테스트기관",
            fixture_dir=fixtures,
        )

        assert _sha256(source) == source_hash
        assert (output / "raw" / "header.xml").read_bytes() == HEADER
        assert (output / "raw" / "section0.xml").read_bytes() == SECTION
        assert (output / "template" / "header.xml").read_bytes() == HEADER
        assert (output / "template" / "section0.template.xml").read_bytes() == SECTION
        assert (output / "raw" / "Scripts" / "main.js").read_bytes() == b"// exact script bytes"
        assert (output / "raw" / "BinData" / "image1.png").is_file()

        data = json.loads(result.template_json.read_text(encoding="utf-8"))
        assert data["template_id"] == "test_report"
        assert data["format"] == "hwpx"
        assert data["status"] == "candidate"
        assert data["rendering_rules"]["preserve_header_xml"] is True
        assert data["rendering_rules"]["replace_only_hp_t_text"] is True
        assert data["rendering_rules"]["preserve_linesegarray"] is False
        section = data["structure"]["sections"][0]
        assert section["paragraph_count"] == 6
        assert section["table_count"] == 1
        assert section["tables"] == [{"row_count": 2, "column_count": 3}]
        assert "추진 배경" in section["visible_text"]
        categories = {
            item["category"] for item in data["structure"]["candidate_placeholders"]
        }
        assert {
            "date",
            "phone_number",
            "report_title",
            "person_name",
            "placeholder_symbol",
            "checkbox",
            "common_report_section",
        }.issubset(categories)
        comparisons = data["package_summary"]["fixture_comparison"]
        assert any(item["file"] == "header.xml" and item["matches"] for item in comparisons)
        assert any(
            item["file"] == "section0.xml" and item["matches"] is False
            for item in comparisons
        )

        report = result.extraction_report.read_text(encoding="utf-8")
        assert "Visible `<hp:t>` Text" in report
        assert "추진 배경" in report
        assert "rowCnt=`2`, colCnt=`3`" in report
        assert "Candidate Placeholders (Not Applied)" in report
        assert "- Source/template XML keeps extracted `linesegarray` caches." in report
        assert (
            "- Rendering removes `linesegarray` caches from changed sections and "
            "retains them in unchanged sections."
        ) in report


def test_rejects_zip_path_escape_and_cleans_partial_output() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "malicious.hwpx"
        output = root / "output"
        _write_hwpx(source, malicious=True)
        try:
            extract_hwpx_template(
                source,
                output,
                template_id="malicious",
            )
        except ValueError as exc:
            assert "unsafe HWPX archive member" in str(exc)
        else:
            raise AssertionError("unsafe archive member was not rejected")
        assert not output.exists()
        assert not (root / "outside.txt").exists()


if __name__ == "__main__":
    test_extracts_exact_assets_and_analysis()
    test_rejects_zip_path_escape_and_cleans_partial_output()
    print("PASS: HWPX template extraction")
