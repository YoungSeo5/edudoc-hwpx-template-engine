"""Persistent false-positive rules used by later template extractions."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ..models import TemplateCandidate, TemplateDiagnostic


@dataclass(frozen=True)
class FalsePositiveRule:
    rule_id: str
    target: str
    pattern: str
    reason: str
    institution: str | None = None
    document_type: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def applies_to(self, candidate: TemplateCandidate) -> bool:
        identity = candidate.identity
        return (
            (self.institution is None or self.institution == identity.institution)
            and (self.document_type is None or self.document_type == identity.document_type)
        )


def load_false_positive_rules(paths: list[Path | str] | None = None) -> list[FalsePositiveRule]:
    rules: list[FalsePositiveRule] = []
    for path in paths or []:
        rule_path = Path(path)
        if not rule_path.is_file():
            continue
        data = json.loads(rule_path.read_text(encoding="utf-8"))
        for item in data.get("rules", []):
            rules.append(FalsePositiveRule(**item))
    return rules


def apply_false_positive_rules(
    candidate: TemplateCandidate,
    rules: list[FalsePositiveRule],
) -> list[TemplateDiagnostic]:
    diagnostics: list[TemplateDiagnostic] = []
    for rule in rules:
        if not rule.applies_to(candidate):
            continue
        values = _target_list(candidate, rule.target)
        if values is None:
            continue
        pattern = re.compile(rule.pattern)
        rejected = [value for value in values if pattern.search(str(value))]
        if not rejected:
            continue
        values[:] = [value for value in values if value not in rejected]
        for value in rejected:
            diagnostics.append(
                TemplateDiagnostic(
                    rule_id=rule.rule_id,
                    severity="info",
                    path=rule.target,
                    value=value,
                    message=rule.reason,
                )
            )
    return diagnostics


def learned_rules_from_diagnostics(
    candidate: TemplateCandidate,
) -> list[FalsePositiveRule]:
    """Turn proven, auto-refined false positives into narrowly scoped memory."""
    rules: list[FalsePositiveRule] = []
    seen: set[tuple[str, str]] = set()
    for item in candidate.diagnostics:
        if item.action != "remove_required_section" or item.value is None or not item.path:
            continue
        key = (item.path, str(item.value))
        if key in seen:
            continue
        seen.add(key)
        rules.append(
            FalsePositiveRule(
                rule_id=f"LEARNED-{len(rules) + 1:03d}",
                target=item.path,
                pattern=f"^{re.escape(str(item.value))}$",
                reason=item.message,
                institution=candidate.identity.institution,
                document_type=candidate.identity.document_type,
            )
        )
    return rules


def _target_list(candidate: TemplateCandidate, target: str) -> list | None:
    if target == "structure.line_candidates":
        value = candidate.structure.get("line_candidates")
    elif target == "structure.required_sections":
        value = candidate.structure.get("required_sections")
    else:
        return None
    return value if isinstance(value, list) else None
