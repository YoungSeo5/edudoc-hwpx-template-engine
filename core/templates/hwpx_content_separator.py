from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..adapters.hwpx_template_renderer import snapshot_source_hwpx
from .hwpx_content_artifacts import (
    mark_ambiguous_content_separation,
    render_ambiguous_review,
    render_separation_review,
    update_template_content_separation,
    write_semantic_classification,
)
from .hwpx_content_classifier import (
    COMMON_RULE_DESCRIPTIONS,
    COMMON_RULE_SET,
    build_text_contexts,
    classify_text,
    content_category,
)
from .hwpx_layout_context import (
    LAYOUT_CONTEXT_KEY,
    LAYOUT_CONTRACT,
    STYLE_MARGIN_KEY,
    DocumentLayout,
    paragraph_anchor,
    verify_recorded_layout,
)
from .hwpx_package_extractor import HwpxExtractionResult, extract_hwpx_template
from .hwpx_semantic_classifier import SemanticAmbiguityError, classify_document_semantics
from .hwpx_semantic_contract import SemanticNodeDecision, SemanticRole
from .hwpx_semantic_placeholder_projection import (
    patch_marker_content_span,
    require_fully_resolved,
)
from .hwpx_semantic_resolutions import apply_resolutions, load_resolutions, unresolved_skeleton
from .hwpx_separation_rules import (
    SeparationRules,
    TextRole,
    load_separation_rules,
)

# 이 모듈의 경계:
# hwpx_package_extractor가 만든 candidate 폴더
# → 각 <hp:t>를 고정 구조 또는 교체 콘텐츠로 분류
# → template XML, content.sample.json, placeholder_map.json, 검토 보고서 생성
# 승인 여부는 바꾸지 않으며, 결과는 계속 candidate 상태다.

_T_NODE_RE = re.compile(
    r"(<(?P<self_prefix>[A-Za-z_][\w.-]*:)?t\b(?P<self_attrs>[^>]*)/>)"
    r"|(<(?P<open_prefix>[A-Za-z_][\w.-]*:)?t\b(?P<attrs>[^>]*)>)"
    r"(?P<body>.*?)"
    r"(</(?P=open_prefix)?t>)",
    re.S,
)
_LEADING_FWSPACE_RE = re.compile(
    r"^(?P<prefix>(?:(?:\s*<(?:[A-Za-z_][\w.-]*:)?fwSpace\b[^>]*/>)| )+)"
)
_TRAILING_FWSPACE_RE = re.compile(
    r"(?P<suffix>(?:<(?:[A-Za-z_][\w.-]*:)?fwSpace\b[^>]*/>\s*)+)$"
)


@dataclass(frozen=True, slots=True)
class HwpxContentSeparationResult:
    output_dir: Path
    extraction: HwpxExtractionResult
    content_sample: Path
    placeholder_map: Path
    review: Path


