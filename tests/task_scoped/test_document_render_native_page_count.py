from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import pytest

from core.adapters import hwpx_semantic_contract
from core.adapters.hancom_page_count import HancomAutomationDiscovery, NativePageValidation
from core.adapters.hwpx_template_input import RenderExecutionContext
from core.adapters.hwpx_template_renderer import HwpxTemplateRenderError, JsonValue
from core.document_api import service as document_service
from scripts.templates import render_hwpx_template

ROOT = Path(__file__).resolve().parents[2]
_SOURCE_PACKAGE = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원페이지"
_CONTENT = json.loads(
    (ROOT / "tests" / "fixtures" / "template-content" / "fss_one_page.input.json").read_text(encoding="utf-8")
)
_CONTEXT = RenderExecutionContext(
    requester_name="테스트 요청자",
    requested_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
)


def _native_validation(*, passed: bool, observed_pages: int | None, reason: str | None) -> NativePageValidation:
    return NativePageValidation(
        passed=passed,
        expected_pages=1,
        observed_pages=observed_pages,
        reason=reason,
        discovery=HancomAutomationDiscovery("available", "available", "available", "test-module"),
        register_module_result=True,
        open_succeeded=observed_pages is not None,
    )


def _approved_template_root(tmp_path: Path, *, native_contract: bool) -> Path:
    root = tmp_path / "registry" / "approved"
    package = root / "금융감독원" / "금감원 원페이지"
    shutil.copytree(_SOURCE_PACKAGE, package)
    if native_contract:
        spec = json.loads(
            (ROOT / "tests" / "fixtures" / "business-status-one-page" / "template_spec.json").read_text(encoding="utf-8")
        )
        spec["family_recipe"] = "family_recipe.json"
        (package / "template_spec.json").write_text(
            json.dumps(spec, ensure_ascii=False), encoding="utf-8"
        )
        recipe_source = ROOT / "templates" / "institutions" / "edudoc" / "_families" / "one_page_report" / "recipe.json"
        recipe = tmp_path / "registry" / "provision" / "금융감독원" / "_families" / "one_page_report" / "recipe.json"
        recipe.parent.mkdir(parents=True)
        shutil.copy2(recipe_source, recipe)
        (package / "family_recipe.json").write_text('{"native_page_count": 99}', encoding="utf-8")
    return root


def test_contract_artifact_persistence_copies_optional_family_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "staging"
    candidate = tmp_path / "candidate"
    staging.mkdir()
    candidate.mkdir()
    for name in (
        "template_request.json",
        "semantic_contract.json",
        "template_spec.json",
        "institution_design.json",
        "institution_design.provenance.json",
        "resolved_authoring_contract.json",
        "separation_rules.json",
    ):
        (staging / name).write_text("{}", encoding="utf-8")
    (staging / "family_recipe.json").write_text('{"native_page_count": 1}', encoding="utf-8")
    monkeypatch.setattr(hwpx_semantic_contract, "load_semantic_contract", lambda _: None)
    monkeypatch.setattr(hwpx_semantic_contract, "load_template_spec", lambda _: None)
    monkeypatch.setattr(hwpx_semantic_contract, "bind_semantic_contract", lambda *_: None)
    monkeypatch.setattr(hwpx_semantic_contract, "validate_candidate_field_identity", lambda *_: None)

    hwpx_semantic_contract.persist_candidate_contract_artifacts(staging, candidate)

    assert (candidate / "family_recipe.json").read_text(encoding="utf-8") == '{"native_page_count": 1}'


def test_document_render_succeeds_when_native_page_contract_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_root = _approved_template_root(tmp_path, native_contract=True)
    monkeypatch.setattr(
        document_service,
        "validate_native_page_count",
        lambda *_: _native_validation(passed=True, observed_pages=1, reason=None),
    )

    result = document_service.render_approved_document(
        "금융감독원", "금감원 원페이지", _CONTENT, tmp_path / "success.hwpx", _CONTEXT,
        content_template_id="fss_one_page",
        registry_root=approved_root,
    )

    assert result.output.is_file()


def test_document_render_rejects_native_page_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_root = _approved_template_root(tmp_path, native_contract=True)
    monkeypatch.setattr(
        document_service,
        "validate_native_page_count",
        lambda *_: _native_validation(passed=False, observed_pages=2, reason=None),
    )

    output = tmp_path / "mismatch.hwpx"
    with pytest.raises(HwpxTemplateRenderError, match="expected_pages=1.*observed_pages=2"):
        document_service.render_approved_document(
            "금융감독원", "금감원 원페이지", _CONTENT, output, _CONTEXT,
            content_template_id="fss_one_page",
            registry_root=approved_root,
        )
    # A failed native-page-count contract must not leave a document behind at
    # the caller's intended output path.
    assert not output.exists()


def test_document_render_rejects_unavailable_native_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_root = _approved_template_root(tmp_path, native_contract=True)
    monkeypatch.setattr(
        document_service,
        "validate_native_page_count",
        lambda *_: _native_validation(
            passed=False, observed_pages=None, reason="native_page_validation_unavailable"
        ),
    )

    with pytest.raises(HwpxTemplateRenderError, match="native_page_validation_unavailable"):
        document_service.render_approved_document(
            "금융감독원", "금감원 원페이지", _CONTENT, tmp_path / "unavailable.hwpx", _CONTEXT,
            content_template_id="fss_one_page",
            registry_root=approved_root,
        )


def test_document_render_keeps_legacy_package_without_native_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_root = _approved_template_root(tmp_path, native_contract=False)
    monkeypatch.setattr(
        document_service,
        "validate_native_page_count",
        lambda *_: pytest.fail("legacy package must not invoke native validation"),
    )

    result = document_service.render_approved_document(
        "금융감독원", "금감원 원페이지", _CONTENT, tmp_path / "legacy.hwpx", _CONTEXT,
        content_template_id="fss_one_page",
        registry_root=approved_root,
    )

    assert result.output.is_file()


def test_direct_content_cli_uses_document_api_enforcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    content_path = tmp_path / "content.json"
    content_path.write_text(
        json.dumps(
            {"template_id": "fss_one_page", "fields": _CONTENT},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def reject(
        institution: str,
        document_type: str,
        content: Mapping[str, JsonValue],
        output_path: Path,
        execution_context: RenderExecutionContext,
        *,
        content_template_id: str | None = None,
        registry_root: Path,
    ) -> NoReturn:
        del institution, document_type, content, output_path, execution_context
        assert content_template_id == "fss_one_page"
        raise HwpxTemplateRenderError("native page validation failed: expected_pages=1, observed_pages=2")

    monkeypatch.setattr(render_hwpx_template, "render_approved_document", reject)
    monkeypatch.setattr(render_hwpx_template, "resolve_registry_root", lambda explicit: tmp_path / "registry")
    monkeypatch.setattr(render_hwpx_template, "connect_registry", lambda root: None)

    exit_code = render_hwpx_template.main(
        [
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원페이지",
            "--content",
            str(content_path),
            "--output",
            str(tmp_path / "output.hwpx"),
            "--requester-name",
            "테스트 요청자",
        ]
    )

    assert exit_code == 1
    assert '"ok": false' in capsys.readouterr().out
