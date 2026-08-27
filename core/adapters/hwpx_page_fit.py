"""One-page page-fit measurement, failure, and diagnosis — no auto-compaction.

이 모듈은 `docs/tasks/one-page-page-fit.md`의 결과물이다. 배경: `one_page_report`
family는 `native_page_count`(현재 항상 1) 검증 게이트를 갖고 있지만, 실제
콘텐츠 밀도(N 늘어난 collection)에 맞춰 layout을 조정하는 production 로직은
없었다 — 3건 project_tasks + 4건 next_actions 입력에서 실측 `PageCount=2`가
그 gap을 증명했다.

**이 모듈은 콘텐츠를 자동으로 압축해 1페이지에 욱여넣지 않는다.** 이전 버전은
`compact`/`minimum` density profile(line-spacing ×0.87, spacing/cell-margin
×0.5, ×0)을 자동 선택해 1페이지를 만들었으나, 그 계수들이 실제로는 baseline
관찰값을 재해석해 만든 heuristic이었지 evidence가 직접 증명한 값이 아니었다는
지적을 받아 **production contract에서 제거했다**(사용자 결정, 이 task
대화 기록 참고). `core/adapters/hwpx_authoring_resolve.py`도 이 결정에 맞춰
`density_profile` 매개변수 없이 원상 복구됐다.

지금 이 모듈이 하는 일은 오직 세 가지다:

1. **측정**: 기존 계층(`resolve()` → `generate_source_hwpx()` →
   `build_separation_rules()`/`write_separation_rules()` →
   `separate_hwpx_template_content()` → `render_candidate_roundtrip()`)을
   그대로 호출해 `default` 설정으로 딱 한 번 렌더링하고, 실제 Hancom
   PageCount를 측정한다.
2. **실패**: 측정된 PageCount가 family recipe의 `native_page_count`와 다르면
   `PageFitResult.ok = False`를 정직하게 반환한다 — 압축을 시도하지 않고,
   성공한 문서로 위장하지도 않는다. 이는 콘텐츠가 실제로 `expected_pages`에
   들어가지 않는다는 정상적인 측정 결과에만 쓰인다. authoring/render 실패나
   콘텐츠 불완전(leftover placeholder·missing field)처럼 호출자가 고쳐야 할
   설정/입력 문제는 `ok=False`로 위장하지 않고 `HwpxPageFitError`를 그대로
   던진다.
3. **진단**: 실패 시 무엇을 측정했는지(기대 페이지 수, 실제 관찰된 페이지 수,
   placeholder/필드 완결성)를 `PageFitAttempt`에 그대로 남겨, 사람이 원인을
   추적할 수 있게 한다.

"이 family가 반드시 1페이지여야 하는가"와 "그렇다면 어떤 속성을 어디까지
줄일 수 있는가"는 Institution Design 수준의 정책 결정이 필요하다 — 이
모듈은 그 결정을 내리지 않는다. 그 정책이 결정되면 이 모듈에 다시
profile 선택 로직을 연결할 수 있다(설계는 `docs/tasks/one-page-page-fit.md`
참고).
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..sandbox_paths import SandboxUnavailableError, require_sandbox_temp_root
from .hancom_page_count import NativePageValidation, validate_native_page_count
from .hwpx_authoring_resolve import HwpxAuthoringResolveError, resolve
from .hwpx_semantic_contract import (
    SemanticContractError,
    bind_semantic_contract,
    load_semantic_contract,
)
from .hwpx_template_authoring import (
    HwpxTemplateAuthoringError,
    TemplateSpec,
    build_separation_rules,
    generate_source_hwpx,
    validate_semantic_placements,
    write_separation_rules,
)
from .hwpx_template_renderer import (
    HwpxTemplateRenderError,
    JsonValue,
    RenderResult,
    render_candidate_roundtrip,
)

from core.templates.hwpx_content_separator import separate_hwpx_template_content  # noqa: E402
from core.templates.hwpx_semantic_classifier import SemanticAmbiguityError  # noqa: E402


class HwpxPageFitError(RuntimeError):
    """Raised for a configuration/input error — never for "does not fit"."""


@dataclass(frozen=True, slots=True)
class PageFitAttempt:
    native_page_validation: NativePageValidation | None
    leftover_placeholders: tuple[str, ...]
    missing_fields: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PageFitResult:
    ok: bool
    expected_pages: int
    attempt: PageFitAttempt


def render_one_page_with_page_fit(
    *,
    template_spec: TemplateSpec,
    semantic_contract_path: Path,
    institution_design_path: Path,
    content: Mapping[str, JsonValue],
    output_path: Path,
    institution: str,
    template_id: str,
    expected_pages: int | None = None,
) -> PageFitResult:
    """Render *content* once at the family's declared `default` layout and
    measure its real Hancom PageCount — no automatic compaction.

    Returns ``ok=True`` (and writes *output_path*) only if the single
    measured attempt already matches *expected_pages*. Returns ``ok=False``
    with the measured attempt recorded for diagnosis only when PageCount was
    actually measured and genuinely does not match — content that honestly
    does not fit in *expected_pages*. It never writes *output_path* in that
    case — never a document disguised as successful. Any other failure
    (authoring, rendering, or content left incomplete despite a correct page
    count) is a caller-fixable configuration/input problem and raises
    ``HwpxPageFitError`` instead of being folded into ``ok=False``.
    """
    spec = template_spec
    if expected_pages is None:
        expected_pages = _required_native_pages(spec)
    if expected_pages is None:
        raise HwpxPageFitError(
            "expected_pages was not given and the TemplateSpec's family recipe "
            "declares no native_page_count to measure against"
        )

    try:
        semantic_raw = _load_json(semantic_contract_path)
        semantic = load_semantic_contract(semantic_contract_path)
        binding = bind_semantic_contract(semantic, spec)
        placements = validate_semantic_placements(semantic_raw, spec)
    except (HwpxTemplateAuthoringError, SemanticContractError, OSError, ValueError) as exc:
        raise HwpxPageFitError(f"cannot prepare semantic binding: {exc}") from exc

    try:
        sandbox_root = require_sandbox_temp_root()
    except SandboxUnavailableError as exc:
        raise HwpxPageFitError(str(exc)) from exc
    with tempfile.TemporaryDirectory(prefix="hwpx-page-fit-", dir=sandbox_root) as tmp:
        attempt, rendered_output = _attempt_default(
            tmp_root=Path(tmp),
            spec=spec,
            institution_design_path=institution_design_path,
            binding=binding,
            placements=placements,
            content=content,
            institution=institution,
            template_id=template_id,
            expected_pages=expected_pages,
        )
        if rendered_output is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(rendered_output, output_path)
            return PageFitResult(ok=True, expected_pages=expected_pages, attempt=attempt)

    return PageFitResult(ok=False, expected_pages=expected_pages, attempt=attempt)


def _attempt_default(
    *,
    tmp_root: Path,
    spec: TemplateSpec,
    institution_design_path: Path,
    binding: Any,
    placements: Any,
    content: Mapping[str, JsonValue],
    institution: str,
    template_id: str,
    expected_pages: int,
) -> tuple[PageFitAttempt, Path | None]:
    from dataclasses import replace as dataclass_replace

    try:
        resolved = dataclass_replace(
            resolve(institution_design_path, spec, binding),
            semantic_placements=placements,
        )
        source_hwpx = generate_source_hwpx(resolved, tmp_root / "source.hwpx")
        rules = build_separation_rules(resolved, source_hwpx)
        rules_path = write_separation_rules(rules, tmp_root / "rules.json")
        candidate_dir = tmp_root / "candidate"
        separate_hwpx_template_content(
            source_hwpx,
            candidate_dir,
            template_id=template_id,
            institution=institution,
            rules_path=rules_path,
        )
    except (
        HwpxAuthoringResolveError,
        HwpxTemplateAuthoringError,
        SemanticAmbiguityError,
        ValueError,
        OSError,
    ) as exc:
        # A caller-fixable configuration/input problem (bad contract, bad
        # design, bad TemplateSpec), not a "this content doesn't fit one
        # page" outcome — raise rather than reporting it as ok=False, so a
        # caller cannot mistake it for legitimate page overflow.
        raise HwpxPageFitError(f"authoring failed: {exc}") from exc

    rendered_output = tmp_root / "rendered.hwpx"
    try:
        result: RenderResult = render_candidate_roundtrip(candidate_dir, content, rendered_output)
    except HwpxTemplateRenderError as exc:
        # Same reasoning: a render failure is a caller-fixable defect, not a
        # page-fit outcome.
        raise HwpxPageFitError(f"render failed: {exc}") from exc

    validation = validate_native_page_count(rendered_output, expected_pages)
    attempt = PageFitAttempt(
        native_page_validation=validation,
        leftover_placeholders=tuple(result.leftover_placeholders),
        missing_fields=tuple(result.missing_fields),
    )
    if not validation.passed:
        # The only legitimate ok=False outcome: PageCount was actually
        # measured and it does not match — the content genuinely does not
        # fit in `expected_pages`.
        return attempt, None
    if result.leftover_placeholders or result.missing_fields:
        # The page count is right, but the supplied content did not fully
        # resolve — a content/mapping defect, not a page-fit outcome.
        raise HwpxPageFitError(
            "content incomplete despite page fit: "
            f"leftover_placeholders={list(result.leftover_placeholders)}, "
            f"missing_fields={list(result.missing_fields)}"
        )
    return attempt, rendered_output


def _required_native_pages(spec: TemplateSpec) -> int | None:
    if not spec.family_recipe_path:
        return None
    data = _load_json(Path(spec.family_recipe_path))
    value = data.get("native_page_count")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HwpxPageFitError("family recipe native_page_count must be a positive integer")
    return value


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HwpxPageFitError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HwpxPageFitError(f"{path} root must be an object")
    return data


__all__ = [
    "HwpxPageFitError",
    "PageFitAttempt",
    "PageFitResult",
    "render_one_page_with_page_fit",
]