def separate_hwpx_template_content(
    source: Path | str,
    output_dir: Path | str,
    *,
    template_id: str,
    template_name: str | None = None,
    institution: str = "확인 필요",
    rules_path: Path | str | None = None,
) -> HwpxContentSeparationResult:
    # 흐름 1: 공통 분류 규칙과 기관별 추가 규칙을 먼저 읽는다.
    rules = load_separation_rules(rules_path)

    # 흐름 2: 원본 HWPX에서 raw/와 template/ 작업본 및 candidate
    # template.json을 만든다. 이 함수가 패키지 추출 단계를 내부 호출한다.
    extraction = extract_hwpx_template(
        source,
        output_dir,
        template_id=template_id,
        template_name=template_name,
        institution=institution,
    )
    root = Path(output_dir)

    # 흐름 3: raw/만으로는 완전한 HWPX 패키지를 재구성할 수 없으므로,
    # 렌더러가 사용할 원본 전체 패키지를 source.hwpx로 보존한다.
    # raw/에는 분석 대상으로 선택한 일부 자산만 들어있고, hwpx 패키지에 필요한 추출되지 않은 기타 자산은 source.hwpx에서 가져와야 한다.

    snapshot_source_hwpx(source, root)

    # 흐름 3.5: XML을 패치하기 전에 문서 전체를 의미 분류로 먼저 판정하고,
    # --rules의 "resolutions"로 넘어온 사람의 결정을 적용한다. semantic
    # 분류 결과는 성공/실패 모두 semantic_classification.json에 남긴다.
    # 그래도 AMBIGUOUS가 남으면 raw/와 (추출기가 만든 미패치) template/
    # 복사본, template.review.md, semantic_classification.json만 남기고
    # placeholder_map.json/content.sample.json/roundtrip 생성 전에 실패로
    # 멈춘다.
    source_sha256 = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    resolutions = load_resolutions(rules_path)
    decisions_by_section = _classify_and_resolve_document(root, rules, resolutions)
    all_decisions = tuple(
        decision
        for section_decisions in decisions_by_section.values()
        for decision in section_decisions
    )
    semantic_classification = root / "semantic_classification.json"
    write_semantic_classification(
        semantic_classification, source_sha256=source_sha256, decisions=all_decisions
    )
    _reject_if_semantically_unresolved(
        root, template_id, all_decisions, semantic_classification
    )

    section_results = []
    fields: dict[str, Any] = {}
    placeholder_entries = []
    section_paragraph_counts: dict[str, int] = {}
    style_margins: dict[str, Any] = {}

    # 흐름 4: 모든 section의 <hp:t>를 문서 순서대로 분류한다.
    # counters를 section 밖에 두어 여러 section에서도 field_id가 중복되지 않는다.
    field_id_counters: dict[str, int] = {}
    for section_index, raw_section in enumerate(
        sorted((root / "raw").glob("section*.xml"), key=_section_sort_key)
    ):
        decisions, table_fields = _section_decisions(
            raw_section,
            rules,
            field_id_counters,
            section_index,
            decisions_by_section.get(raw_section.name, ()),
        )

        # CONTENT로 판정한 텍스트만 {{field_id}}로 바꾸고, FIXED 텍스트와
        # XML 구조·스타일 ID는 원문 그대로 유지한다.
        template_xml, applied = _apply_decisions(raw_section.read_text(encoding="utf-8"), decisions)
        applied.extend(table_fields)
        template_section = root / "template" / raw_section.name.replace(".xml", ".template.xml")
        template_section.write_text(template_xml, encoding="utf-8")
        section_paragraph_counts[raw_section.name] = _paragraph_count(template_xml)
        section_results.append(
            {
                "section": raw_section.name,
                "text_node_count": len(decisions),
                "placeholder_count": len(applied),
            }
        )
        # placeholder가 원본에서 물려받은 서식을 그대로 기록한다. 어떤 서식이
        # 계약에 들어가는지는 DocumentLayout.context_for 한 곳이 정한다.
        layout = DocumentLayout.read(
            raw_section.read_bytes(),
            (root / "raw" / "header.xml").read_bytes(),
        )
        for item in applied:
            item[LAYOUT_CONTEXT_KEY] = layout.context_for(item)
            fields[item["field_id"]] = item["sample_value"]
            placeholder_entries.append(item)
        # 스타일 정의는 여러 placeholder가 공유하므로 문서 단위로 한 번만 기록한다.
        style_margins.update(layout.margins_of_referenced_styles(applied))

    # 흐름 5: 같은 분리 결과를 세 관점으로 저장한다.
    # content.sample.json은 원본 예시 값, placeholder_map.json은 위치 계약,
    # template.review.md는 사람이 승인 전에 읽는 검토 자료다.
    content_sample = root / "content.sample.json"
    placeholder_map = root / "placeholder_map.json"
    review = root / "template.review.md"
    content_sample.write_text(
        json.dumps(
            {
                "template_id": template_id,
                "source_file": Path(source).name,
                "fields": fields,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    placeholder_map.write_text(
        json.dumps(
            {
                "template_id": template_id,
                "replacement_mode": _replacement_mode(placeholder_entries),
                "layout_contract": LAYOUT_CONTRACT,
                "classification_rule_set": COMMON_RULE_SET,
                "classification_rules": list(COMMON_RULE_DESCRIPTIONS),
                "template_rule_count": len(rules.rules),
                "section_paragraph_counts": section_paragraph_counts,
                STYLE_MARGIN_KEY: style_margins,
                "fields": placeholder_entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _validate_placeholder_paragraph_contract(root)
    review.write_text(
        render_separation_review(template_id, section_results, placeholder_entries, rules),
        encoding="utf-8",
    )

    # 흐름 6: 생성한 산출물의 상대 경로와 분리 상태를 candidate
    # template.json에 연결한다. status 자체를 approved로 바꾸지는 않는다.
    update_template_content_separation(
        root / "template.json",
        content_sample,
        placeholder_map,
        review,
        semantic_classification=semantic_classification,
    )
    return HwpxContentSeparationResult(
        output_dir=root,
        extraction=extraction,
        content_sample=content_sample,
        placeholder_map=placeholder_map,
        review=review,
    )


# 한 section을 읽어 각 텍스트 노드에 "유지/교체" 결정을 붙인다.
# 이 단계는 아직 XML을 변경하지 않고 결정 목록만 만든다.
def _section_decisions(
    path: Path,
    rules: SeparationRules,
    counters: dict[str, int],
    section_index: int,
    semantic_decisions: tuple[SemanticNodeDecision, ...] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.fromstring(path.read_bytes())
    decisions = []
    contexts = build_text_contexts(root, path.name)
    semantic_by_index = {item.location.text_node_index: item for item in semantic_decisions}
    table_contexts: dict[tuple[int, int, int], list[Any]] = defaultdict(list)
    for context in contexts:
        location = context.location
        if (
            location.table is not None
            and location.row is not None
            and location.col is not None
        ):
            table_contexts[(location.table, location.row, location.col)].append(context)

    table_fields = []
    seen_table_cells: set[tuple[int, int, int]] = set()
    for context in contexts:
        category = content_category(context.normalized_text)
        role = classify_text(context, rules)
        candidate_field_id = None
        is_table_text = context.location.table is not None
        table_key = (
            context.location.table,
            context.location.row,
            context.location.col,
        )
        cell_is_multi_node = (
            is_table_text
            and None not in table_key
            and sum(1 for item in table_contexts[table_key] if item.normalized_text) >= 2
        )
        # 사람이 --rules resolutions로 MARKER_CONTENT를 확정한 노드는 표 안에
        # 있어도 same-node lossless span 치환 대상이다. 일반 table_cell field
        # 생성 경로로 보내면 표식(prefix/suffix)이 스킬 채움 단계에서 사라진다.
        semantic = semantic_by_index.get(context.location.text_node_index)
        is_marker_content_node = (
            semantic is not None and semantic.role is SemanticRole.MARKER_CONTENT
        )
        is_semantic_fixed = semantic is not None and semantic.role is SemanticRole.FIXED
        if (
            is_table_text
            and not cell_is_multi_node
            and not is_marker_content_node
            and None not in table_key
            and table_key not in seen_table_cells
        ):
            seen_table_cells.add(table_key)
            table, row, col = table_key
            cell_contexts = table_contexts[(table, row, col)]
            sample_value = _table_cell_sample_value(cell_contexts)
            if sample_value and _table_cell_is_content(cell_contexts, rules):
                category = content_category(sample_value)
                counters[category] = counters.get(category, 0) + 1
                field_id = rules.field_id_for(cell_contexts[0].location) or f"{category}_{counters[category]:02d}"
                table_fields.append(
                    {
                        "field_id": field_id,
                        "placeholder": f"{{{{{field_id}}}}}",
                        "sample_value": sample_value,
                        "category": category,
                        "replacement_mode": "table_cell",
                        "section": path.name,
                        "section_index": section_index,
                        "text_node_index": cell_contexts[0].location.text_node_index,
                        "table": table,
                        "row": row,
                        "col": col,
                        "paragraph_index": cell_contexts[0].location.paragraph_index,
                        **_semantic_tags(
                            semantic_by_index.get(cell_contexts[0].location.text_node_index)
                        ),
                    }
                )
        node_level = not is_table_text or cell_is_multi_node or is_marker_content_node
        # 사람이 --rules resolutions로 MARKER_CONTENT를 확정한 노드만 same-node
        # lossless span 치환 대상이다. 그 외에는 기존 whole-node CONTENT 경로다.
        is_marker_content = node_level and is_marker_content_node
        if is_marker_content:
            category = content_category(semantic.span.content_decoded)
        if context.normalized_text and node_level:
            counters[category] = counters.get(category, 0) + 1
            candidate_field_id = rules.field_id_for(context.location) or f"{category}_{counters[category]:02d}"
        replace = (
            bool(context.normalized_text)
            and node_level
            and not is_semantic_fixed
            and (role is TextRole.CONTENT or is_marker_content)
        )
        field_id = candidate_field_id if replace else None
        location = context.location
        decisions.append(
            {
                "text_node_index": location.text_node_index,
                "original_text": context.original_text,
                "normalized_text": context.normalized_text,
                "replace": replace,
                "category": category,
                "role": role.value,
                "field_id": field_id,
                "placeholder": f"{{{{{field_id}}}}}" if field_id else None,
                "location": {
                    "section": location.section,
                    "table": location.table,
                    "row": location.row,
                    "col": location.col,
                    "paragraph_index": location.paragraph_index,
                },
                "marker_content_decision": semantic if is_marker_content else None,
                **_semantic_tags(semantic),
            }
        )

    return decisions, table_fields


def _semantic_tags(semantic: SemanticNodeDecision | None) -> dict[str, Any]:
    return {
        "semantic_role": semantic.role.value if semantic else None,
        "semantic_decision_id": semantic.decision_id if semantic else None,
    }


# 결정 목록을 원본 XML 문자열의 <hp:t> 순서와 맞춰 적용한다.
# XML 파서를 통한 재직렬화를 피하므로 템플릿의 나머지 바이트 구조는 유지된다.
def _apply_decisions(xml: str, decisions: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    parts = []
    cursor = 0
    text_index = 0
    applied = []
    for match in _T_NODE_RE.finditer(xml):
        parts.append(xml[cursor:match.start()])
        decision = decisions[text_index] if text_index < len(decisions) else None
        if match.group(1):
            parts.append(match.group(1))
        elif decision and decision["replace"] and decision.get("marker_content_decision"):
            # 사람이 확정한 MARKER_CONTENT: 표식은 그대로 두고 content span만
            # placeholder로 바꾸는 lossless 패처를 쓴다.
            semantic_decision = decision["marker_content_decision"]
            patched_body = patch_marker_content_span(
                match.group("body") or "", semantic_decision, decision["placeholder"]
            )
            parts.append(match.group(4))
            parts.append(patched_body)
            parts.append(match.group(8))
            applied.append(
                {
                    "field_id": decision["field_id"],
                    "placeholder": decision["placeholder"],
                    "sample_value": semantic_decision.span.content_decoded,
                    "category": decision["category"],
                    "replacement_mode": "hp_t_text_marker_span",
                    "section": decision["location"]["section"],
                    "text_node_index": decision["text_node_index"],
                    "table": decision["location"].get("table"),
                    "row": decision["location"].get("row"),
                    "col": decision["location"].get("col"),
                    "paragraph_index": decision["location"].get("paragraph_index"),
                    "semantic_role": decision["semantic_role"],
                    "semantic_decision_id": decision["semantic_decision_id"],
                }
            )
        elif decision and decision["replace"]:
            placeholder = html.escape(decision["placeholder"], quote=False)
            leading, trailing = _edge_fwspace_xml(match.group("body") or "")
            parts.append(match.group(4))
            parts.append(leading)
            parts.append(placeholder)
            parts.append(trailing)
            parts.append(match.group(8))
            applied.append(
                {
                    "field_id": decision["field_id"],
                    "placeholder": decision["placeholder"],
                    "sample_value": decision["original_text"],
                    "category": decision["category"],
                    "replacement_mode": "hp_t_text",
                    "section": decision["location"]["section"],
                    "text_node_index": decision["text_node_index"],
                    "table": decision["location"].get("table"),
                    "row": decision["location"].get("row"),
                    "col": decision["location"].get("col"),
                    "paragraph_index": decision["location"].get("paragraph_index"),
                    "semantic_role": decision["semantic_role"],
                    "semantic_decision_id": decision["semantic_decision_id"],
                }
            )
        else:
            parts.append(match.group(0))
        cursor = match.end()
        text_index += 1
    parts.append(xml[cursor:])
    return "".join(parts), applied


def _edge_fwspace_xml(body: str) -> tuple[str, str]:
    leading_match = _LEADING_FWSPACE_RE.match(body)
    trailing_match = _TRAILING_FWSPACE_RE.search(body)
    return (
        leading_match.group("prefix") if leading_match else "",
        trailing_match.group("suffix") if trailing_match else "",
    )


def _table_cell_is_content(
    contexts: list[Any],
    rules: SeparationRules,
) -> bool:
    configured = [
        rules.role_for(context.location)
        for context in contexts
        if rules.role_for(context.location) is not None
    ]
    if configured:
        return TextRole.CONTENT in configured

    first = contexts[0]
    row = first.location.row
    col = first.location.col
    rows, cols = first.table_rows or 0, first.table_cols or 0
    if row is None or col is None:
        return False
    if rows <= 1 or cols <= 1:
        return any(classify_text(context, rules) is TextRole.CONTENT for context in contexts)
    if row == 0:
        return _looks_like_table_header_value(_table_cell_sample_value(contexts))
    return col > 0


def _table_cell_sample_value(contexts: list[Any]) -> str:
    return " ".join(
        context.normalized_text
        for context in contexts
        if context.normalized_text
    )


def _looks_like_table_header_value(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:\d{1,2}/)?\d{1,2}\s*\([월화수목금토일]\)",
            value,
        )
    )


def _replacement_mode(entries: list[dict[str, Any]]) -> str:
    modes = {entry.get("replacement_mode", "hp_t_text") for entry in entries}
    if not modes or modes == {"hp_t_text"}:
        return "hp_t_text_only"
    if modes == {"table_cell"}:
        return "table_cell_only"
    return "mixed"


def _validate_placeholder_paragraph_contract(template_dir: Path) -> None:
    """기록한 layout context가 원본과 템플릿 양쪽에서 모두 성립하는지 확인한다."""
    mapping = json.loads(
        (template_dir / "placeholder_map.json").read_text(encoding="utf-8")
    )
    for label, directory, suffix in (
        ("raw", template_dir / "raw", ".xml"),
        ("template", template_dir / "template", ".template.xml"),
    ):
        verify_recorded_layout(
            mapping,
            lambda section, d=directory, s=suffix: (
                d / section.replace(".xml", s)
            ).read_bytes(),
            (directory / "header.xml").read_bytes(),
            where=f"separated {label}",
        )
    _validate_placeholder_stays_in_its_paragraph(template_dir, mapping)


def _validate_placeholder_stays_in_its_paragraph(
    template_dir: Path,
    mapping: dict[str, Any],
) -> None:
    for section in mapping["section_paragraph_counts"]:
        paragraphs = _paragraphs(
            (
                template_dir / "template" / section.replace(".xml", ".template.xml")
            ).read_text(encoding="utf-8")
        )
        for field in mapping["fields"]:
            if (
                field["section"] != section
                or field.get("replacement_mode") == "table_cell"
            ):
                continue
            paragraph = paragraphs[paragraph_anchor(field)]
            if field["placeholder"] not in "".join(paragraph.itertext()):
                raise ValueError(
                    f"placeholder moved from paragraph for {field['field_id']}"
                )


def _paragraph_count(xml: str) -> int:
    return len(_paragraphs(xml))


def _paragraphs(xml: str) -> list[ET.Element]:
    return [node for node in ET.fromstring(xml).iter() if node.tag.rsplit("}", 1)[-1] == "p"]


def _classify_and_resolve_document(
    root: Path,
    rules: SeparationRules,
    resolutions: tuple[Any, ...],
) -> dict[str, tuple[SemanticNodeDecision, ...]]:
    result: dict[str, tuple[SemanticNodeDecision, ...]] = {}
    for raw_section in sorted((root / "raw").glob("section*.xml"), key=_section_sort_key):
        section_root = ET.fromstring(raw_section.read_bytes())
        decisions = classify_document_semantics(section_root, raw_section.name, rules)
        result[raw_section.name] = apply_resolutions(decisions, resolutions)
    return result


def _reject_if_semantically_unresolved(
    root: Path,
    template_id: str,
    decisions: tuple[SemanticNodeDecision, ...],
    semantic_classification: Path,
) -> None:
    unresolved = [item for item in decisions if item.role is SemanticRole.AMBIGUOUS]
    if not unresolved:
        return
    unresolved_report = [
        {
            "decision_id": item.decision_id,
            "section": item.location.section,
            "text_node_index": item.location.text_node_index,
            "table": item.location.table,
            "row": item.location.row,
            "col": item.location.col,
            "reason_codes": item.reason_codes,
        }
        for item in unresolved
    ]
    review = root / "template.review.md"
    review.write_text(
        render_ambiguous_review(template_id, unresolved_report), encoding="utf-8"
    )
    mark_ambiguous_content_separation(
        root / "template.json",
        semantic_classification=semantic_classification,
        review=review,
        unresolved_count=len(unresolved),
    )
    try:
        require_fully_resolved(decisions)
    except SemanticAmbiguityError as exc:
        exc.unresolved = unresolved_report
        exc.resolution_skeleton = unresolved_skeleton(decisions)
        exc.semantic_classification_path = str(semantic_classification)
        raise


def _section_sort_key(path: Path) -> int:
    match = re.search(r"section(\d+)", path.name)
    return int(match.group(1)) if match else 10**9
