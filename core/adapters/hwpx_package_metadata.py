from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hwpx_template_input import ResolvedMetadata

PACKAGE_META_NAMES = (
    "creator",
    "subject",
    "description",
    "lastsaveby",
    "date",
    "keyword",
    "CreatedDate",
    "ModifiedDate",
)


@dataclass(frozen=True, slots=True)
class PackageMetadata:
    title: str
    creator: str
    subject: str
    description: str
    lastsaveby: str
    report_date: str
    keywords: str
    requested_at: datetime


def build_package_metadata(
    metadata: ResolvedMetadata,
    *,
    requester_name: str,
    requested_at: datetime,
) -> PackageMetadata:
    return PackageMetadata(
        title=metadata.title,
        creator=requester_name,
        subject=metadata.subject,
        description=metadata.description,
        lastsaveby=requester_name,
        report_date=metadata.report_date,
        keywords=metadata.keywords,
        requested_at=requested_at,
    )
