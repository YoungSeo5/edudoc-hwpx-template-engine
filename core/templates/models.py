"""Data contracts for deterministic institution-template extraction."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ExtractedStyleProfile:
    """Style values pulled from a reference document — extracted, never defaulted.

    A field stays ``None`` when the reference does not provide it. A renderer must
    fall back explicitly (and record that it did) rather than treat ``None`` as a
    real institution value. ``confidence`` and ``evidence`` let downstream steps
    tell extracted truth apart from a guess.
    """

    source: str = "unknown"                    # extracted_from_hwpx | unknown
    font_family: str | None = None
    body_font_size_pt: float | None = None
    page_margins_mm: dict | None = None        # {top, bottom, left, right}
    line_spacing: str | None = None            # e.g. "160%"
    heading_styles: list[dict] = field(default_factory=list)
    table_style: dict | None = None
    confidence: str = "low"                    # high | medium | low
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RendererContract:
    """How a validated template may be rendered."""

    preferred_format: str = "hwpx"
    route: str | None = None
    reference_hwpx: str | None = None
    fallback: str = "md2hwpx"


@dataclass(frozen=True)
class TemplateIdentity:
    institution: str
    document_type: str
    extends: str | None = None
    template_id: str | None = None
    template_name: str | None = None


@dataclass(frozen=True)
class TemplateDiagnostic:
    rule_id: str
    severity: str
    message: str
    path: str | None = None
    action: str | None = None
    value: Any = None


@dataclass
class TemplateCandidate:
    """The only in-memory template candidate shape.

    Passing the automatic gate makes a candidate ``validated``. Only an explicit
    approval action may promote it to the official ``template.json`` artifact.
    """

    identity: TemplateIdentity
    reference_path: str
    reference_format: str
    schema_version: str = "1.0"
    structure: dict[str, Any] = field(default_factory=dict)
    writing_rules: dict[str, Any] = field(default_factory=dict)
    style_profile: ExtractedStyleProfile = field(default_factory=ExtractedStyleProfile)
    renderer: RendererContract = field(default_factory=RendererContract)
    source_summary: dict[str, Any] = field(default_factory=dict)
    assets: dict[str, Any] = field(default_factory=dict)
    package_summary: dict[str, Any] = field(default_factory=dict)
    rendering_rules: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)
    status: str = "candidate"
    refinement_passes: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["format"] = self.reference_format
        data["template_id"] = self.identity.template_id
        data["template_name"] = (
            self.identity.template_name or self.identity.document_type
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemplateCandidate":
        identity_data = dict(data.get("identity", {}))
        identity_data.setdefault("template_id", data.get("template_id"))
        identity_data.setdefault("template_name", data.get("template_name"))
        return cls(
            identity=TemplateIdentity(**identity_data),
            reference_path=data["reference_path"],
            reference_format=data.get("reference_format", data.get("format", "unknown")),
            schema_version=str(data.get("schema_version", "1.0")),
            structure=dict(data.get("structure", {})),
            writing_rules=dict(data.get("writing_rules", {})),
            style_profile=ExtractedStyleProfile(**data.get("style_profile", {})),
            renderer=RendererContract(**data.get("renderer", {})),
            source_summary=dict(data.get("source_summary", {})),
            assets=dict(data.get("assets", {})),
            package_summary=dict(data.get("package_summary", {})),
            rendering_rules=dict(data.get("rendering_rules", {})),
            evidence=list(data.get("evidence", [])),
            unknown_fields=list(data.get("unknown_fields", [])),
            diagnostics=[
                item if isinstance(item, TemplateDiagnostic) else TemplateDiagnostic(**item)
                for item in data.get("diagnostics", [])
            ],
            status=data.get("status", "candidate"),
            refinement_passes=int(data.get("refinement_passes", 0)),
        )
