"""Template extraction, review, refinement, and validation pipeline."""
from __future__ import annotations

from pathlib import Path
from zipfile import is_zipfile

from .extractors import (
    extract_structure,
    extract_structure_from_text,
    extract_style,
    hwp_to_text,
    style_mentions_in_text,
)
from .models import RendererContract, TemplateCandidate, TemplateIdentity
from .quality.false_positive import (
    FalsePositiveRule,
    apply_false_positive_rules,
)
from .quality.gate import GateResult, evaluate_gate
from .quality.lint import lint_candidate
from .quality.refine import refine_candidate
from .quality.success_rules import SuccessRules

UNKNOWN = "확인 필요"

# 이 모듈은 참조 문서에서 일반적인 구조·스타일 근거를 모아 품질을 판정한다.
# HWPX 패키지 복사와 placeholder XML 생성은 hwpx_package_extractor 및
# hwpx_content_separator의 별도 책임이다.

def build_candidate(
    reference: Path | str,
    *,
    institution: str,
    document_type: str,
    route: str | None = None,
    extends: str | None = None,
) -> TemplateCandidate:
    """Build one candidate shape from deterministic reference observations."""
    reference = Path(reference)

    # 흐름 1: 스타일은 형식과 별개로 먼저 추출하고, 아래 분기에서는
    # 참조 형식별로 얻을 수 있는 구조 증거만 수집한다.
    style = extract_style(reference)
    evidence = [f"reference_path: {reference.as_posix()}"]
    style_mentions: list[str] = []

    if is_zipfile(reference):
        reference_format = "hwpx"
        structure = extract_structure(reference)
        evidence.append("HWPX XML inspected: Contents/header.xml and Contents/section0.xml")
    elif reference.suffix.lower() == ".hwp":
        reference_format = "hwp"
        text = hwp_to_text(reference)
        if text:
            structure = extract_structure_from_text(text)
            style_mentions = style_mentions_in_text(text)
            evidence.append("legacy HWP text extracted through pyhwp")
        else:
            structure = extract_structure(reference)
            evidence.append("legacy HWP text extraction unavailable")
    else:
        reference_format = reference.suffix.lower().lstrip(".") or "unknown"
        structure = extract_structure(reference)
        evidence.append(f"no deterministic extractor for format={reference_format}")

    if style_mentions:
        evidence.extend(f"style_text_mention (not parsed style): {item}" for item in style_mentions)

    # 흐름 2: 자동 추출로 증명하지 못한 필드는 추측하지 않고
    # unknown_fields와 "확인 필요"로 명시한다.
    unknown_fields = ["structure.required_sections", "structure.required_fields"]
    for field_name in ("font_family", "body_font_size_pt", "page_margins_mm", "line_spacing"):
        if getattr(style, field_name) is None:
            unknown_fields.append(f"style_profile.{field_name}")
    if route is None:
        unknown_fields.append("renderer.route")

    structure = {
        **structure,
        "required_sections": UNKNOWN,
        "required_fields": UNKNOWN,
        "repeat_sections": UNKNOWN,
    }

    # 흐름 3: 추출 결과를 모든 템플릿 품질 단계가 공유하는
    # TemplateCandidate 한 개로 정규화한다.
    return TemplateCandidate(
        identity=TemplateIdentity(
            institution=institution,
            document_type=document_type,
            extends=extends,
        ),
        reference_path=reference.as_posix(),
        reference_format=reference_format,
        structure=structure,
        writing_rules={"tone": UNKNOWN, "unknown_policy": UNKNOWN},
        style_profile=style,
        renderer=RendererContract(
            preferred_format="docx",
            route=route,
            reference_hwpx=reference.as_posix() if reference_format == "hwpx" else None,
            fallback="md2hwpx",
        ),
        evidence=evidence,
        unknown_fields=unknown_fields,
    )


def run_template_pipeline(
    reference: Path | str,
    *,
    institution: str,
    document_type: str,
    route: str | None = None,
    extends: str | None = None,
    success_rules: SuccessRules | None = None,
    false_positive_rules: list[FalsePositiveRule] | None = None,
    max_refinement_passes: int = 3,
) -> tuple[TemplateCandidate, GateResult]:
    """Extract, lint, refine, and gate a template candidate."""
    rules = success_rules or SuccessRules()

    # 흐름 1: 참조 문서에서 최초 후보를 만든다.
    candidate = build_candidate(
        reference,
        institution=institution,
        document_type=document_type,
        route=route,
        extends=extends,
    )

    # 흐름 2: 과거 검토에서 확정한 오탐 규칙을 먼저 적용해,
    # 이후 lint와 보정이 같은 오탐을 다시 문제로 취급하지 않게 한다.
    memory_diagnostics = apply_false_positive_rules(
        candidate,
        false_positive_rules or [],
    )

    passes = 0
    refinement_history = []

    # 흐름 3: lint 진단으로 자동 보정 가능한 항목만 제한 횟수 내에서
    # 고친다. 더 이상 바뀌지 않으면 즉시 반복을 끝낸다.
    for pass_number in range(1, max_refinement_passes + 1):
        diagnostics = lint_candidate(candidate, rules)
        if not refine_candidate(candidate, diagnostics):
            break
        refinement_history.extend(diagnostics)
        passes = pass_number

    # 흐름 4: 보정이 끝난 최종 후보를 다시 검사하고 성공 게이트를 평가한다.
    # 통과 상태는 validated일 뿐 approved가 아니며, 승인은 serialization 단계의
    # 명시적 approve 입력이 별도로 필요하다.
    candidate.refinement_passes = passes
    final_diagnostics = lint_candidate(candidate, rules)
    candidate.diagnostics = memory_diagnostics + refinement_history + final_diagnostics
    gate = evaluate_gate(candidate, final_diagnostics, rules)
    candidate.status = "validated" if gate.passed else "rejected"
    return candidate, gate
