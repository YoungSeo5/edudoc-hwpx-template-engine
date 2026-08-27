"""docs/tasks/one-page-page-fit.md.

`one_page_report`은 `native_page_count=1` 검증 게이트를 갖고 있었지만, 실제
콘텐츠 밀도(collection cardinality)에 맞춰 layout을 조정해 1페이지를 지키는
production 로직은 없었다 — 3건 project_tasks + 4건 next_actions 입력에서
실측 `PageCount=2`가 그 gap을 증명했다.

이 테스트는 `core.adapters.hwpx_page_fit.render_one_page_with_page_fit()`이
실제 Hancom PageCount를 **측정**하고, 기대와 다르면 문서를 압축해 통과시키지
않고 **정직하게 실패**시키는지를 검증한다. 자동 압축(density profile 자동
선택)은 사용자 결정으로 production contract에서 제거됐다 — 그 계수
(line-spacing ×0.87, spacing/cell-margin ×0.5·×0)가 evidence로 직접 증명된
값이 아니라 baseline 관찰을 재해석해 만든 heuristic이었다는 지적을 받았기
때문이다. "이 family가 반드시 1페이지여야 하는가"와 "그렇다면 무엇을 얼마나
줄일 수 있는가"는 Institution Design 수준의 별도 정책 결정이 필요하며 이
task 범위 밖이다.

Hancom Automation 자체가 이 실행 환경에 없으면(native_page_validation이
`unavailable`) 실제 PageCount를 아무도 실측할 수 없다는 뜻이라 이 테스트는
그 사실만 기록하고 스킵한다.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import hwpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import sandbox_paths  # noqa: E402
from core.adapters import hwpx_page_fit as page_fit_module  # noqa: E402
from core.adapters.hancom_page_count import (  # noqa: E402
    HancomAutomationDiscovery,
    NativePageValidation,
)
from core.adapters.hwpx_authoring_resolve import HwpxAuthoringResolveError  # noqa: E402
from core.adapters.hwpx_page_fit import (  # noqa: E402
    HwpxPageFitError,
    render_one_page_with_page_fit,
)
from core.adapters.hwpx_template_authoring import load_template_spec  # noqa: E402
from core.adapters.hwpx_template_renderer import HwpxTemplateRenderError  # noqa: E402

_FIXTURES = ROOT / "tests" / "fixtures" / "business-status-one-page"
_SPEC = _FIXTURES / "template_spec.json"
_SEMANTIC = _FIXTURES / "semantic_contract.json"
_DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"


def _base_content() -> dict[str, Any]:
    return json.loads((_FIXTURES / "fixture-normal.json").read_text(encoding="utf-8"))["fields"]


def _dense_task(index: int) -> dict[str, str]:
    return {
        "task_name": f"작업 {index}",
        "stage": "진행",
        "progress": f"{10 * index}%",
        "schedule": f"{index}월",
    }


def _dense_action(index: int) -> dict[str, object]:
    return {"level": 1 if index % 2 == 0 else 2, "text": f"조치 {index}"}


def _require_native_validation(attempt) -> None:
    if (
        attempt.native_page_validation is not None
        and attempt.native_page_validation.reason == "native_page_validation_unavailable"
    ):
        pytest.skip(
            "Hancom Automation native page validation is unavailable in this "
            "environment — cannot measure real PageCount"
        )


def _render(task_count: int, action_count: int, label: str, tmp_path: Path):
    spec = load_template_spec(_SPEC)
    content = _base_content()
    content["project_tasks"] = [_dense_task(i) for i in range(task_count)]
    content["next_actions"] = [_dense_action(i) for i in range(action_count)]
    output = tmp_path / f"{label}.hwpx"
    result = render_one_page_with_page_fit(
        template_spec=spec,
        semantic_contract_path=_SEMANTIC,
        institution_design_path=_DESIGN,
        content=content,
        output_path=output,
        institution="edudoc",
        template_id=f"page-fit-{label}-{uuid.uuid4().hex}",
    )
    return result, output


@pytest.mark.parametrize(
    ("label", "task_count", "action_count"),
    [
        ("sparse", 0, 0),
        ("one_each", 1, 1),
    ],
)
def test_one_page_page_fit_measures_and_passes_when_default_already_fits(
    tmp_path: Path, label: str, task_count: int, action_count: int
) -> None:
    result, output = _render(task_count, action_count, label, tmp_path)
    _require_native_validation(result.attempt)

    assert result.expected_pages == 1
    assert result.ok is True
    assert output.is_file()
    assert hwpx.validate_package(output).ok is True
    assert result.attempt.native_page_validation.passed is True
    assert result.attempt.native_page_validation.observed_pages == 1
    assert result.attempt.leftover_placeholders == ()
    assert result.attempt.missing_fields == ()


def test_one_page_page_fit_measures_and_fails_honestly_without_compacting(tmp_path: Path) -> None:
    """The exact case that first proved the gap: 3 project_tasks + 4
    next_actions genuinely overflows the default one-page layout. This must
    now fail explicitly — not be silently compacted into fitting."""
    result, output = _render(3, 4, "dense_3_project_tasks_4_next_actions", tmp_path)
    _require_native_validation(result.attempt)

    assert result.expected_pages == 1
    assert result.ok is False
    assert not output.exists()
    assert result.attempt.native_page_validation is not None
    assert result.attempt.native_page_validation.passed is False
    assert result.attempt.native_page_validation.observed_pages == 2


def test_one_page_page_fit_fails_explicitly_for_a_larger_overflow(tmp_path: Path) -> None:
    result, output = _render(6, 8, "larger", tmp_path)
    _require_native_validation(result.attempt)

    assert result.ok is False
    assert not output.exists()
    assert result.attempt.native_page_validation is not None
    assert result.attempt.native_page_validation.passed is False


def test_page_fit_measurement_uses_the_repository_sandbox_not_os_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AGENTS.md: QA temp artifacts stay under sandbox/, never the OS temp volume."""
    # tempfile is a process-wide singleton module, so patching it here also
    # observes any TemporaryDirectory the rest of the render pipeline (e.g.
    # candidate separation) happens to create — filter to this module's own
    # call by its distinguishing prefix rather than asserting on every call.
    real_temporary_directory = page_fit_module.tempfile.TemporaryDirectory
    seen_dirs: list[Path | None] = []

    class _RecordingTemporaryDirectory(real_temporary_directory):
        def __init__(self, *args, **kwargs):
            if kwargs.get("prefix") == "hwpx-page-fit-":
                seen_dirs.append(kwargs.get("dir"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        page_fit_module.tempfile, "TemporaryDirectory", _RecordingTemporaryDirectory
    )

    _render(0, 0, "sandbox-check", tmp_path)

    assert seen_dirs == [sandbox_paths.ROOT / "sandbox"]


def test_authoring_failure_raises_instead_of_reporting_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller-fixable authoring/config defect must not look like a
    legitimate page-overflow outcome (ok=False)."""
    spec = load_template_spec(_SPEC)

    def _broken_resolve(*args, **kwargs):
        raise HwpxAuthoringResolveError("boom")

    monkeypatch.setattr(page_fit_module, "resolve", _broken_resolve)

    with pytest.raises(HwpxPageFitError, match="authoring failed"):
        render_one_page_with_page_fit(
            template_spec=spec,
            semantic_contract_path=_SEMANTIC,
            institution_design_path=_DESIGN,
            content=_base_content(),
            output_path=tmp_path / "authoring-failure.hwpx",
            institution="edudoc",
            template_id=f"page-fit-authoring-failure-{uuid.uuid4().hex}",
        )


def test_render_failure_raises_instead_of_reporting_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller-fixable render defect must not look like a legitimate
    page-overflow outcome (ok=False)."""
    spec = load_template_spec(_SPEC)

    def _broken_render(*args, **kwargs):
        raise HwpxTemplateRenderError("boom")

    monkeypatch.setattr(page_fit_module, "render_candidate_roundtrip", _broken_render)

    with pytest.raises(HwpxPageFitError, match="render failed"):
        render_one_page_with_page_fit(
            template_spec=spec,
            semantic_contract_path=_SEMANTIC,
            institution_design_path=_DESIGN,
            content=_base_content(),
            output_path=tmp_path / "render-failure.hwpx",
            institution="edudoc",
            template_id=f"page-fit-render-failure-{uuid.uuid4().hex}",
        )


def test_content_incomplete_despite_correct_page_count_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A correct page count with leftover placeholders is a content/mapping
    defect, not a page-fit outcome — it must not report ok=False either."""
    spec = load_template_spec(_SPEC)
    content = dict(_base_content())
    del content["decision_request"]  # leaves {{decision_request}} unresolved

    monkeypatch.setattr(
        page_fit_module,
        "validate_native_page_count",
        lambda *_args, **_kwargs: NativePageValidation(
            passed=True,
            expected_pages=1,
            observed_pages=1,
            reason=None,
            discovery=HancomAutomationDiscovery("available", "available", "available", "test-module"),
            register_module_result=True,
            open_succeeded=True,
        ),
    )

    with pytest.raises(HwpxPageFitError, match="content incomplete"):
        render_one_page_with_page_fit(
            template_spec=spec,
            semantic_contract_path=_SEMANTIC,
            institution_design_path=_DESIGN,
            content=content,
            output_path=tmp_path / "content-incomplete.hwpx",
            institution="edudoc",
            template_id=f"page-fit-content-incomplete-{uuid.uuid4().hex}",
        )


def test_resolve_no_longer_accepts_a_density_profile_argument() -> None:
    """core/adapters/hwpx_authoring_resolve.py must not expose the removed
    auto-compaction mechanism — DENSITY_PROFILES and the density_profile
    parameter were pulled from the production contract."""
    import inspect

    from core.adapters import hwpx_authoring_resolve

    assert not hasattr(hwpx_authoring_resolve, "DENSITY_PROFILES")
    assert "density_profile" not in inspect.signature(hwpx_authoring_resolve.resolve).parameters
