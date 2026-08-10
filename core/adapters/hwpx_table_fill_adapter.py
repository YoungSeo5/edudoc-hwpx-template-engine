from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from validators.hwpx_package_rules import validate as validate_hwpx_package


DEFAULT_HWP_SKILL_DIR = Path("skills") / "hwp-skill"


class HwpxTableFillAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class HwpxTableCellFill:
    table: int
    row: int
    col: int
    value: str
    section: int = 0

    def to_payload(self) -> dict:
        return {
            "table": self.table,
            "row": self.row,
            "col": self.col,
            "value": self.value,
            "section": self.section,
        }


@dataclass(frozen=True)
class HwpxTableFillResult:
    input_path: Path
    output_path: Path
    ok: bool
    error: str | None = None
    report: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    command: list[str] = field(default_factory=list)

    def to_meta(self) -> dict:
        return {
            "adapter": "hwpx_table_fill_adapter",
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "ok": self.ok,
            "error": self.error,
            "report": dict(self.report),
            "validation": dict(self.validation),
            "command": list(self.command),
        }


def fill_hwpx_table_cells(
    input_path: Path | str,
    output_path: Path | str,
    cells: Iterable[HwpxTableCellFill | dict],
    *,
    skill_dir: Path | str = DEFAULT_HWP_SKILL_DIR,
) -> HwpxTableFillResult:
    source = Path(input_path)
    output = Path(output_path)
    script = Path(skill_dir) / "scripts" / "fill_hwpx.py"
    payload = _normalize_cells(cells)
    _validate_inputs(source, output, script, payload)
    payload, coordinate_errors = _translate_cell_addresses(source, payload)
    if coordinate_errors:
        error = f"cell_errors={coordinate_errors}"
        return HwpxTableFillResult(
            input_path=source,
            output_path=output,
            ok=False,
            error=error,
            report={"ok": False, "cell_errors": coordinate_errors},
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".hwpx-table-fill-", dir=output.parent) as temp:
        temp_dir = Path(temp)
        cells_path = temp_dir / "cells.json"
        report_path = temp_dir / "fill-report.json"
        cells_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cmd = [
            sys.executable,
            str(script),
            "fill",
            str(source),
            str(output),
            "--cells",
            str(cells_path),
            "--report",
            str(report_path),
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except Exception as exc:  # noqa: BLE001
            return HwpxTableFillResult(
                input_path=source,
                output_path=output,
                ok=False,
                error=repr(exc),
                command=cmd,
            )

        report = _load_report(report_path)
        validation_report = validate_hwpx_package(output)
        validation = {
            "passed": validation_report.passed,
            "summary": validation_report.summary(),
        }
        ok = (
            completed.returncode == 0
            and bool(report.get("ok"))
            and not report.get("cell_errors")
            and validation_report.passed
        )
        error = None
        if not ok:
            error = _error_summary(completed, report, validation)
        return HwpxTableFillResult(
            input_path=source,
            output_path=output,
            ok=ok,
            error=error,
            report=report,
            validation=validation,
            command=cmd,
        )


def _normalize_cells(cells: Iterable[HwpxTableCellFill | dict]) -> list[dict]:
    payload: list[dict] = []
    for cell in cells:
        item = cell.to_payload() if isinstance(cell, HwpxTableCellFill) else dict(cell)
        normalized = {
            "table": int(item.get("table", 0)),
            "row": int(item["row"]),
            "col": int(item["col"]),
            "value": str(item["value"]),
            "section": int(item.get("section", 0)),
        }
        payload.append(normalized)
    return payload


def _validate_inputs(
    source: Path,
    output: Path,
    script: Path,
    payload: list[dict],
) -> None:
    if not source.is_file():
        raise HwpxTableFillAdapterError(f"input HWPX does not exist: {source}")
    if source.suffix.lower() != ".hwpx":
        raise HwpxTableFillAdapterError(f"input must be a .hwpx file: {source}")
    if output.suffix.lower() != ".hwpx":
        raise HwpxTableFillAdapterError(f"output must be a .hwpx file: {output}")
    if not script.is_file():
        raise HwpxTableFillAdapterError(f"hwp-skill fill_hwpx.py not found: {script}")
    if not payload:
        raise HwpxTableFillAdapterError("at least one table cell fill is required")
    for index, item in enumerate(payload):
        for key in ("table", "row", "col", "section"):
            if item[key] < 0:
                raise HwpxTableFillAdapterError(
                    f"cells[{index}].{key} must be non-negative"
                )


def _translate_cell_addresses(
    source: Path,
    payload: list[dict],
) -> tuple[list[dict], list[str]]:
    translated = []
    errors = []
    with zipfile.ZipFile(source) as package:
        section_names = sorted(
            (
                name
                for name in package.namelist()
                if re.fullmatch(r"Contents/section\d+\.xml", name, re.IGNORECASE)
            ),
            key=_section_number,
        )
        section_roots = [
            ET.fromstring(package.read(section_name))
            for section_name in section_names
        ]

    for item in payload:
        section_index = item["section"]
        table_index = item["table"]
        row_addr = item["row"]
        col_addr = item["col"]
        location = (
            f"section{section_index}.table{table_index}."
            f"row{row_addr}.col{col_addr}"
        )
        if section_index >= len(section_roots):
            errors.append(
                f"{location}: section index out of range ({len(section_roots)} sections)"
            )
            continue
        tables = _nodes(section_roots[section_index], "tbl")
        if table_index >= len(tables):
            errors.append(
                f"{location}: table index out of range ({len(tables)} tables)"
            )
            continue

        resolved = _cell_position(tables[table_index], row_addr, col_addr)
        if resolved is None:
            errors.append(f"{location}: cellAddr not found")
            continue
        row_position, col_position = resolved
        translated.append(
            {
                **item,
                "row": row_position,
                "col": col_position,
            }
        )
    return translated, errors


def _cell_position(
    table: ET.Element,
    row_addr: int,
    col_addr: int,
) -> tuple[int, int] | None:
    rows = _direct_children(table, "tr")
    for row_position, row in enumerate(rows):
        for col_position, cell in enumerate(_direct_children(row, "tc")):
            address = next(
                (
                    child
                    for child in cell
                    if _local_name(child.tag) == "cellAddr"
                ),
                None,
            )
            if address is None:
                continue
            if (
                _int_attr(address, "rowAddr") == row_addr
                and _int_attr(address, "colAddr") == col_addr
            ):
                return row_position, col_position
    return None


def _direct_children(node: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in node if _local_name(child.tag) == local_name]


def _nodes(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].split(":", 1)[-1]


def _int_attr(node: ET.Element, name: str) -> int | None:
    for key, value in node.attrib.items():
        if _local_name(key) == name:
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _section_number(path: str) -> int:
    match = re.search(r"section(\d+)", path, re.IGNORECASE)
    return int(match.group(1)) if match else 10**9


def _load_report(report_path: Path) -> dict:
    if not report_path.is_file():
        return {"ok": False, "error": "hwp-skill did not write a fill report"}
    return json.loads(report_path.read_text(encoding="utf-8"))


def _error_summary(
    completed: subprocess.CompletedProcess,
    report: dict,
    validation: dict,
) -> str:
    parts: list[str] = []
    if completed.returncode != 0:
        parts.append(f"fill_hwpx.py exited {completed.returncode}")
    if report.get("cell_errors"):
        parts.append(f"cell_errors={report['cell_errors']}")
    if not report.get("ok"):
        parts.append("fill report ok=false")
    if validation and not validation.get("passed"):
        parts.append(validation.get("summary", "HWPX validation failed"))
    detail = (completed.stderr or completed.stdout or "").strip()
    if detail:
        parts.append(detail[:500])
    return "; ".join(parts) if parts else "HWPX table fill failed"


__all__ = [
    "HwpxTableCellFill",
    "HwpxTableFillAdapterError",
    "HwpxTableFillResult",
    "fill_hwpx_table_cells",
]
