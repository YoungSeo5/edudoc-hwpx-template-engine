from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

import pytest

from core.adapters.hwpx_source_content_mapper import MappingResult
from core.adapters.hwpx_template_input import RenderExecutionContext
from core.adapters.hwpx_template_renderer import HwpxTemplateRenderError, RenderResult
from core.document_api import service as document_service


_CONTEXT = RenderExecutionContext(
    requester_name="테스트 요청자",
    requested_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
)
_INSTITUTION = "금융감독원"
_DOCUMENT_TYPE = "금감원 원장보고"
_TEMPLATE_ID = "fss_director_report"
_SOURCE = Path(__file__).resolve().parents[2] / "templates" / "institutions" / _INSTITUTION / _DOCUMENT_TYPE


@pytest.fixture
def approved_root(tmp_path: Path) -> Path:
    root = tmp_path / "registry" / "approved"
    shutil.copytree(_SOURCE, root / _INSTITUTION / _DOCUMENT_TYPE)
    return root


def test_direct_render_rejects_missing_template_identity_before_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved_root: Path
) -> None:
    monkeypatch.setattr(
        document_service,
        "orchestrate_hwpx_render",
        lambda *_args, **_kwargs: pytest.fail("renderer must not run"),
    )

    with pytest.raises(HwpxTemplateRenderError, match="template_id"):
        document_service.render_approved_document(
            _INSTITUTION,
            _DOCUMENT_TYPE,
            {},
            tmp_path / "output.hwpx",
            _CONTEXT,
            content_template_id=None,
            registry_root=approved_root,
        )


def test_direct_render_rejects_mismatched_template_identity_before_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved_root: Path
) -> None:
    monkeypatch.setattr(
        document_service,
        "orchestrate_hwpx_render",
        lambda *_args, **_kwargs: pytest.fail("renderer must not run"),
    )

    with pytest.raises(HwpxTemplateRenderError, match="template_id mismatch"):
        document_service.render_approved_document(
            _INSTITUTION,
            _DOCUMENT_TYPE,
            {},
            tmp_path / "output.hwpx",
            _CONTEXT,
            content_template_id="other-template",
            registry_root=approved_root,
        )


def test_direct_render_keeps_matching_template_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, approved_root: Path
) -> None:
    output = tmp_path / "output.hwpx"
    expected = RenderResult(output=output)
    monkeypatch.setattr(
        document_service,
        "orchestrate_hwpx_render",
        lambda *_args, **_kwargs: expected,
    )

    result = document_service.render_approved_document(
        _INSTITUTION,
        _DOCUMENT_TYPE,
        {},
        output,
        _CONTEXT,
        content_template_id=_TEMPLATE_ID,
        registry_root=approved_root,
    )

    assert result is expected


def test_source_render_passes_selected_template_identity_to_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.hwpx"
    monkeypatch.setattr(
        document_service,
        "get_template_contract",
        lambda *_args, **_kwargs: ({"template_id": _TEMPLATE_ID, "fields": []}, None),
    )
    monkeypatch.setattr(document_service, "read_source_as_markdown", lambda _: "source")
    monkeypatch.setattr(
        document_service,
        "map_source_to_content",
        lambda *_args: MappingResult(content={}, unresolved_fields=[]),
    )

    def render(
        institution: str,
        document_type: str,
        content: dict,
        output_path: Path,
        execution_context: RenderExecutionContext,
        *,
        content_template_id: str | None = None,
        registry_root: Path,
    ) -> RenderResult:
        assert institution == _INSTITUTION
        assert document_type == _DOCUMENT_TYPE
        assert content == {}
        assert output_path == output
        assert execution_context == _CONTEXT
        assert content_template_id == _TEMPLATE_ID
        assert registry_root == tmp_path / "registry" / "approved"
        return RenderResult(output=output)

    monkeypatch.setattr(document_service, "render_approved_document", render)

    result = document_service.render_document_from_source(
        _INSTITUTION,
        _DOCUMENT_TYPE,
        tmp_path / "source.md",
        output,
        _CONTEXT,
        registry_root=tmp_path / "registry" / "approved",
    )

    assert result.output == output
