from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapters.hwpx_template_renderer import _table_cell_fills


def _write_non_contiguous_source(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("Contents/section0.xml", "<section0/>")
        package.writestr("Contents/section2.xml", "<section2/>")


def test_table_cell_section_without_index_uses_package_ordinal(
    tmp_path: Path,
) -> None:
    template_dir = tmp_path / "candidate"
    template_dir.mkdir()
    _write_non_contiguous_source(template_dir / "source.hwpx")
    placeholder_map = {
        "fields": [
            {
                "field_id": "table_value_01",
                "replacement_mode": "table_cell",
                "section": "section2.xml",
                "table": 0,
                "row": 0,
                "col": 0,
            }
        ]
    }

    fills, filled, missing = _table_cell_fills(
        template_dir,
        placeholder_map,
        {"table_value_01": "검증값"},
        on_missing="keep",
    )

    assert filled == {"table_value_01"}
    assert not missing
    assert len(fills) == 1
    assert fills[0].section == 1


def test_table_cell_section_index_keeps_the_recorded_ordinal(
    tmp_path: Path,
) -> None:
    template_dir = tmp_path / "candidate"
    template_dir.mkdir()

    fills, _, _ = _table_cell_fills(
        template_dir,
        {
            "fields": [
                {
                    "field_id": "table_value_01",
                    "replacement_mode": "table_cell",
                    "section": "section2.xml",
                    "section_index": 1,
                    "table": 0,
                    "row": 0,
                    "col": 0,
                }
            ]
        },
        {"table_value_01": "검증값"},
        on_missing="keep",
    )

    assert fills[0].section == 1
