"""Render an auditable Markdown review for a template candidate."""
from __future__ import annotations

from ..models import TemplateCandidate
from .gate import GateResult


def render_review(candidate: TemplateCandidate, gate: GateResult) -> str:
    lines = [
        "# Template Review",
        "",
        f"- institution: `{candidate.identity.institution}`",
        f"- document_type: `{candidate.identity.document_type}`",
        f"- status: `{candidate.status}`",
        f"- gate_passed: `{gate.passed}`",
        f"- refinement_passes: `{candidate.refinement_passes}`",
        "",
        "## Diagnostics",
        "",
    ]
    if candidate.diagnostics:
        for item in candidate.diagnostics:
            path = f" `{item.path}`" if item.path else ""
            value = f" value=`{item.value}`" if item.value is not None else ""
            lines.append(
                f"- [{item.severity.upper()}] `{item.rule_id}`{path}{value}: {item.message}"
            )
    else:
        lines.append("- No diagnostics.")

    lines.extend(["", "## Unknown Fields", ""])
    lines.extend(f"- `{field}`" for field in candidate.unknown_fields)
    if not candidate.unknown_fields:
        lines.append("- None.")

    lines.extend(["", "## Evidence", ""])
    lines.extend(f"- {item}" for item in candidate.evidence)
    if not candidate.evidence:
        lines.append("- None.")
    return "\n".join(lines) + "\n"
