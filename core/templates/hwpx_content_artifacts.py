from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .hwpx_content_classifier import COMMON_RULE_DESCRIPTIONS, COMMON_RULE_SET
from .hwpx_layout_context import LAYOUT_CONTRACT
from .hwpx_semantic_contract import (
    TAXONOMY_VERSION,
    SemanticNodeDecision,
    SemanticRegionAnnotation,
    decision_json,
    region_json,
)
from .hwpx_separation_rules import SeparationRules


def render_separation_review(
    template_id: str,
    section_results: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    rules: SeparationRules,
) -> str:
    lines = [
        "# Template Content Separation Review",
        "",
        f"- Template ID: `{template_id}`",
        "- Status: `candidate`",
        "- XML structure, style IDs, and table shapes are preserved.",
        "- Rendering removes `linesegarray` caches from changed sections so "
        "Hancom can recalculate text layout.",
        "- Rendering retains `linesegarray` caches in unchanged sections.",
        "- Non-table content and content nodes in multi-text-node table cells use "
        "`<hp:t>` placeholders; single-text-node content table cells use mapped "
        "cell coordinates.",
        f"- Layout contract: `{LAYOUT_CONTRACT}`. Every placeholder records the "
        "source layout it must keep, and rendering re-checks it.",
        f"- Common classification rule set: `{COMMON_RULE_SET}`.",
        "- Common fixed roles: " + "; ".join(COMMON_RULE_DESCRIPTIONS) + ".",
        f"- Template-specific location rules applied: {len(rules.rules)}.",
        "",
        "## Sections",
        "",
    ]
    for section in section_results:
        lines.append(
            f"- `{section['section']}`: text_nodes={section['text_node_count']}, "
            f"placeholders={section['placeholder_count']}"
        )
    lines.extend(["", "## Placeholder Fields", ""])
    for entry in entries:
        location = []
        if entry.get("table") is not None:
            location.append(f"table={entry['table']}")
        if entry.get("row") is not None:
            location.append(f"row={entry['row']}")
        if entry.get("col") is not None:
            location.append(f"col={entry['col']}")
        suffix = f" ({', '.join(location)})" if location else ""
        lines.append(
            f"- `{entry['field_id']}` -> `{entry['placeholder']}` "
            f"[{entry['category']}; {entry.get('replacement_mode', 'hp_t_text')}]{suffix}"
        )
    lines.append("")
    return "\n".join(lines)


def update_template_content_separation(
    path: Path,
    content_sample: Path,
    placeholder_map: Path,
    review: Path,
    *,
    semantic_classification: Path | None = None,
) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    placeholder_data = json.loads(placeholder_map.read_text(encoding="utf-8"))
    template_sections = sorted(
        str(item.relative_to(path.parent)).replace("\\", "/")
        for item in (path.parent / "template").glob("section*.template.xml")
    )
    data["content_separation"] = {
        "status": "candidate",
        "content_sample": content_sample.name,
        "placeholder_map": placeholder_map.name,
        "review": review.name,
        "replacement_mode": placeholder_data["replacement_mode"],
        "classification_rule_set": placeholder_data["classification_rule_set"],
        "classification_rules": placeholder_data["classification_rules"],
        "template_rule_count": placeholder_data["template_rule_count"],
        "field_count": len(placeholder_data.get("fields", [])),
        "template_sections": template_sections,
    }
    if semantic_classification is not None:
        data["content_separation"]["semantic_status"] = "resolved"
        data["content_separation"]["semantic_classification"] = semantic_classification.name
    data.setdefault("rendering_rules", {})
    data["rendering_rules"]["self_contained_base"] = "source.hwpx"
    data["rendering_rules"]["replace_only_hp_t_text"] = (
        placeholder_data["replacement_mode"] == "hp_t_text_only"
    )
    data["rendering_rules"]["fill_mapped_table_cells"] = (
        placeholder_data["replacement_mode"] in {"mixed", "table_cell_only"}
    )
    data["rendering_rules"]["preserve_table_structure"] = True
    data["rendering_rules"]["preserve_linesegarray"] = False
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_semantic_classification(
    path: Path,
    *,
    source_sha256: str,
    decisions: tuple[SemanticNodeDecision, ...],
    regions: tuple[SemanticRegionAnnotation, ...] = (),
) -> None:
    """Write the canonical, path-independent semantic classification artifact.

    Identical ``source_sha256``/decisions/regions always produce identical bytes:
    no output-directory or invocation path is included.
    """
    ordered_decisions = sorted(
        decisions,
        key=lambda item: (item.location.section, item.location.text_node_index, item.decision_id),
    )
    ordered_regions = sorted(
        regions,
        key=lambda item: (
            item.section,
            item.start_text_node_index,
            item.end_text_node_index,
            item.annotation_id,
        ),
    )
    role_counts = Counter(item.role.value for item in decisions)
    reason_codes = sorted(
        {code for item in decisions for code in item.reason_codes}
        | {code for item in regions for code in item.reason_codes}
    )
    payload = {
        "taxonomy_version": TAXONOMY_VERSION,
        "source_sha256": source_sha256,
        "node_decisions": [decision_json(item) for item in ordered_decisions],
        "region_annotations": [region_json(item) for item in ordered_regions],
        "role_counts": dict(sorted(role_counts.items())),
        "unresolved_count": role_counts.get("ambiguous", 0),
        "reason_codes": reason_codes,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_ambiguous_review(template_id: str, unresolved: list[dict[str, Any]]) -> str:
    """Review artifact for a candidate that stopped before placeholder projection."""
    lines = [
        "# Template Content Separation Review",
        "",
        f"- Template ID: `{template_id}`",
        "- Status: `candidate`",
        "- Semantic status: `ambiguous` — no placeholder_map.json/content.sample.json "
        "was written; the document is not fully resolved.",
        f"- Unresolved decisions: {len(unresolved)}.",
        "",
        "## Unresolved Decisions",
        "",
    ]
    for item in unresolved:
        lines.append(
            f"- `{item['decision_id']}` — section={item['section']} "
            f"text_node_index={item['text_node_index']} table={item['table']} "
            f"row={item['row']} col={item['col']} reasons={list(item['reason_codes'])}"
        )
    lines.append("")
    return "\n".join(lines)


def mark_ambiguous_content_separation(
    path: Path,
    *,
    semantic_classification: Path,
    review: Path,
    unresolved_count: int,
) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["content_separation"] = {
        "status": "candidate",
        "semantic_status": "ambiguous",
        "semantic_classification": semantic_classification.name,
        "review": review.name,
        "unresolved_count": unresolved_count,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
