"""Institution-template extraction and approved-template loading."""

from .models import (
    ExtractedStyleProfile,
    RendererContract,
    TemplateCandidate,
    TemplateDiagnostic,
    TemplateIdentity,
)
from .hwpx_package_extractor import HwpxExtractionResult, extract_hwpx_template
from .registry import TemplateRegistry

__all__ = [
    "ExtractedStyleProfile",
    "HwpxExtractionResult",
    "RendererContract",
    "TemplateCandidate",
    "TemplateDiagnostic",
    "TemplateIdentity",
    "TemplateRegistry",
    "extract_hwpx_template",
]
