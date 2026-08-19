from __future__ import annotations

from pathlib import Path

from core.adapters import hancom_page_count


def test_discovery_reports_missing_security_module_without_disabling_com(
    monkeypatch,
) -> None:
    monkeypatch.setattr(hancom_page_count, "_automation_available", lambda: True)
    monkeypatch.setattr(hancom_page_count, "_registered_security_modules", lambda: ())

    discovery = hancom_page_count.discover_hancom_automation()

    assert discovery.hancom_automation == "available"
    assert discovery.security_module == "missing"
    assert discovery.native_page_validation == "unavailable"


def test_required_native_page_validation_rejects_unavailable_backend(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        hancom_page_count,
        "discover_hancom_automation",
        lambda: hancom_page_count.HancomAutomationDiscovery(
            hancom_automation="available",
            security_module="missing",
            native_page_validation="unavailable",
            security_module_name=None,
        ),
    )

    result = hancom_page_count.validate_native_page_count(tmp_path / "candidate.hwpx", 1)

    assert result.passed is False
    assert result.reason == "native_page_validation_unavailable"
