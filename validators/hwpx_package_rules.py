"""Small deterministic checks for generated HWPX packages.

This module intentionally mirrors only the safe package-level ideas from the
protected HWPX skill references. It does not implement full HWPX layout or AST
validation.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree


REQUIRED_FILES = (
    "mimetype",
    "Contents/content.hpf",
    "Contents/header.xml",
    "Contents/section0.xml",
)

EXPECTED_MIMETYPE = "application/hwp+zip"


@dataclass
class HwpxPackageFinding:
    rule: str
    message: str
    severity: str = "error"


@dataclass
class HwpxPackageReport:
    findings: list[HwpxPackageFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def summary(self) -> str:
        if self.passed and not self.findings:
            return "HWPX package validation: 0 findings (passed)"
        errors = sum(1 for f in self.findings if f.severity == "error")
        warnings = sum(1 for f in self.findings if f.severity == "warning")
        lines = [f"HWPX package validation: errors {errors}, warnings {warnings}"]
        lines.extend(
            f"  - [{f.severity}] {f.rule}: {f.message}"
            for f in self.findings
        )
        return "\n".join(lines)


def validate(path: Path | str) -> HwpxPackageReport:
    """Validate minimal HWPX package structure and XML well-formedness."""
    hwpx_path = Path(path)
    report = HwpxPackageReport()

    if not hwpx_path.exists():
        report.findings.append(HwpxPackageFinding(
            "file_exists",
            f"HWPX file does not exist: {hwpx_path}",
        ))
        return report

    try:
        with zipfile.ZipFile(hwpx_path) as zf:
            names = zf.namelist()
            _check_required_files(report, names)
            _check_mimetype(report, zf, names)
            _check_xml_well_formed(report, zf, names)
    except zipfile.BadZipFile:
        report.findings.append(HwpxPackageFinding(
            "zip_container",
            f"Not a valid ZIP archive: {hwpx_path}",
        ))

    return report


def _check_required_files(report: HwpxPackageReport, names: list[str]) -> None:
    for required in REQUIRED_FILES:
        if required not in names:
            report.findings.append(HwpxPackageFinding(
                "required_file",
                f"Missing required file: {required}",
            ))


def _check_mimetype(
    report: HwpxPackageReport,
    zf: zipfile.ZipFile,
    names: list[str],
) -> None:
    if "mimetype" not in names:
        return

    content = zf.read("mimetype").decode("utf-8", "replace").strip()
    if content != EXPECTED_MIMETYPE:
        report.findings.append(HwpxPackageFinding(
            "mimetype_content",
            f"Invalid mimetype: {content}",
        ))

    if names and names[0] != "mimetype":
        report.findings.append(HwpxPackageFinding(
            "mimetype_first",
            "mimetype must be the first ZIP entry",
        ))

    info = zf.getinfo("mimetype")
    if info.compress_type != zipfile.ZIP_STORED:
        report.findings.append(HwpxPackageFinding(
            "mimetype_storage",
            "mimetype must be stored without compression",
        ))


def _check_xml_well_formed(
    report: HwpxPackageReport,
    zf: zipfile.ZipFile,
    names: list[str],
) -> None:
    for name in names:
        if not (name.endswith(".xml") or name.endswith(".hpf")):
            continue
        try:
            ElementTree.fromstring(zf.read(name))
        except ElementTree.ParseError as exc:
            report.findings.append(HwpxPackageFinding(
                "xml_well_formed",
                f"Malformed XML in {name}: {exc}",
            ))
