from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from html import unescape
from typing import Final, Literal, TypeAlias, assert_never

from .hwpx_separation_rules import TextLocation


TAXONOMY_VERSION: Final = "semantic-v1"
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")

JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
RawOffsets: TypeAlias = tuple[int, int]


class SemanticContractError(ValueError):
    pass


class SemanticRole(StrEnum):
    FIXED = "fixed"
    CONTENT = "content"
    MARKER_CONTENT = "marker_content"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class LosslessTextSpan:
    raw_body: str
    layout_prefix_raw: str
    marker_prefix_raw: str
    content_raw: str
    marker_suffix_raw: str
    content_decoded: str
    layout_prefix_offsets: RawOffsets
    marker_prefix_offsets: RawOffsets
    content_offsets: RawOffsets
    marker_suffix_offsets: RawOffsets

    def __post_init__(self) -> None:
        parts = (
            self.layout_prefix_raw,
            self.marker_prefix_raw,
            self.content_raw,
            self.marker_suffix_raw,
        )
        offsets = (
            self.layout_prefix_offsets,
            self.marker_prefix_offsets,
            self.content_offsets,
            self.marker_suffix_offsets,
        )
        cursor = 0
        for part, (start, end) in zip(parts, offsets, strict=True):
            if start != cursor or end < start or self.raw_body[start:end] != part:
                detail = "offsets do not identify the recorded raw parts"
                raise SemanticContractError(f"invalid lossless text span: {detail}")
            cursor = end
        if cursor != len(self.raw_body) or self.reconstruct_raw_body() != self.raw_body:
            detail = "raw parts do not reconstruct the original body"
            raise SemanticContractError(f"invalid lossless text span: {detail}")
        if unescape(self.content_raw) != self.content_decoded:
            detail = "decoded content does not match the raw content"
            raise SemanticContractError(f"invalid lossless text span: {detail}")

    def reconstruct_raw_body(self) -> str:
        return "".join(
            (
                self.layout_prefix_raw,
                self.marker_prefix_raw,
                self.content_raw,
                self.marker_suffix_raw,
            )
        )


@dataclass(frozen=True, slots=True)
class SemanticNodeDecision:
    role: SemanticRole
    source_sha256: str
    text_sha256: str
    location: TextLocation
    reason_codes: tuple[str, ...]
    evidence: tuple[str, ...]
    span: LosslessTextSpan | None = None
    scope: Literal["text_node"] = field(default="text_node", init=False)
    decision_id: str = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.source_sha256, "source_sha256")
        _require_sha256(self.text_sha256, "text_sha256")
        if not self.reason_codes or not self.evidence:
            detail = "reason_codes and evidence must be non-empty"
            raise SemanticContractError(f"invalid semantic node decision: {detail}")
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        object.__setattr__(self, "evidence", tuple(sorted(set(self.evidence))))
        identity = _canonical_bytes(
            {
                "location": _location_json(self.location),
                "scope": self.scope,
                "source_sha256": self.source_sha256,
                "taxonomy_version": TAXONOMY_VERSION,
                "text_sha256": self.text_sha256,
            }
        )
        object.__setattr__(self, "decision_id", f"semantic-v1:text_node:{sha256(identity).hexdigest()}")

    @property
    def placeholder_eligible(self) -> bool:
        match self.role:
            case SemanticRole.CONTENT | SemanticRole.MARKER_CONTENT:
                return True
            case SemanticRole.FIXED | SemanticRole.AMBIGUOUS:
                return False
            case unreachable:
                assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class SemanticRegionAnnotation:
    source_sha256: str
    section: str
    start_text_node_index: int
    end_text_node_index: int
    declaration_source: str
    reason_codes: tuple[str, ...]
    evidence: tuple[str, ...]
    scope: Literal["region"] = field(default="region", init=False)
    role: Literal["repeat_group"] = field(default="repeat_group", init=False)
    annotation_id: str = field(init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.source_sha256, "source_sha256")
        if not self.section or self.start_text_node_index < 0:
            detail = "section and non-negative range are required"
            raise SemanticContractError(f"invalid semantic region annotation: {detail}")
        if self.end_text_node_index < self.start_text_node_index:
            detail = "range end must not precede range start"
            raise SemanticContractError(f"invalid semantic region annotation: {detail}")
        if not self.declaration_source.strip():
            detail = "a human declaration source is required"
            raise SemanticContractError(f"invalid semantic region annotation: {detail}")
        if not self.reason_codes or not self.evidence:
            detail = "reason_codes and evidence must be non-empty"
            raise SemanticContractError(f"invalid semantic region annotation: {detail}")
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        object.__setattr__(self, "evidence", tuple(sorted(set(self.evidence))))
        identity = _canonical_bytes(
            {
                "declaration_source": self.declaration_source,
                "end_text_node_index": self.end_text_node_index,
                "role": self.role,
                "scope": self.scope,
                "section": self.section,
                "source_sha256": self.source_sha256,
                "start_text_node_index": self.start_text_node_index,
                "taxonomy_version": TAXONOMY_VERSION,
            }
        )
        object.__setattr__(self, "annotation_id", f"semantic-v1:region:{sha256(identity).hexdigest()}")


