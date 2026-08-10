"""Final deterministic success gate for template candidates."""
from __future__ import annotations

from dataclasses import dataclass

from ..models import TemplateCandidate, TemplateDiagnostic
from .success_rules import SuccessRules


@dataclass(frozen=True)
class GateResult:
    passed: bool
    error_count: int
    reasons: tuple[str, ...]


def evaluate_gate(
    candidate: TemplateCandidate,
    diagnostics: list[TemplateDiagnostic],
    rules: SuccessRules,
) -> GateResult:
    errors = [item for item in diagnostics if item.severity == "error"]
    reasons = tuple(item.message for item in errors)
    return GateResult(
        passed=len(errors) <= rules.max_error_count,
        error_count=len(errors),
        reasons=reasons,
    )
