from __future__ import annotations

from typing import TypeAlias

from .hwpx_structural_observation_models import DocumentObservation
from .hwpx_structural_observations import observe_hwpx_section


SectionSource: TypeAlias = tuple[str, str | bytes]


def observe_hwpx_document(
    sections: tuple[SectionSource, ...],
) -> tuple[DocumentObservation, ...]:
    return tuple(
        observe_hwpx_section(xml, section=name, section_ordinal=ordinal)
        for ordinal, (name, xml) in enumerate(sections)
    )
