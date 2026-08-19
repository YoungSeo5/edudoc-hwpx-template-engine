"""Runtime-discovered Hancom Automation page-count validation."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

if os.name == "nt":
    import winreg


_PROG_ID = "HWPFrame.HwpObject"
_MODULE_REGISTRY_PATH = r"Software\HNC\HwpAutomation\Modules"


@dataclass(frozen=True, slots=True)
class HancomAutomationDiscovery:
    hancom_automation: Literal["available", "missing"]
    security_module: Literal["available", "missing"]
    native_page_validation: Literal["available", "unavailable"]
    security_module_name: str | None


@dataclass(frozen=True, slots=True)
class NativePageValidation:
    passed: bool
    expected_pages: int
    observed_pages: int | None
    reason: str | None
    discovery: HancomAutomationDiscovery
    register_module_result: bool | None
    open_succeeded: bool

@dataclass(frozen=True, slots=True)
class _NativePageReadResult:
    register_module_result: bool | None
    open_succeeded: bool
    observed_pages: int | None
    reason: str | None

def discover_hancom_automation() -> HancomAutomationDiscovery:
    """Discover COM and one locally registered file-access approval module."""
    if not _automation_available():
        return HancomAutomationDiscovery("missing", "missing", "unavailable", None)
    modules = _registered_security_modules()
    if not modules:
        return HancomAutomationDiscovery("available", "missing", "unavailable", None)
    return HancomAutomationDiscovery("available", "available", "available", modules[0])


def validate_native_page_count(source: Path, expected_pages: int) -> NativePageValidation:
    """Open an HWPX through COM and compare its native layout page count."""
    discovery = discover_hancom_automation()

    if discovery.native_page_validation == "unavailable":
        return NativePageValidation(
            passed=False,
            expected_pages=expected_pages,
            observed_pages=None,
            reason="native_page_validation_unavailable",
            discovery=discovery,
            register_module_result=None,
            open_succeeded=False,
        )

    if not source.is_file():
        return NativePageValidation(
            passed=False,
            expected_pages=expected_pages,
            observed_pages=None,
            reason="native_page_source_missing",
            discovery=discovery,
            register_module_result=None,
            open_succeeded=False,
        )

    read_result = _read_page_count(
        source,
        discovery.security_module_name,
    )

    if read_result.observed_pages is None:
        return NativePageValidation(
            passed=False,
            expected_pages=expected_pages,
            observed_pages=None,
            reason=read_result.reason,
            discovery=discovery,
            register_module_result=read_result.register_module_result,
            open_succeeded=read_result.open_succeeded,
        )

    return NativePageValidation(
        passed=read_result.observed_pages == expected_pages,
        expected_pages=expected_pages,
        observed_pages=read_result.observed_pages,
        reason=None,
        discovery=discovery,
        register_module_result=read_result.register_module_result,
        open_succeeded=read_result.open_succeeded,
    )

def _automation_available() -> bool:
    if os.name != "nt":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{_PROG_ID}\\CLSID"):
            return True
    except OSError:
        return False


def _registered_security_modules() -> tuple[str, ...]:
    if os.name != "nt":
        return ()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _MODULE_REGISTRY_PATH) as key:
            modules: list[str] = []
            index = 0
            while True:
                try:
                    name, dll_path, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                if isinstance(dll_path, str) and name and Path(dll_path).is_file():
                    modules.append(name)
                index += 1
            return tuple(sorted(modules))
    except OSError:
        return ()


def _read_page_count(
    source: Path,
    security_module_name: str | None,
) -> _NativePageReadResult:
    if security_module_name is None:
        return _NativePageReadResult(
            register_module_result=None,
            open_succeeded=False,
            observed_pages=None,
            reason="security_module_unavailable",
        )

    payload = base64.b64encode(
        json.dumps(
            {
                "path": str(source),
                "security_module_name": security_module_name,
            }
        ).encode("utf-8")
    ).decode("ascii")

    script = """
$payload = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($env:EDUDOC_HANCOM_PAYLOAD)
) | ConvertFrom-Json
$hwp = New-Object -ComObject 'HWPFrame.HwpObject'
try {
  if (-not $hwp.RegisterModule('FilePathCheckDLL', $payload.security_module_name)) { exit 2 }
  if (-not $hwp.Open($payload.path, '', 'forceopen:true;suspendpassword:true;versionwarning:false')) { exit 3 }
  [Console]::Out.Write($hwp.PageCount)
} finally {
  try { $hwp.Close($false) } catch {}
  $hwp.Quit()
}
"""

    env = os.environ.copy()
    env["EDUDOC_HANCOM_PAYLOAD"] = payload
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
        env=env,
    )

    if completed.returncode == 2:
        return _NativePageReadResult(
            register_module_result=False,
            open_succeeded=False,
            observed_pages=None,
            reason="security_module_registration_failed",
        )

    if completed.returncode == 3:
        return _NativePageReadResult(
            register_module_result=True,
            open_succeeded=False,
            observed_pages=None,
            reason="native_page_open_failed",
        )

    if completed.returncode != 0:
        return _NativePageReadResult(
            register_module_result=None,
            open_succeeded=False,
            observed_pages=None,
            reason="native_page_validation_failed",
        )

    try:
        pages = int(completed.stdout.strip())
    except ValueError:
        return _NativePageReadResult(
            register_module_result=True,
            open_succeeded=True,
            observed_pages=None,
            reason="native_page_count_unreadable",
        )

    return _NativePageReadResult(
        register_module_result=True,
        open_succeeded=True,
        observed_pages=pages,
        reason=None,
    )