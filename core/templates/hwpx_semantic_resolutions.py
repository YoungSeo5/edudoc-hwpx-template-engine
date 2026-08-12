from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from .hwpx_semantic_contract import SemanticNodeDecision, SemanticRole, decision_json

# 이 모듈의 경계:
# 사람이 --rules 파일의 "resolutions" 배열로 특정 AMBIGUOUS decision을
# 확정한다. decision_id + source/text SHA-256을 모두 맞춰야 하고, 이미
# 해소된 decision을 다시 겨냥하거나 span이 바뀌었으면 거부한다. 이 모듈은
# classify_document_semantics의 결정론적 결과를 덮어쓰지 않고, AMBIGUOUS인
# 것만 교체한다.

_ROLE_MAP: Final = {
    "fixed": SemanticRole.FIXED,
    "content": SemanticRole.CONTENT,
    "marker_content": SemanticRole.MARKER_CONTENT,
}


class ResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DecisionResolution:
    decision_id: str
    source_sha256: str
    text_sha256: str
    role: Literal["fixed", "content", "marker_content"]
    marker_prefix_raw: str | None = None
    marker_suffix_raw: str | None = None


def load_resolutions(path: Path | str | None) -> tuple[DecisionResolution, ...]:
    if path is None:
        return ()
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ResolutionError(f"invalid rules in {source}: root must be an object")
    items = raw.get("resolutions", [])
    if not isinstance(items, list):
        raise ResolutionError(f"invalid rules in {source}: resolutions must be a list")
    resolutions = tuple(_parse_resolution(source, item) for item in items)
    seen: set[str] = set()
    for item in resolutions:
        if item.decision_id in seen:
            raise ResolutionError(
                f"invalid rules in {source}: conflicting resolutions for "
                f"decision_id {item.decision_id!r}"
            )
        seen.add(item.decision_id)
    return resolutions


def apply_resolutions(
    decisions: tuple[SemanticNodeDecision, ...],
    resolutions: tuple[DecisionResolution, ...],
) -> tuple[SemanticNodeDecision, ...]:
    if not resolutions:
        return decisions
    ambiguous_by_id = {
        item.decision_id: item for item in decisions if item.role is SemanticRole.AMBIGUOUS
    }
    by_id = {item.decision_id: item for item in decisions}
    resolved_ids: set[str] = set()
    result = list(decisions)
    for resolution in resolutions:
        target = ambiguous_by_id.get(resolution.decision_id)
        if target is None:
            if resolution.decision_id in by_id:
                raise ResolutionError(
                    f"resolution targets decision_id {resolution.decision_id!r}, "
                    "which is not (or no longer) AMBIGUOUS"
                )
            raise ResolutionError(
                f"resolution targets unknown decision_id {resolution.decision_id!r}"
            )
        if resolution.source_sha256 != target.source_sha256 or (
            resolution.text_sha256 != target.text_sha256
        ):
            raise ResolutionError(
                f"resolution for decision_id {resolution.decision_id!r} does not match "
                "the current source/text identity"
            )
        role = _ROLE_MAP[resolution.role]
        span = None
        if role is SemanticRole.MARKER_CONTENT:
            span = target.span
            if span is None:
                raise ResolutionError(
                    f"resolution for decision_id {resolution.decision_id!r} chose "
                    "marker_content, but the decision has no lossless span candidate"
                )
            if (
                resolution.marker_prefix_raw != span.marker_prefix_raw
                or resolution.marker_suffix_raw != span.marker_suffix_raw
            ):
                raise ResolutionError(
                    f"resolution for decision_id {resolution.decision_id!r} has a stale "
                    "marker span; re-run classification and regenerate the resolution"
                )
        resolved = SemanticNodeDecision(
            role=role,
            source_sha256=target.source_sha256,
            text_sha256=target.text_sha256,
            location=target.location,
            reason_codes=(*target.reason_codes, "human_resolution_applied"),
            evidence=(*target.evidence, f"resolution:{resolution.decision_id}"),
            span=span,
        )
        result[result.index(target)] = resolved
        resolved_ids.add(resolution.decision_id)
    return tuple(result)


def unresolved_skeleton(decisions: tuple[SemanticNodeDecision, ...]) -> list[dict]:
    """A machine-generated skeleton a human fills in as ``resolutions`` entries.

    Role and marker prefix/suffix are intentionally left unset for the human to
    decide; only identity guards, location, and evidence are pre-filled.
    """
    return [
        {
            "decision_id": item.decision_id,
            "source_sha256": item.source_sha256,
            "text_sha256": item.text_sha256,
            "role": None,
            "marker_prefix_raw": None,
            "marker_suffix_raw": None,
            "decision": decision_json(item),
        }
        for item in decisions
        if item.role is SemanticRole.AMBIGUOUS
    ]


def _parse_resolution(path: Path, item: object) -> DecisionResolution:
    if not isinstance(item, dict):
        raise ResolutionError(f"invalid rules in {path}: each resolution must be an object")
    decision_id = item.get("decision_id")
    source_sha256 = item.get("source_sha256")
    text_sha256 = item.get("text_sha256")
    role = item.get("role")
    if not isinstance(decision_id, str) or not decision_id:
        raise ResolutionError(f"invalid rules in {path}: resolution requires decision_id")
    if not isinstance(source_sha256, str) or not source_sha256:
        raise ResolutionError(
            f"invalid rules in {path}: resolution requires source_sha256 identity guard"
        )
    if not isinstance(text_sha256, str) or not text_sha256:
        raise ResolutionError(
            f"invalid rules in {path}: resolution requires text_sha256 identity guard"
        )
    if role not in _ROLE_MAP:
        raise ResolutionError(
            f"invalid rules in {path}: resolution role must be fixed, content, or marker_content"
        )
    marker_prefix_raw = item.get("marker_prefix_raw")
    marker_suffix_raw = item.get("marker_suffix_raw")
    if role == "marker_content" and (
        not isinstance(marker_prefix_raw, str) or not isinstance(marker_suffix_raw, str)
    ):
        raise ResolutionError(
            f"invalid rules in {path}: marker_content resolution requires exact "
            "marker_prefix_raw and marker_suffix_raw"
        )
    return DecisionResolution(
        decision_id=decision_id,
        source_sha256=source_sha256,
        text_sha256=text_sha256,
        role=role,
        marker_prefix_raw=marker_prefix_raw,
        marker_suffix_raw=marker_suffix_raw,
    )
