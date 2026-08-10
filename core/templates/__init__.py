"""Institution-template extraction, quality control, and approved-template loading."""

from .models import (
    ExtractedStyleProfile,
    RendererContract,
    TemplateCandidate,
    TemplateDiagnostic,
    TemplateIdentity,
)
from .hwpx_package_extractor import HwpxExtractionResult, extract_hwpx_template
from .pipeline import build_candidate, run_template_pipeline
from .registry import TemplateRegistry

__all__ = [
    "ExtractedStyleProfile",
    "HwpxExtractionResult",
    "RendererContract",
    "TemplateCandidate",
    "TemplateDiagnostic",
    "TemplateIdentity",
    "TemplateRegistry",
    "build_candidate",
    "extract_hwpx_template",
    "run_template_pipeline",
]
