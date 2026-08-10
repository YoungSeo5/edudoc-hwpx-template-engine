"""Safe deterministic corrections for lint diagnostics."""
from __future__ import annotations

from ..models import TemplateCandidate, TemplateDiagnostic


def refine_candidate(
    candidate: TemplateCandidate,
    diagnostics: list[TemplateDiagnostic],
) -> bool:
    changed = False
    for diagnostic in diagnostics:
        if diagnostic.action == "clear_unproven_style":
            style = candidate.style_profile
            for field_name in (
                "font_family",
                "body_font_size_pt",
                "page_margins_mm",
                "line_spacing",
            ):
                if getattr(style, field_name) is not None:
                    setattr(style, field_name, None)
                    changed = True
            style.source = "unknown"
            style.confidence = "low"
        elif diagnostic.action == "remove_required_section":
            values = candidate.structure.get("required_sections")
            if isinstance(values, list) and diagnostic.value in values:
                values.remove(diagnostic.value)
                changed = True
    return changed
