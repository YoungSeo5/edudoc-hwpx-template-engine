from __future__ import annotations

import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.adapters.hwpx_table_fill_adapter import (
    HwpxTableCellFill,
    fill_hwpx_table_cells,
)


HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"\n'
    '         xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">\n'
    '  <hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>\n'
    "</hh:head>\n"
)

CONTENT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf">\n'
    "  <opf:manifest>\n"
    '    <opf:item id="header" href="Contents/header.xml" media-type="text/xml"/>\n'
    '    <opf:item id="section0" href="Contents/section0.xml" media-type="text/xml"/>\n'
    "  </opf:manifest>\n"
    "  <opf:spine><opf:itemref idref=\"section0\"/></opf:spine>\n"
    "</opf:package>\n"
)

SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"\n'
    '        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">\n'
    '  <hp:p id="1" paraPrIDRef="0" styleIDRef="0">\n'
    '    <hp:run charPrIDRef="0">\n'
    '      <hp:tbl rowCnt="2" colCnt="2" borderFillIDRef="1">\n'
    "        <hp:tr>\n"
    '          <hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList><hp:p id="2"><hp:run charPrIDRef="0"><hp:t>항목</hp:t></hp:run></hp:p></hp:subList></hp:tc>\n'
    '          <hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/><hp:subList><hp:p id="3"><hp:run charPrIDRef="0"><hp:t>값</hp:t></hp:run></hp:p></hp:subList></hp:tc>\n'
    "        </hp:tr>\n"
    "        <hp:tr>\n"
    '          <hp:tc><hp:cellAddr rowAddr="1" colAddr="0"/><hp:subList><hp:p id="4"><hp:run charPrIDRef="0"><hp:t>제목</hp:t></hp:run></hp:p></hp:subList></hp:tc>\n'
    '          <hp:tc><hp:cellAddr rowAddr="1" colAddr="1"/><hp:subList><hp:p id="5"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList></hp:tc>\n'
    "        </hp:tr>\n"
    "      </hp:tbl>\n"
    "    </hp:run>\n"
    "  </hp:p>\n"
    "</hs:sec>\n"
)


def _write_hwpx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/section0.xml", SECTION)


def _section_text(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        return package.read("Contents/section0.xml").decode("utf-8")


def test_fill_hwpx_table_cells_uses_hwp_skill_cells_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "filled.hwpx"
        _write_hwpx(source)

        result = fill_hwpx_table_cells(
            source,
            output,
            [
                HwpxTableCellFill(table=0, row=1, col=1, value="데이터기반행정 업무보고"),
                {"table": 0, "row": 0, "col": 1, "value": "작성값", "section": 0},
            ],
        )

        assert result.ok, result.error
        assert output.exists()
        assert result.report["ok"] is True
        assert result.report["cell_errors"] == []
        assert result.report["modified_entries"] == ["Contents/section0.xml"]
        section = _section_text(output)
        assert "데이터기반행정 업무보고" in section
        assert "작성값" in section
        assert re.search(r"<hp:t>값</hp:t>", section) is None


def test_fill_hwpx_table_cells_reports_bad_coordinates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "filled.hwpx"
        _write_hwpx(source)

        result = fill_hwpx_table_cells(
            source,
            output,
            [HwpxTableCellFill(table=0, row=9, col=1, value="실패")],
        )

        assert result.ok is False
        assert result.report["cell_errors"]
        assert "cell_errors" in (result.error or "")


if __name__ == "__main__":
    test_fill_hwpx_table_cells_uses_hwp_skill_cells_contract()
    test_fill_hwpx_table_cells_reports_bad_coordinates()
    print("PASS: HWPX table fill adapter")
