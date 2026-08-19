from __future__ import annotations

from pathlib import Path

from core.adapters.hancom_page_count import HancomAutomationDiscovery, NativePageValidation
from scripts.templates import check_native_page_count


def test_cli_reports_a_native_page_pass(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        check_native_page_count,
        "validate_native_page_count",
        lambda _input, required: NativePageValidation(
            passed=True,
            expected_pages=required,
            observed_pages=1,
            reason=None,
            discovery=HancomAutomationDiscovery("available", "available", "available", "discovered-module"),
        ),
    )

    exit_code = check_native_page_count.main(["--input", str(tmp_path / "candidate.hwpx"), "--required-pages", "1"])

    assert exit_code == 0
    assert "register_module = true" in capsys.readouterr().out