@dataclass(frozen=True, slots=True)
class SemanticReport:
    source_sha256: str
    decisions: tuple[SemanticNodeDecision, ...]
    regions: tuple[SemanticRegionAnnotation, ...]
    taxonomy_version: Literal["semantic-v1"] = field(default="semantic-v1", init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.source_sha256, "source_sha256")
        if any(item.source_sha256 != self.source_sha256 for item in self.decisions):
            detail = "node decision source identity does not match the report"
            raise SemanticContractError(f"invalid semantic report: {detail}")
        if any(item.source_sha256 != self.source_sha256 for item in self.regions):
            detail = "region annotation source identity does not match the report"
            raise SemanticContractError(f"invalid semantic report: {detail}")

    def canonical_json_bytes(self) -> bytes:
        decisions = sorted(
            self.decisions,
            key=lambda item: (
                item.location.section,
                item.location.text_node_index,
                item.decision_id,
            ),
        )
        regions = sorted(
            self.regions,
            key=lambda item: (
                item.section,
                item.start_text_node_index,
                item.end_text_node_index,
                item.annotation_id,
            ),
        )
        return _canonical_bytes(
            {
                "decisions": [_decision_json(item) for item in decisions],
                "regions": [_region_json(item) for item in regions],
                "source_sha256": self.source_sha256,
                "taxonomy_version": self.taxonomy_version,
            }
        )


def _require_sha256(value: str, name: str) -> None:
    if _SHA256_RE.fullmatch(value) is None:
        raise SemanticContractError(f"{name} must be a lowercase SHA-256 digest")


def _canonical_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _location_json(location: TextLocation) -> dict[str, JsonValue]:
    return {
        "col": location.col,
        "paragraph_index": location.paragraph_index,
        "row": location.row,
        "section": location.section,
        "table": location.table,
        "text_node_index": location.text_node_index,
    }


def _span_json(span: LosslessTextSpan | None) -> JsonValue:
    if span is None:
        return None
    return {
        "content_decoded": span.content_decoded,
        "content_offsets": list(span.content_offsets),
        "content_raw": span.content_raw,
        "layout_prefix_offsets": list(span.layout_prefix_offsets),
        "layout_prefix_raw": span.layout_prefix_raw,
        "marker_prefix_offsets": list(span.marker_prefix_offsets),
        "marker_prefix_raw": span.marker_prefix_raw,
        "marker_suffix_offsets": list(span.marker_suffix_offsets),
        "marker_suffix_raw": span.marker_suffix_raw,
        "raw_body": span.raw_body,
    }


def _decision_json(item: SemanticNodeDecision) -> dict[str, JsonValue]:
    return {
        "decision_id": item.decision_id,
        "evidence": list(item.evidence),
        "location": _location_json(item.location),
        "placeholder_eligible": item.placeholder_eligible,
        "reason_codes": list(item.reason_codes),
        "role": item.role.value,
        "scope": item.scope,
        "source_sha256": item.source_sha256,
        "span": _span_json(item.span),
        "text_sha256": item.text_sha256,
    }


def decision_json(item: SemanticNodeDecision) -> dict[str, JsonValue]:
    """Public JSON shape for one node decision, reused by artifact writers."""
    return _decision_json(item)


def region_json(item: SemanticRegionAnnotation) -> dict[str, JsonValue]:
    """Public JSON shape for one region annotation, reused by artifact writers."""
    return _region_json(item)


def _region_json(item: SemanticRegionAnnotation) -> dict[str, JsonValue]:
    return {
        "annotation_id": item.annotation_id,
        "declaration_source": item.declaration_source,
        "end_text_node_index": item.end_text_node_index,
        "evidence": list(item.evidence),
        "reason_codes": list(item.reason_codes),
        "role": item.role,
        "scope": item.scope,
        "section": item.section,
        "source_sha256": item.source_sha256,
        "start_text_node_index": item.start_text_node_index,
    }
