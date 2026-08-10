"""Static analysis for extracted template candidates."""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from ..models import TemplateCandidate, TemplateDiagnostic
from .success_rules import SuccessRules

_CONTENT_VALUE = re.compile(
    r"(?:\b20\d{2}\b|[\d,]+\s*(?:원|천원|만원|억원)|\d{4}[.-]\s*\d{1,2}|"
    r"(?:담당자|작성자|성명)\s*[:：])"
)


def lint_candidate(
    candidate: TemplateCandidate,
    rules: SuccessRules,
) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    blob = candidate.to_dict()

    if rules.forbid_fake_placeholders and _contains_fake_placeholder(blob):
        diagnostics.append(
            TemplateDiagnostic(
                rule_id="TPL001",
                severity="error",
                message='가짜 추출값 "..."를 사용할 수 없습니다.',
            )
        )

    if rules.require_evidence and not candidate.evidence:
        diagnostics.append(
            TemplateDiagnostic(
                rule_id="EVIDENCE001",
                severity="error",
                path="evidence",
                message="템플릿 후보에 추출 근거가 없습니다.",
            )
        )

    if rules.require_structure_signal and not _has_structure_signal(candidate):
        diagnostics.append(
            TemplateDiagnostic(
                rule_id="STRUCT001",
                severity="error",
                path="structure",
                message="마커, 표 또는 본문 후보 중 하나 이상의 구조 근거가 필요합니다.",
            )
        )

    style = candidate.style_profile
    style_values = (
        style.font_family,
        style.body_font_size_pt,
        style.page_margins_mm,
        style.line_spacing,
    )
    if (
        rules.forbid_unproven_style
        and style.source != "extracted_from_hwpx"
        and any(value is not None for value in style_values)
    ):
        diagnostics.append(
            TemplateDiagnostic(
                rule_id="STYLE001",
                severity="error",
                path="style_profile",
                action="clear_unproven_style",
                message="HWPX XML 근거 없이 확정된 스타일값을 제거해야 합니다.",
            )
        )

    required = candidate.structure.get("required_sections")
    if isinstance(required, list):
        for value in required:
            text = str(value).strip()
            if len(text) > 60 or _CONTENT_VALUE.search(text):
                diagnostics.append(
                    TemplateDiagnostic(
                        rule_id="STRUCT002",
                        severity="warning",
                        path="structure.required_sections",
                        action="remove_required_section",
                        value=value,
                        message="예시 내용값으로 보이는 항목을 필수 섹션에서 제거합니다.",
                    )
                )

    if style.source == "extracted_from_hwpx" and not style.evidence:
        diagnostics.append(
            TemplateDiagnostic(
                rule_id="STYLE002",
                severity="error",
                path="style_profile.evidence",
                message="추출 스타일에는 XML 근거가 필요합니다.",
            )
        )

    return diagnostics


def _contains_fake_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() == "..."
    if isinstance(value, dict):
        return any(_contains_fake_placeholder(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_fake_placeholder(item) for item in value)
    return False


def _has_structure_signal(candidate: TemplateCandidate) -> bool:
    structure = candidate.structure
    return bool(
        structure.get("marker_system")
        or structure.get("tables")
        or structure.get("line_candidates")
    )
