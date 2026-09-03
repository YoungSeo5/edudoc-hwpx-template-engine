"""Build a self-authored HWPX source document from a ``template_spec``.

이 모듈의 경계 (authoring-v2, section 기반):
template_spec(구조: ``sections[]`` + 조판 계약: ``page``/section별 style role
참조) -> (별도 모듈 ``core.adapters.hwpx_authoring_resolve``가 Institution
Design Contract와 병합해 만든) Resolved Authoring Contract ->
``hwpx`` 라이브러리를 직접 호출해 실제 source.hwpx 생성 -> 생성 시점에 각
section이 문서 어디에 놓였는지(문단 text_node_index 또는 표 index)를 그대로
재사용해 --rules 파일(hwpx_separation_rules.SeparationRules 계약)로
FIXED/CONTENT를 결정론적으로 선언한다. semantic classifier가 다시 추측하지
않는다.

**재설계 이력**: 이전 두 버전 모두 "제목 문단 1개 + 2열 표 1개"라는 고정
shape을 전제했다 — 처음엔 blocks.json으로
skills/hwp-skill/scripts/create_document.py를 subprocess 호출했고(v1), 이후엔
hwpx 라이브러리를 직접 호출하되 여전히 같은 고정 shape에 baseline 스타일만
입혔다(중간 버전, 폐기 — docs/tasks/template-create-authoring-v2.md 참고).
둘 다 문서 **구조** 자체를 template_spec이 표현하지 못했다. authoring-v2는
template_spec이 순서 있는 section 목록(title/info_table/body_section)으로
구조를 표현하고, page/style role 참조로 조판을 표현하게 했다 — 무엇을
배치할지와 어떻게 보이게 할지를 분리했다.

**institution-design-contract-v1**: authoring-v2 시점에는 각 section의
style이 ``{size_pt, align}``/``{width_mm, border_width_mm}`` 같은 인라인 값을
직접 들고 있었다. 이 모듈이 ``doc.styles.ensure_run(size=...)``만 호출하고
``color``/``font``/``bold``를 넘기지 않았기 때문에, hwpx 라이브러리가 생성한
``charPr``가 skeleton 문서의 기존 ``charPr``(미지정 속성)을 그대로 물려받는
문제(관찰된 사례: 제목이 의도치 않게 ``#2E74B5``로 나옴)가 있었다. 지금은
section의 style 필드가 **기관이 정의한 style role 이름**(문자열)이고, 그
role의 실제 font/size/color/bold/align 값은 Institution Design Contract
(``docs/contracts/institution-design-contract.schema.json``)에서 온다.
``core.adapters.hwpx_authoring_resolve.resolve()``가 role을 조회하고
TemplateSpec의 (허용된 범위 안의) override를 병합해 ``ResolvedAuthoringContract``
를 만든다 — 이 모듈은 그 결과만 소비한다. 이 파일의 ``generate_source_hwpx()``
는 style을 해석하거나 institution default를 조회하지 않는다: 받은 Resolved*
값을 그대로 ``hwpx`` 라이브러리 호출에 명시적으로 전달할 뿐이다.

repeat/가변 개수 section은 이 버전의 범위 밖이다 — 스키마에 예약된 타입도
없다(docs/tasks/template-create-authoring-v2.md "Out of scope"). 허용되는
``section.type``은 ``title`` / ``info_table`` / ``body_section`` 셋뿐이다.

candidate 생성·QA(strict roundtrip 검증 포함)는 이 모듈의 책임이 아니며, 기존
qa_hwpx_template.py가 그대로 담당한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Mapping, Union

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

from ..templates.hwpx_content_classifier import build_text_contexts
from ..templates.hwpx_separation_rules import TextRole
from .hwpx_layout_components import HwpxLayoutComponentError, expand_family_components

# 1 inch = 7200 HWPUNIT = 25.4mm. core/templates/extractors/style.py가 읽기
# 방향으로 쓰는 것과 같은 변환식을 저작(쓰기) 방향에 쓴다.
_HWPUNIT_PER_MM = 7200 / 25.4
_HANCOM_REFERENCE_PORTRAIT_TOKEN = "WIDELY"

_VALID_ALIGNS = ("left", "center")
_MARGIN_KEYS = ("left", "right", "top", "bottom", "header", "footer")
_REQUIRED_MARGIN_KEYS = ("left", "right", "top", "bottom")
_SECTION_TYPES = ("title", "info_table", "simple_table", "body_section", "content_box")

# masthead는 1행 [로고/문서명/로고] 3-슬롯 표다(institution-design-contract-v1
# 2026-08-18 사용자 결정). 어떤 칸이 어떤 role(logo_left/title/logo_right)인지는
# 더 이상 이 모듈의 상수가 아니다 — Institution Design Contract의
# ``masthead.slots``(왼쪽→오른쪽 role 순서)를 그대로 읽어 materialize한다
# (masthead-structural-ownership task, 확인 필요 시
# docs/tasks/masthead-structural-ownership.md 참고). 행 개수도 ``masthead.
# row_count`` 선언에서 오지 이 모듈의 리터럴이 아니다 — 다만 이 버전이
# 지원하는 값은 1뿐이고(resolve()가 그 외 값을 거부한다), 정확히 이 3개
# role 각 1개라는 것도 이 authoring 버전의 capability 한계이지 institution이
# 자유롭게 늘리거나 줄일 수 있는 값이 아니다.
_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


class HwpxTemplateAuthoringError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 문서 구조 — "무엇을 배치할지". style 필드는 institution role 이름 문자열이고,
# ``<key>_override``는 그 role의 일부 속성만 이 문서용으로 바꾸는 선택적
# 객체다 — 실제 병합·검증은 core.adapters.hwpx_authoring_resolve.resolve()가
# 한다. 이 모듈은 role 존재 여부나 override 허용 범위를 판단하지 않는다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TitleSection:
    style: str
    style_override: Mapping[str, Any]
    text: str
    semantic_element_id: str = ""
    type: Literal["title"] = "title"


@dataclass(frozen=True, slots=True)
class InfoTableRow:
    label: str
    field_id: str
    sample_value: str
    label_element_id: str = ""
    value_element_id: str = ""


@dataclass(frozen=True, slots=True)
class InfoTableSection:
    style: str
    style_override: Mapping[str, Any]
    label_style_override: Mapping[str, Any]
    value_style_override: Mapping[str, Any]
    rows: tuple[InfoTableRow, ...]
    pairs_per_row: int = 1
    type: Literal["info_table"] = "info_table"


@dataclass(frozen=True, slots=True)
class SimpleTableSection:
    style: str
    style_override: Mapping[str, Any]
    header: tuple[str, ...]
    column_widths: tuple[float, ...]
    rows: tuple[tuple[str, ...], ...]
    collection_field_id: str
    item_fields: tuple[str, ...]
    header_element_ids: tuple[str, ...]
    type: Literal["simple_table"] = "simple_table"


@dataclass(frozen=True, slots=True)
class HierarchyItem:
    level: int
    text: str
    marker: str
    native_intent_hwpunit: int
    line_spacing_percent: float


@dataclass(frozen=True, slots=True)
class BodySection:
    """``heading_style``/``heading_text`` are optional as a pair: both set
    means a FIXED_LABEL heading paragraph precedes the content (existing
    behavior, unchanged); both absent (``""``) means this section renders
    CONTENT only, with no heading paragraph at all. Declaring exactly one of
    the two is invalid — see ``_parse_body_section()``, which is the only
    place that enforces this both-or-neither rule.
    """

    body_style: str
    body_style_override: Mapping[str, Any]
    field_id: str
    sample_value: str
    heading_style: str = ""
    heading_style_override: Mapping[str, Any] = field(default_factory=dict)
    heading_text: str = ""
    hierarchy_items: tuple[HierarchyItem, ...] = ()
    hierarchy_item_field: str = ""
    heading_element_id: str = ""
    content_element_id: str = ""
    type: Literal["body_section"] = "body_section"


@dataclass(frozen=True, slots=True)
class ContentBoxItem:
    """One row of a ``ContentBoxSection`` — a single CONTENT field with no
    FIXED_LABEL, styled independently of its sibling rows.
    """

    body_style: str
    body_style_override: Mapping[str, Any]
    field_id: str
    sample_value: str
    content_element_id: str = ""


@dataclass(frozen=True, slots=True)
class ContentBoxSection:
    """A bordered, single-column table whose rows are CONTENT-only — no
    FIXED_LABEL anywhere in the box. The smallest primitive that can
    reproduce a reference layout where two or more distinct single-value
    CONTENT fields (e.g. a press-release headline and subtitle) sit inside
    one visible bordered box, each with its own style, with no label.

    ``style`` references an existing institution *table* role purely for its
    border/width — ``ResolvedTableStyle.label_style``/``value_style`` are
    resolved by ``resolve()`` (reusing the existing table-role resolver
    unchanged) but never used here, since this section has no label/value
    concept. Each row's own text style comes from its ``ContentBoxItem.body_style``
    instead, the same way ``BodySection.body_style`` works.
    """

    style: str
    style_override: Mapping[str, Any]
    items: tuple[ContentBoxItem, ...]
    type: Literal["content_box"] = "content_box"


Section = Union[TitleSection, InfoTableSection, SimpleTableSection, BodySection, ContentBoxSection]


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """Document structure (``sections``) plus its page contract (``page``).

    ``sections`` is what to place, in order — ``title`` / ``info_table`` /
    ``body_section`` (a repeating/variable-cardinality section type is
    explicitly out of scope for this version, not reserved; see
    docs/tasks/template-create-authoring-v2.md).

    Each section's style field(s) are institution style-role **names**, not
    inline property values — this module holds no typography values and no
    baseline defaults. ``core.adapters.hwpx_authoring_resolve.resolve()``
    turns a ``TemplateSpec`` plus an Institution Design Contract into a
    ``ResolvedAuthoringContract`` before ``generate_source_hwpx()`` runs.
    """

    template_spec_version: str
    page_margins_mm: Mapping[str, float]
    sections: tuple[Section, ...]
    semantic_contract_id: str = ""
    institution_design_id: str = ""
    institution_design_version: str = ""
    document_family: str = ""
    family_recipe_path: str = ""
    component_types: tuple[str, ...] = ()
    #: 이 문서가 masthead를 쓸지에 대한 **문서 자신의 선언**. ``None``은
    #: "선언하지 않음"이며 이때는 Institution Design Contract의
    #: ``masthead.default``가 그대로 적용된다. ``True``/``False``는
    #: ``masthead.document_override_allowed``가 true일 때만 유효하고,
    #: 아니면 resolve()가 거부한다.
    masthead_use: bool | None = None
    #: family recipe가 선언한 page invariant(용지/방향/좌우 여백). family가
    #: 없는 legacy spec은 비어 있다.
    family_page_invariants: Mapping[str, Any] = field(default_factory=dict)


def load_template_spec(path: Path | str) -> TemplateSpec:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HwpxTemplateAuthoringError(f"cannot read template_spec: {source} ({exc})") from exc
    if not isinstance(data, dict):
        raise HwpxTemplateAuthoringError(f"template_spec root must be an object: {source}")

    version = data.get("template_spec_version")
    if not isinstance(version, str) or not version.strip():
        raise HwpxTemplateAuthoringError("template_spec requires a non-empty template_spec_version")
    semantic_contract_id = _optional_top_level_str(data, "semantic_contract_id")
    institution_design_id = _optional_top_level_str(data, "institution_design_id")
    institution_design_version = _optional_top_level_str(data, "institution_design_version")

    page_margins_mm = _parse_page(data.get("page"))
    document_family = _optional_top_level_str(data, "document_family")
    component_types: tuple[str, ...] = ()
    family_recipe_path = ""
    family_page_invariants: dict[str, Any] = {}
    if document_family:
        recipe_value = _optional_top_level_str(data, "family_recipe")
        recipe_path = Path(recipe_value)
        if not recipe_path.is_absolute():
            recipe_path = source.parent / recipe_path
        try:
            raw_sections, component_types, family_page_invariants = expand_family_components(
                document_family, recipe_path, data.get("components")
            )
        except HwpxLayoutComponentError as exc:
            raise HwpxTemplateAuthoringError(str(exc)) from exc
        sections = _parse_sections(raw_sections)
        family_recipe_path = str(recipe_path)
    else:
        sections = _parse_sections(data.get("sections"))

    return TemplateSpec(
        template_spec_version=version,
        semantic_contract_id=semantic_contract_id,
        institution_design_id=institution_design_id,
        institution_design_version=institution_design_version,
        page_margins_mm=page_margins_mm,
        sections=sections,
        document_family=document_family,
        family_recipe_path=family_recipe_path,
        component_types=component_types,
        masthead_use=_parse_spec_masthead(data.get("masthead")),
        family_page_invariants=family_page_invariants,
    )


def _parse_spec_masthead(raw: Any) -> bool | None:
    """Read the document's own masthead declaration.

    Absent means "not declared" (institution default applies) — it is not the
    same as ``{"use": false}``. Whether a declaration is *permitted* is the
    Institution Design Contract's call and is checked in ``resolve()``, not
    here; this function only parses.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HwpxTemplateAuthoringError("template_spec.masthead must be an object")
    unknown = sorted(set(raw) - {"use"})
    if unknown:
        raise HwpxTemplateAuthoringError(
            f"template_spec.masthead has unknown key(s): {unknown}"
        )
    use = raw.get("use")
    if not isinstance(use, bool):
        raise HwpxTemplateAuthoringError("template_spec.masthead.use must be a boolean")
    return use


def _optional_top_level_str(data: Mapping[str, Any], key: str) -> str:
    if key not in data:
        return ""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HwpxTemplateAuthoringError(f"template_spec requires a non-empty {key}")
    return value


def _parse_page(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise HwpxTemplateAuthoringError("template_spec.page is required and must be an object")
    margins_raw = raw.get("margins_mm")
    if not isinstance(margins_raw, dict):
        raise HwpxTemplateAuthoringError(
            "template_spec.page.margins_mm is required and must be an object"
        )
    missing = [key for key in _REQUIRED_MARGIN_KEYS if key not in margins_raw]
    if missing:
        raise HwpxTemplateAuthoringError(
            f"template_spec.page.margins_mm is missing required key(s): {missing}"
        )
    margins: dict[str, float] = {}
    for key, value in margins_raw.items():
        if key not in _MARGIN_KEYS:
            raise HwpxTemplateAuthoringError(f"template_spec.page.margins_mm has unknown key: {key!r}")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
            or (key not in {"header", "footer"} and value == 0)
        ):
            raise HwpxTemplateAuthoringError(
                f"template_spec.page.margins_mm.{key} must be "
                f"{'non-negative' if key in {'header', 'footer'} else 'positive'} number"
            )
        margins[key] = float(value)
    return margins


def _parse_sections(raw: Any) -> tuple[Section, ...]:
    if not isinstance(raw, list) or not raw:
        raise HwpxTemplateAuthoringError("template_spec.sections is required and must be a non-empty list")
    sections: list[Section] = []
    seen_field_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HwpxTemplateAuthoringError(f"sections[{index}] must be an object")
        section_type = item.get("type")
        if section_type not in _SECTION_TYPES:
            raise HwpxTemplateAuthoringError(
                f"sections[{index}].type must be one of {_SECTION_TYPES}, got {section_type!r}"
            )
        if section_type == "title":
            sections.append(_parse_title_section(index, item))
        elif section_type == "info_table":
            info_table = _parse_info_table_section(index, item)
            for row in info_table.rows:
                _check_duplicate_field_id(index, row.field_id, seen_field_ids)
            sections.append(info_table)
        elif section_type == "simple_table":
            sections.append(_parse_simple_table_section(index, item))
        elif section_type == "content_box":
            content_box = _parse_content_box_section(index, item)
            for content_box_item in content_box.items:
                _check_duplicate_field_id(index, content_box_item.field_id, seen_field_ids)
            sections.append(content_box)
        else:
            body = _parse_body_section(index, item)
            _check_duplicate_field_id(index, body.field_id, seen_field_ids)
            sections.append(body)
    return tuple(sections)


def _check_duplicate_field_id(index: int, field_id: str, seen: set[str]) -> None:
    if field_id in seen:
        raise HwpxTemplateAuthoringError(f"sections[{index}] has duplicate field_id: {field_id!r}")
    seen.add(field_id)


def _require_nonempty_str(index: int, item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HwpxTemplateAuthoringError(f"sections[{index}].{key} must be a non-empty string")
    return value


def _require_style_ref(index: int, item: Mapping[str, Any], key: str) -> str:
    """Read ``sections[index][key]`` as an institution style-role **name**.

    Only shape is checked here (non-empty string) — whether the role
    actually exists in an Institution Design Contract is
    ``resolve()``'s job, not ``load_template_spec()``'s: a bare
    ``TemplateSpec`` has no institution contract to check against.
    """
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HwpxTemplateAuthoringError(f"sections[{index}].{key} must be a non-empty string")
    return value


def _parse_style_override(index: int, item: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Read the optional ``sections[index][key]`` override object.

    Absent means "no override" (``{}``), not "unresolved" — every property
    of the referenced role still comes from the Institution Design Contract.
    Which override keys are actually allowed is enforced by ``resolve()``,
    not here.
    """
    if key not in item:
        return {}
    value = item[key]
    if not isinstance(value, dict):
        raise HwpxTemplateAuthoringError(f"sections[{index}].{key} must be an object")
    return dict(value)


def _parse_title_section(index: int, item: Mapping[str, Any]) -> TitleSection:
    style = _require_style_ref(index, item, "style")
    style_override = _parse_style_override(index, item, "style_override")
    semantic_element_id = _optional_section_str(index, item, "semantic_element_id")
    text = _require_nonempty_str(index, item, "text")
    return TitleSection(
        style=style,
        style_override=style_override,
        semantic_element_id=semantic_element_id,
        text=text,
    )


def _parse_info_table_section(index: int, item: Mapping[str, Any]) -> InfoTableSection:
    style = _require_style_ref(index, item, "style")
    style_override = _parse_style_override(index, item, "style_override")
    label_style_override = _parse_style_override(index, item, "label_style_override")
    value_style_override = _parse_style_override(index, item, "value_style_override")
    raw_rows = item.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise HwpxTemplateAuthoringError(f"sections[{index}].rows must be a non-empty list")
    rows: list[InfoTableRow] = []
    for row_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise HwpxTemplateAuthoringError(f"sections[{index}].rows[{row_index}] must be an object")
        label_element_id = _optional_section_str(index, raw_row, "label_element_id")
        value_element_id = _optional_section_str(index, raw_row, "value_element_id")
        label = _require_nonempty_str(index, raw_row, "label")
        field_id = _require_nonempty_str(index, raw_row, "field_id")
        sample_value = _require_nonempty_str(index, raw_row, "sample_value")
        rows.append(
            InfoTableRow(
                label_element_id=label_element_id,
                value_element_id=value_element_id,
                label=label,
                field_id=field_id,
                sample_value=sample_value,
            )
        )
    pairs_per_row = item.get("pairs_per_row", 1)
    if not isinstance(pairs_per_row, int) or isinstance(pairs_per_row, bool) or pairs_per_row not in {1, 2}:
        raise HwpxTemplateAuthoringError(f"sections[{index}].pairs_per_row must be 1 or 2")
    return InfoTableSection(
        style=style,
        style_override=style_override,
        label_style_override=label_style_override,
        value_style_override=value_style_override,
        rows=tuple(rows),
        pairs_per_row=pairs_per_row,
    )


def _parse_body_section(index: int, item: Mapping[str, Any]) -> BodySection:
    has_heading_text = "heading_text" in item
    has_heading_style = "heading_style" in item
    if has_heading_text != has_heading_style:
        raise HwpxTemplateAuthoringError(
            f"sections[{index}] must declare both heading_text and heading_style, or neither"
        )
    if has_heading_text:
        heading_style = _require_style_ref(index, item, "heading_style")
        heading_style_override = _parse_style_override(index, item, "heading_style_override")
        heading_text = _require_nonempty_str(index, item, "heading_text")
        heading_element_id = _optional_section_str(index, item, "heading_element_id")
    else:
        if "heading_style_override" in item:
            raise HwpxTemplateAuthoringError(
                f"sections[{index}].heading_style_override requires heading_text/heading_style to also be declared"
            )
        if "heading_element_id" in item:
            raise HwpxTemplateAuthoringError(
                f"sections[{index}].heading_element_id requires heading_text/heading_style to also be declared"
            )
        heading_style = ""
        heading_style_override = {}
        heading_text = ""
        heading_element_id = ""
    body_style = _require_style_ref(index, item, "body_style")
    body_style_override = _parse_style_override(index, item, "body_style_override")
    content_element_id = _optional_section_str(index, item, "content_element_id")
    field_id = _require_nonempty_str(index, item, "field_id")
    hierarchy_items = _parse_hierarchy_items(index, item)
    hierarchy_item_field = _optional_section_str(index, item, "hierarchy_item_field") if hierarchy_items else ""
    sample_value = "" if hierarchy_items else _require_nonempty_str(index, item, "sample_value")
    return BodySection(
        heading_style=heading_style,
        heading_style_override=heading_style_override,
        body_style=body_style,
        body_style_override=body_style_override,
        heading_element_id=heading_element_id,
        content_element_id=content_element_id,
        heading_text=heading_text,
        field_id=field_id,
        sample_value=sample_value,
        hierarchy_items=hierarchy_items,
        hierarchy_item_field=hierarchy_item_field,
    )


def _parse_simple_table_section(index: int, item: Mapping[str, Any]) -> SimpleTableSection:
    style = _require_style_ref(index, item, "style")
    style_override = _parse_style_override(index, item, "style_override")
    header_raw = item.get("header", [])
    widths_raw = item.get("column_widths")
    rows_raw = item.get("rows")
    collection_field_id = _require_nonempty_str(index, item, "collection_field_id")
    item_fields_raw = item.get("item_fields")
    header_element_ids_raw = item.get("header_element_ids")
    if not isinstance(header_raw, list) or any(not isinstance(cell, str) or not cell for cell in header_raw):
        raise HwpxTemplateAuthoringError(f"sections[{index}].header must be a list of non-empty strings")
    if not isinstance(widths_raw, list) or not widths_raw or any(
        not isinstance(width, (int, float)) or isinstance(width, bool) or width <= 0 for width in widths_raw
    ):
        raise HwpxTemplateAuthoringError(f"sections[{index}].column_widths must contain positive numbers")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise HwpxTemplateAuthoringError(f"sections[{index}].rows must be a non-empty list")
    column_count = len(widths_raw)
    if header_raw and len(header_raw) != column_count:
        raise HwpxTemplateAuthoringError(f"sections[{index}].header must match column_widths length")
    if not isinstance(item_fields_raw, list) or len(item_fields_raw) != column_count or any(not isinstance(value, str) or not value for value in item_fields_raw):
        raise HwpxTemplateAuthoringError(f"sections[{index}].item_fields must match column_widths length")
    if not isinstance(header_element_ids_raw, list) or len(header_element_ids_raw) != len(header_raw) or any(not isinstance(value, str) or not value for value in header_element_ids_raw):
        raise HwpxTemplateAuthoringError(f"sections[{index}].header_element_ids must match header length")
    rows: list[tuple[str, ...]] = []
    for row_index, row in enumerate(rows_raw):
        if not isinstance(row, list) or len(row) != column_count or any(
            not isinstance(cell, str) or not cell for cell in row
        ):
            raise HwpxTemplateAuthoringError(
                f"sections[{index}].rows[{row_index}] must contain one non-empty string per column"
            )
        rows.append(tuple(row))
    return SimpleTableSection(
        style=style,
        style_override=style_override,
        header=tuple(header_raw),
        column_widths=tuple(float(width) for width in widths_raw),
        rows=tuple(rows),
        collection_field_id=collection_field_id,
        item_fields=tuple(item_fields_raw),
        header_element_ids=tuple(header_element_ids_raw),
    )


def _parse_content_box_section(index: int, item: Mapping[str, Any]) -> ContentBoxSection:
    style = _require_style_ref(index, item, "style")
    style_override = _parse_style_override(index, item, "style_override")
    raw_items = item.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise HwpxTemplateAuthoringError(f"sections[{index}].items must be a non-empty list")
    items = tuple(
        _parse_content_box_item(index, item_index, raw_item)
        for item_index, raw_item in enumerate(raw_items)
    )
    return ContentBoxSection(style=style, style_override=style_override, items=items)


def _parse_content_box_item(index: int, item_index: int, raw_item: Any) -> ContentBoxItem:
    if not isinstance(raw_item, dict):
        raise HwpxTemplateAuthoringError(f"sections[{index}].items[{item_index}] must be an object")
    body_style = raw_item.get("body_style")
    if not isinstance(body_style, str) or not body_style.strip():
        raise HwpxTemplateAuthoringError(
            f"sections[{index}].items[{item_index}].body_style must be a non-empty string"
        )
    body_style_override = raw_item.get("body_style_override", {})
    if not isinstance(body_style_override, dict):
        raise HwpxTemplateAuthoringError(
            f"sections[{index}].items[{item_index}].body_style_override must be an object"
        )
    field_id = raw_item.get("field_id")
    if not isinstance(field_id, str) or not field_id.strip():
        raise HwpxTemplateAuthoringError(
            f"sections[{index}].items[{item_index}].field_id must be a non-empty string"
        )
    sample_value = raw_item.get("sample_value")
    if not isinstance(sample_value, str) or not sample_value.strip():
        raise HwpxTemplateAuthoringError(
            f"sections[{index}].items[{item_index}].sample_value must be a non-empty string"
        )
    content_element_id = raw_item.get("content_element_id", "")
    if not isinstance(content_element_id, str):
        raise HwpxTemplateAuthoringError(
            f"sections[{index}].items[{item_index}].content_element_id must be a string"
        )
    return ContentBoxItem(
        body_style=body_style,
        body_style_override=dict(body_style_override),
        field_id=field_id,
        sample_value=sample_value,
        content_element_id=content_element_id,
    )


def _parse_hierarchy_items(index: int, item: Mapping[str, Any]) -> tuple[HierarchyItem, ...]:
    if "hierarchy" not in item and "items" not in item:
        return ()
    geometry_raw = item.get("hierarchy")
    items_raw = item.get("items")
    if not isinstance(geometry_raw, list) or not geometry_raw or not isinstance(items_raw, list) or not items_raw:
        raise HwpxTemplateAuthoringError(f"sections[{index}] hierarchy and items must be non-empty lists")
    geometry: dict[int, tuple[str, int, float]] = {}
    for geometry_index, entry in enumerate(geometry_raw):
        if not isinstance(entry, dict):
            raise HwpxTemplateAuthoringError(f"sections[{index}].hierarchy[{geometry_index}] must be an object")
        level = entry.get("level")
        marker = entry.get("marker")
        intent = entry.get("native_intent_hwpunit")
        spacing = entry.get("line_spacing_percent")
        if not isinstance(level, int) or isinstance(level, bool) or level <= 0 or level in geometry:
            raise HwpxTemplateAuthoringError(f"sections[{index}].hierarchy[{geometry_index}].level must be unique and positive")
        if not isinstance(marker, str) or not marker or not isinstance(intent, int) or isinstance(intent, bool):
            raise HwpxTemplateAuthoringError(f"sections[{index}].hierarchy[{geometry_index}] has invalid marker or native intent")
        if not isinstance(spacing, (int, float)) or isinstance(spacing, bool) or spacing <= 0:
            raise HwpxTemplateAuthoringError(f"sections[{index}].hierarchy[{geometry_index}].line_spacing_percent must be positive")
        geometry[level] = (marker, intent, float(spacing))
    items: list[HierarchyItem] = []
    for item_index, entry in enumerate(items_raw):
        if not isinstance(entry, dict):
            raise HwpxTemplateAuthoringError(f"sections[{index}].items[{item_index}] must be an object")
        level = entry.get("level")
        text = entry.get("text")
        if level not in geometry or not isinstance(text, str) or not text:
            raise HwpxTemplateAuthoringError(f"sections[{index}].items[{item_index}] must select a declared level and text")
        marker, intent, spacing = geometry[level]
        items.append(HierarchyItem(level, text, marker, intent, spacing))
    return tuple(items)


def _optional_section_str(index: int, item: Mapping[str, Any], key: str) -> str:
    if key not in item:
        return ""
    return _require_nonempty_str(index, item, key)


def validate_semantic_placements(
    semantic_contract: Mapping[str, Any], spec: TemplateSpec
) -> tuple[Mapping[str, str], ...]:
    elements = semantic_contract.get("elements")
    if not isinstance(elements, list) or not elements:
        raise HwpxTemplateAuthoringError("semantic contract requires a non-empty elements list")
    by_element: dict[str, Mapping[str, Any]] = {}
    for entry in elements:
        if not isinstance(entry, dict):
            raise HwpxTemplateAuthoringError("semantic contract elements must be objects")
        element_id = entry.get("element_id")
        role = entry.get("role")
        if not isinstance(element_id, str) or not element_id or role not in {
            "CONTENT", "FIXED_LABEL", "FIXED_TEXT"
        }:
            raise HwpxTemplateAuthoringError("semantic contract has an invalid element_id or role")
        if element_id in by_element:
            raise HwpxTemplateAuthoringError(f"semantic contract has duplicate element_id: {element_id!r}")
        by_element[element_id] = entry

    placements: list[Mapping[str, str]] = []
    for section_index, section in enumerate(spec.sections):
        match section:
            case TitleSection():
                placements.append(
                    _semantic_placement(by_element, section.semantic_element_id, "FIXED_TEXT", section_index, None, None)
                )
            case InfoTableSection():
                for row_index, row in enumerate(section.rows):
                    placements.append(
                        _semantic_placement(by_element, row.label_element_id, "FIXED_LABEL", section_index, row_index, None)
                    )
                    placement = _semantic_placement(
                        by_element, row.value_element_id, "CONTENT", section_index, row_index, row.field_id
                    )
                    placements.append(placement)
            case SimpleTableSection():
                for column_index, element_id in enumerate(section.header_element_ids):
                    placements.append(_semantic_placement(by_element, element_id, "FIXED_LABEL", section_index, column_index, None))
                for column_index, item_field in enumerate(section.item_fields):
                    placements.append(_semantic_collection_placement(by_element, section.collection_field_id, item_field, section_index, column_index))
            case BodySection():
                if section.hierarchy_items:
                    for item_index, item in enumerate(section.hierarchy_items):
                        placement = dict(
                            _semantic_collection_placement(
                                by_element,
                                section.content_element_id,
                                section.hierarchy_item_field,
                                section_index,
                                item_index,
                            )
                        )
                        placement["prototype_level"] = str(item.level)
                        placements.append(placement)
                else:
                    if section.heading_text:
                        placements.append(_semantic_placement(by_element, section.heading_element_id, "FIXED_LABEL", section_index, None, None))
                    placements.append(_semantic_placement(by_element, section.content_element_id, "CONTENT", section_index, None, section.field_id))
            case ContentBoxSection():
                for item_index, box_item in enumerate(section.items):
                    placements.append(
                        _semantic_placement(by_element, box_item.content_element_id, "CONTENT", section_index, item_index, box_item.field_id)
                    )
            case unreachable:
                raise HwpxTemplateAuthoringError(f"unsupported TemplateSpec section: {unreachable!r}")

    placed_ids = [placement["element_id"] for placement in placements]
    duplicated_fixed = [element_id for element_id in placed_ids if placed_ids.count(element_id) > 1 and by_element[element_id].get("role") != "CONTENT"]
    if duplicated_fixed:
        raise HwpxTemplateAuthoringError("each fixed semantic contract element must be placed exactly once")
    if set(placed_ids) != set(by_element):
        raise HwpxTemplateAuthoringError("TemplateSpec must place every semantic contract element exactly once")
    return tuple(placements)


def _semantic_placement(
    by_element: Mapping[str, Mapping[str, Any]],
    element_id: str,
    expected_role: str,
    section_index: int,
    row_index: int | None,
    field_id: str | None,
) -> Mapping[str, str]:
    element = by_element.get(element_id)
    if element is None:
        raise HwpxTemplateAuthoringError(f"TemplateSpec references unknown semantic element: {element_id!r}")
    if element.get("role") != expected_role:
        raise HwpxTemplateAuthoringError(
            f"semantic element {element_id!r} must be {expected_role}, got {element.get('role')!r}"
        )
    result = {"element_id": element_id, "role": expected_role, "section_index": str(section_index)}
    if row_index is not None:
        result["row_index"] = str(row_index)
    if expected_role == "CONTENT":
        declared_field_id = element.get("field_id")
        if not isinstance(declared_field_id, str) or declared_field_id != field_id:
            raise HwpxTemplateAuthoringError(
                f"semantic CONTENT element {element_id!r} must project field_id {declared_field_id!r}"
            )
        result["field_id"] = declared_field_id
    return result


def _semantic_collection_placement(
    by_element: Mapping[str, Mapping[str, Any]], element_id: str, item_field: str, section_index: int, materialized_index: int
) -> Mapping[str, str]:
    element = by_element.get(element_id)
    if element is None or element.get("role") != "CONTENT" or element.get("content_type") != "object":
        raise HwpxTemplateAuthoringError(f"semantic collection element {element_id!r} is not declared as structured CONTENT")
    item_fields = element.get("item_fields")
    if not isinstance(item_fields, list) or item_field not in item_fields:
        raise HwpxTemplateAuthoringError(f"semantic collection element {element_id!r} does not declare item field {item_field!r}")
    field_id = element.get("field_id")
    if not isinstance(field_id, str):
        raise HwpxTemplateAuthoringError(f"semantic collection element {element_id!r} has no canonical field_id")
    return {"element_id": element_id, "role": "CONTENT", "field_id": field_id, "item_field": item_field, "section_index": str(section_index), "materialized_index": str(materialized_index)}


# ---------------------------------------------------------------------------
# Resolved Authoring Contract — "실제 HWPX 생성 직전, 모든 필요한 authoring
# 값이 명시적으로 확정된 상태". core.adapters.hwpx_authoring_resolve.resolve()
# 가 이 타입들을 만들어 낸다; generate_source_hwpx()는 이 값을 그대로 소비할
# 뿐 institution default를 조회하거나 override를 병합하지 않는다.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedTextStyle:
    font_family: str
    size_pt: float
    color: str
    bold: bool
    align: str
    line_spacing_percent: float | None = None
    spacing_before_pt: float | None = None
    spacing_after_pt: float | None = None
    indent_left_mm: float | None = None
    native_intent_hwpunit: int | None = None
    heading_rule_width_mm: float | None = None
    marker: str | None = None
    keep_with_next: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedTableStyle:
    width_mm: float
    border_width_mm: float
    border_color: str
    label_style: ResolvedTextStyle
    value_style: ResolvedTextStyle
    label_width_ratio: float
    cell_margin_mm: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedLogo:
    # str, not Path: 이 필드를 포함한 ResolvedAuthoringContract 전체가
    # write_resolved_authoring_contract()에서 dataclasses.asdict() + json.dumps로
    # 그대로 직렬화된다(provenance 기록) — Path는 json 기본 인코더가 직렬화
    # 못 해 그 경로가 깨진다. 다른 Resolved* 필드가 전부 str/float/bool인 것과
    # 맞춘다.
    asset_path: str
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class ResolvedMasthead:
    """The fixed top-of-document identity band (institution-design-contract-v1
    visual-layout task, 2026-08-18 user decision): a bordered box with a logo
    left, the document name centered, and a second logo right. ``title`` is
    the text of the ``TemplateSpec``'s first ``title`` section — the masthead
    *consumes* that section (``generate_source_hwpx()`` does not also
    materialize it as a standalone paragraph) rather than duplicating it.
    """

    title: str
    title_style: ResolvedTextStyle
    width_mm: float
    height_mm: float
    border_width_mm: float
    border_color: str
    cell_margin_mm: Mapping[str, float]
    spacing_after_pt: float | None
    logo_left: ResolvedLogo | None
    logo_right: ResolvedLogo | None
    # 세 칸의 실제 폭 — institution이 명시적으로 결정한 값이다(로고 크기나
    # cell_margin에서 유도하지 않는다, width/3 균등분배도 아니다). 합이
    # width_mm과 일치함은 resolve()가 이미 검증했다.
    logo_left_slot_width_mm: float
    title_slot_width_mm: float
    logo_right_slot_width_mm: float
    # 왼쪽→오른쪽 column 순서로 나열한 role 이름
    # ("logo_left"/"title"/"logo_right", 각 정확히 1개). 어느 칸이 어느
    # role인지를 결정하는 유일한 source of truth다 — authoring은 이 순서를
    # 그대로 읽어 column index를 계산할 뿐, 스스로 위치를 가정하지 않는다.
    slots: tuple[str, ...]
    # 표의 행 개수 — 이 authoring 버전은 1만 지원하지만(resolve()가 검증),
    # 그 사실 자체를 이 필드가 보존한다. `_materialize_masthead()`는 이 값을
    # `_add_table(rows=...)`에 그대로 전달할 뿐 리터럴 `1`을 스스로 쓰지 않는다.
    row_count: int


@dataclass(frozen=True, slots=True)
class ResolvedTitleSection:
    style: ResolvedTextStyle
    text: str
    type: Literal["title"] = "title"


@dataclass(frozen=True, slots=True)
class ResolvedInfoTableSection:
    style: ResolvedTableStyle
    rows: tuple[InfoTableRow, ...]
    pairs_per_row: int = 1
    type: Literal["info_table"] = "info_table"


@dataclass(frozen=True, slots=True)
class ResolvedSimpleTableSection:
    style: ResolvedTableStyle
    header: tuple[str, ...]
    column_widths: tuple[float, ...]
    rows: tuple[tuple[str, ...], ...]
    collection_field_id: str
    item_fields: tuple[str, ...]
    header_element_ids: tuple[str, ...]
    type: Literal["simple_table"] = "simple_table"


@dataclass(frozen=True, slots=True)
class ResolvedBodySection:
    """``heading_style`` is ``None`` exactly when the source ``BodySection``
    declared no heading (see ``BodySection``'s docstring) — that is the sole
    signal ``generate_source_hwpx()`` and ``_expected_non_table_entries()``
    use to skip the heading paragraph.
    """

    heading_style: ResolvedTextStyle | None
    body_style: ResolvedTextStyle
    heading_text: str
    field_id: str
    sample_value: str
    hierarchy_items: tuple[HierarchyItem, ...] = ()
    type: Literal["body_section"] = "body_section"


@dataclass(frozen=True, slots=True)
class ResolvedContentBoxItem:
    body_style: ResolvedTextStyle
    field_id: str
    sample_value: str


@dataclass(frozen=True, slots=True)
class ResolvedContentBoxSection:
    """``style`` is a full ``ResolvedTableStyle`` (same resolver as
    ``info_table``/``simple_table``) but only its ``width_mm``/
    ``border_width_mm``/``border_color``/``cell_margin_mm`` are used —
    ``label_style``/``value_style`` are resolved and then ignored, since a
    content box has no label/value concept; each row's style is its own
    ``ResolvedContentBoxItem.body_style`` instead.
    """

    style: ResolvedTableStyle
    items: tuple[ResolvedContentBoxItem, ...]
    type: Literal["content_box"] = "content_box"


ResolvedSection = Union[
    ResolvedTitleSection,
    ResolvedInfoTableSection,
    ResolvedSimpleTableSection,
    ResolvedBodySection,
    ResolvedContentBoxSection,
]


@dataclass(frozen=True, slots=True)
class ResolvedAuthoringContract:
    page_margins_mm: Mapping[str, float]
    sections: tuple[ResolvedSection, ...]
    semantic_contract_id: str | None = None
    institution_design_id: str | None = None
    semantic_placements: tuple[Mapping[str, str], ...] = ()
    masthead: ResolvedMasthead | None = None
    #: family recipe가 선언한 용지/방향. ``None``이면 family가 없는 legacy
    #: spec이라 이 authoring 버전이 용지를 명시하지 않는다(기존 동작 유지).
    paper_size: str | None = None
    orientation: str | None = None


def run_skill_subprocess(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with the shared skill-invocation convention.

    Captures text output as UTF-8 (Windows-safe for Korean text) the same way
    every hwp-skill/qa_hwpx_template.py caller in this codebase does. Raises
    ``HwpxTemplateAuthoringError`` if the process itself cannot be launched;
    a non-zero exit code is returned to the caller to interpret, not raised.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except OSError as exc:
        raise HwpxTemplateAuthoringError(f"failed to launch subprocess {cmd[:2]}: {exc}") from exc


def generate_source_hwpx(resolved: ResolvedAuthoringContract, output_path: Path | str) -> Path:
    """Materialize *resolved*'s ``sections`` into a real HWPX package via the ``hwpx`` library.

    Dispatches per ``section.type`` (``title``/``info_table``/``body_section``)
    instead of assuming any fixed shape — the number and order of paragraphs
    and tables follow ``resolved.sections`` exactly. Every property this
    function passes to the ``hwpx`` library (font/size/color/bold/align for
    runs, border/width for tables) comes directly from *resolved* — this
    function makes no design judgment and consults no institution default; a
    caller must resolve a ``TemplateSpec`` via
    ``core.adapters.hwpx_authoring_resolve.resolve()`` first.
    """
    output = Path(output_path)
    if output.exists():
        raise HwpxTemplateAuthoringError(f"authoring output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        doc = HwpxDocument.new()
        section = doc.sections[0]
        # 용지/방향은 family recipe가 소유한 invariant다 — 라이브러리
        # skeleton이 우연히 A4 세로를 만들어 주는 것에 기대지 않고 명시적으로
        # 전달한다. family가 없는 legacy spec은 선언할 값이 없으므로 기존처럼
        # 여백만 설정한다.
        page_setup: dict[str, Any] = {"margins_mm": dict(resolved.page_margins_mm)}
        if resolved.paper_size is not None:
            page_setup["paper_size"] = resolved.paper_size
        if resolved.orientation is not None:
            page_setup["orientation"] = resolved.orientation
        doc.page.setup(section=section, **page_setup)
        if resolved.orientation == "portrait":
            section.properties.set_page_size(orientation=_HANCOM_REFERENCE_PORTRAIT_TOKEN)

        # HwpxDocument.new()의 section에는 빈 skeleton 문단이 하나 이미 있다
        # (HWPX가 섹션을 비워 두는 것을 허용하지 않기 때문, 그리고 방금 적용한
        # secPr/여백이 이 문단에 붙어 있다). 이 문단을 지우는 대신, 문서에서
        # **가장 먼저 materialize되는 내용**(masthead가 있으면 masthead, 없으면
        # title, 그것도 없으면 첫 body_section의 heading)이 될 때 재사용한다 —
        # section.remove_paragraph()로 지우면 이 hwpx 버전에서 이후 API 호출이
        # lxml/stdlib ElementTree 불일치로 깨지는 문제가 있었다(직접 재현 확인).
        #
        # 중요: 이 skeleton 문단은 문서 안에서 항상 맨 앞에 물리적으로 존재한다
        # — "재사용"이 텍스트만 바꿔 끼우는 것이라면, 실제로 맨 먼저
        # materialize된 내용이 아닌 다른 것이 이 문단을 먼저 채가면 문서
        # 순서가 어긋난다(v3 visual QA에서 실측된 P0-1 버그: masthead/
        # info_table은 doc.add_table()로 항상 새 문단을 append만 해서
        # skeleton_pool을 전혀 건드리지 않았고, 그래서 masthead 다음에 나와야
        # 할 첫 heading이 skeleton_pool을 팝해 여전히 맨 앞 위치에 남아 있던
        # 그 문단의 텍스트를 바꿔치기했다 — 결과적으로 heading이 masthead보다
        # 앞에 나왔다). 표를 만드는 _materialize_masthead()/_materialize_info_table()
        # 도 이제 같은 skeleton_pool을 공유해, 실제로 가장 먼저 호출된 쪽이
        # 이 문단을 가져간다 — materialize 호출 순서와 문서 상 순서가 항상
        # 일치하도록 보장한다.
        skeleton_pool = list(section.paragraphs)

        if resolved.masthead is not None:
            _materialize_masthead(doc, section, resolved.masthead, skeleton_pool)

        for entry in resolved.sections:
            if isinstance(entry, ResolvedTitleSection):
                if resolved.masthead is not None:
                    # masthead가 이 title section의 텍스트를 이미 masthead 중앙
                    # 셀에 실었다 — 별도 문단으로 다시 materialize하면 문서명이
                    # 두 번 나온다. resolve()가 masthead를 만들 때 title
                    # section에서 텍스트를 가져왔으므로 여기서는 건너뛴다.
                    continue
                _materialize_paragraph(doc, section, entry.text, entry.style, skeleton_pool)
            elif isinstance(entry, ResolvedInfoTableSection):
                _materialize_info_table(doc, section, entry, skeleton_pool)
            elif isinstance(entry, ResolvedSimpleTableSection):
                _materialize_simple_table(doc, section, entry, skeleton_pool)
            elif isinstance(entry, ResolvedBodySection):
                if entry.hierarchy_items:
                    for item in entry.hierarchy_items:
                        _materialize_paragraph(
                            doc,
                            section,
                            item.text,
                            replace(
                                entry.body_style,
                                marker=item.marker,
                                native_intent_hwpunit=item.native_intent_hwpunit,
                                line_spacing_percent=item.line_spacing_percent,
                            ),
                            skeleton_pool,
                        )
                else:
                    if entry.heading_style is not None:
                        _materialize_paragraph(
                            doc, section, entry.heading_text, entry.heading_style, skeleton_pool
                        )
                    _materialize_paragraph(
                        doc, section, entry.sample_value, entry.body_style, skeleton_pool
                    )
            elif isinstance(entry, ResolvedContentBoxSection):
                _materialize_content_box(doc, section, entry, skeleton_pool)
            else:  # pragma: no cover - resolve() only ever builds the above
                raise HwpxTemplateAuthoringError(f"unhandled section type: {entry!r}")

        if skeleton_pool:
            # title/body_section이 하나도 없어 skeleton 문단을 재사용할
            # 기회가 없었다 — info_table만으로 이뤄진 문서는 이 함수가
            # 아직 지원하지 않는다(추측으로 처리하지 않고 명시적으로 거부).
            raise HwpxTemplateAuthoringError(
                "template_spec.sections must include at least one 'title' or "
                "'body_section' entry; a document made only of 'info_table' "
                "sections is not supported"
            )

        doc.save_to_path(output)
    except HwpxError as exc:
        if output.exists():
            output.unlink()
        raise HwpxTemplateAuthoringError(f"failed to author source.hwpx: {exc}") from exc

    if not zipfile.is_zipfile(output):
        if output.exists():
            output.unlink()
        raise HwpxTemplateAuthoringError(
            f"authored output is not a readable HWPX ZIP: {output}"
        )
    return output


def _ensure_run_for_style(doc: Any, style: ResolvedTextStyle) -> str:
    """Mint/find a ``charPr`` with every contract-owned property passed
    explicitly, so the hwpx library's "unspecified = don't care" predicate
    (``_run_style_predicate`` in the installed ``hwpx`` library) can never
    match/reuse an unrelated skeleton ``charPr`` for font or color — the
    fix for the originally reported ``#2E74B5`` leak.
    """
    return doc.styles.ensure_run(
        size=style.size_pt,
        color=style.color,
        font=style.font_family,
        bold=style.bold,
    )


def _apply_paragraph_format(doc: Any, paragraph: Any, style: ResolvedTextStyle) -> None:
    kwargs: dict[str, Any] = {
        "paragraph_index": doc.paragraphs.index(paragraph),
        "alignment": style.align.upper(),
    }
    if style.line_spacing_percent is not None:
        kwargs["line_spacing_percent"] = style.line_spacing_percent
    if style.spacing_before_pt is not None:
        kwargs["spacing_before_pt"] = style.spacing_before_pt
    if style.spacing_after_pt is not None:
        kwargs["spacing_after_pt"] = style.spacing_after_pt
    if style.native_intent_hwpunit is None and style.indent_left_mm is not None:
        kwargs["indent_left_mm"] = style.indent_left_mm
    if style.heading_rule_width_mm is not None:
        # section heading 아래 구분선("heading rule") — role 자신의 color를
        # 그대로 재사용한다(별도 heading_rule_color 속성을 새로 만들지 않는다:
        # 지금까지 필요한 경우가 하나뿐이라 role color 재사용이 최소 구현이다).
        kwargs["bottom_border"] = True
        kwargs["border_color"] = style.color
        kwargs["border_width"] = f"{style.heading_rule_width_mm} mm"
    if style.keep_with_next:
        kwargs["keep_with_next"] = True
    doc.styles.apply_paragraph_format(**kwargs)
    if style.native_intent_hwpunit is not None:
        header = doc._root.headers[0]
        left_margin = 0
        if style.indent_left_mm is not None:
            left_margin = round(style.indent_left_mm * _HWPUNIT_PER_MM)
        paragraph.para_pr_id_ref = header.ensure_paragraph_format(
            base_para_pr_id=paragraph.para_pr_id_ref,
            margins={"left": left_margin, "intent": style.native_intent_hwpunit},
        )


def _materialize_paragraph(
    doc: Any,
    section: Any,
    text: str,
    style: ResolvedTextStyle,
    skeleton_pool: list[Any],
) -> None:
    display_text = f"{style.marker}{text}" if style.marker else text
    char_pr = _ensure_run_for_style(doc, style)
    if skeleton_pool:
        paragraph = skeleton_pool.pop()
        paragraph.text = display_text
        paragraph.char_pr_id_ref = char_pr
    else:
        # inherit_style=False: 기본값(True)은 새 문단의 paraPrIDRef를 바로 앞
        # 문단(예: 방금 만든 heading)의 paraPrIDRef로 그대로 복사한다.
        # ensure_paragraph_format()은 이렇게 상속된 paraPr을 deepcopy 기반으로
        # 덮어쓰기만 하고 명시되지 않은 속성(border 등)은 지우지 않으므로,
        # heading의 구분선이 body에 그대로 새어나오는 원인이었다(v3 visual QA
        # P0-2). body는 항상 중립 기본 paraPr에서 시작해야 한다.
        paragraph = doc.add_paragraph(
            display_text, section=section, char_pr_id_ref=char_pr, inherit_style=False
        )
    _apply_paragraph_format(doc, paragraph, style)


def _add_table(
    doc: Any,
    section: Any,
    skeleton_pool: list[Any],
    *,
    rows: int,
    cols: int,
    border_fill_id_ref: str,
    width: int,
    height: int | None = None,
) -> Any:
    """표를 만든다 — skeleton 재사용 가능하면 그 문단 위에, 아니면 새 문단에.

    `doc.add_table()`은 항상 새 문단을 append만 해서 `skeleton_pool`을
    건드리지 않는다. masthead/info_table이 문서에서 실제로 가장 먼저
    materialize되는 내용일 때도 이 때문에 맨 앞 skeleton 문단이 그대로
    남아 있다가 이후의 첫 본문 문단이 그 자리를 대신 차지해, 결과 문서
    순서가 실제 materialize 순서와 어긋났다(v3 visual QA P0-1: masthead
    보다 먼저 나와야 할 heading이 여전히 맨 앞 자리를 차지). 표도 문단
    문단(`HwpxOxmlParagraph.add_table()`)에 대해 만들 수 있으므로, skeleton
    문단이 남아 있으면 그 위에 표를 지어 같은 pool을 공유한다 — 실제로
    가장 먼저 호출된 쪽이 맨 앞 자리를 갖도록 보장한다.
    """
    if skeleton_pool:
        anchor_paragraph = skeleton_pool.pop()
        # 재사용하는 skeleton 문단은 빈 텍스트 run을 이미 갖고 있다 —
        # _materialize_masthead_logo()가 로고 칸에서 하는 것과 같은 이유로,
        # 표를 붙이기 전에 지운다(안 지우면 표 옆에 의미 없는 빈 텍스트
        # 노드가 하나 남아 build_text_contexts()/build_separation_rules()가
        # 어긋난다). 단, 이 문단이 section의 실제 첫 문단이면 그 안의 run
        # 하나에 `<hp:secPr>`(margins/용지 설정, doc.page.setup()이 이미
        # 적용한 값)가 들어 있을 수 있다 — hwpx 라이브러리가 secPr을 항상
        # section 첫 문단의 첫 run 안에 둔다(oxml/section.py 확인). 그 run까지
        # 지우면 secPr 자체가 사라져 margin이 통째로 빠진다 — secPr을 담은
        # run은 남기고 순수 텍스트 run만 지운다.
        for run in list(anchor_paragraph.runs):
            if run.element.find(f"{{{_HP_NS}}}secPr") is not None:
                continue
            anchor_paragraph.element.remove(run.element)
        table_kwargs: dict[str, Any] = {"width": width, "border_fill_id_ref": border_fill_id_ref}
        if height is not None:
            table_kwargs["height"] = height
        return anchor_paragraph.add_table(rows, cols, **table_kwargs)
    table_kwargs = {"section": section, "border_fill_id_ref": border_fill_id_ref, "width": width}
    if height is not None:
        table_kwargs["height"] = height
    return doc.add_table(rows, cols, **table_kwargs)


def _materialize_info_table(
    doc: Any, section: Any, entry: ResolvedInfoTableSection, skeleton_pool: list[Any]
) -> None:
    style = entry.style
    border_fill_id = doc.styles.ensure_border_fill(
        border_width=f"{style.border_width_mm} mm",
        border_color=style.border_color,
    )
    table_rows = (len(entry.rows) + entry.pairs_per_row - 1) // entry.pairs_per_row
    table_columns = 2 * entry.pairs_per_row
    table = _add_table(
        doc,
        section,
        skeleton_pool,
        rows=table_rows,
        cols=table_columns,
        border_fill_id_ref=border_fill_id,
        width=round(style.width_mm * _HWPUNIT_PER_MM),
    )
    # 고정 width/2, width/2 대신 institution이 정한 label:value 비율을 쓴다 —
    # "보고 기간 | 2026-08-04 ~ 2026-08-08"처럼 label이 짧고 value가 길 때
    # 둘을 반씩 나누면 label 열에 빈 공간이 크게 남는다.
    table.set_column_widths(
        [style.label_width_ratio, 1.0 - style.label_width_ratio] * entry.pairs_per_row
    )
    if style.cell_margin_mm is not None:
        _set_table_cell_margin(table, style.cell_margin_mm)
    label_char_pr = _ensure_run_for_style(doc, style.label_style)
    value_char_pr = _ensure_run_for_style(doc, style.value_style)
    for row_index, row in enumerate(entry.rows):
        table_row = row_index // entry.pairs_per_row
        label_column = 2 * (row_index % entry.pairs_per_row)
        value_column = label_column + 1
        table.set_cell_text(table_row, label_column, row.label)
        table.set_cell_text(table_row, value_column, row.sample_value)
        # set_cell_text()의 기본 preserve_format=True는 셀이 이미 갖고 있던
        # (skeleton 또는 이전) charPr을 그대로 둔다 — label/value typography가
        # Institution Design Contract에서 온 값이 아니라 라이브러리/이전
        # 상태에서 새어 들어올 수 있다. 텍스트를 쓴 뒤 각 셀 문단의
        # charPrIDRef를 명시적으로 덮어써 이 leak을 차단한다.
        for paragraph in table.cell(table_row, label_column).paragraphs:
            paragraph.char_pr_id_ref = label_char_pr
        for paragraph in table.cell(table_row, value_column).paragraphs:
            paragraph.char_pr_id_ref = value_char_pr


def _materialize_simple_table(
    doc: Any, section: Any, entry: ResolvedSimpleTableSection, skeleton_pool: list[Any]
) -> None:
    style = entry.style
    border_fill_id = doc.styles.ensure_border_fill(
        border_width=f"{style.border_width_mm} mm",
        border_color=style.border_color,
    )
    table = _add_table(
        doc,
        section,
        skeleton_pool,
        rows=len(entry.rows) + (1 if entry.header else 0),
        cols=len(entry.column_widths),
        border_fill_id_ref=border_fill_id,
        width=round(style.width_mm * _HWPUNIT_PER_MM),
    )
    table.set_column_widths(list(entry.column_widths))
    if style.cell_margin_mm is not None:
        _set_table_cell_margin(table, style.cell_margin_mm)
    label_char_pr = _ensure_run_for_style(doc, style.label_style)
    value_char_pr = _ensure_run_for_style(doc, style.value_style)
    if entry.header:
        for column_index, cell_text in enumerate(entry.header):
            table.set_cell_text(0, column_index, cell_text)
            for paragraph in table.cell(0, column_index).paragraphs:
                paragraph.char_pr_id_ref = label_char_pr
    row_offset = 1 if entry.header else 0
    for row_index, row in enumerate(entry.rows, start=row_offset):
        for column_index, cell_text in enumerate(row):
            table.set_cell_text(row_index, column_index, cell_text)
            for paragraph in table.cell(row_index, column_index).paragraphs:
                paragraph.char_pr_id_ref = value_char_pr


def _materialize_content_box(
    doc: Any, section: Any, entry: ResolvedContentBoxSection, skeleton_pool: list[Any]
) -> None:
    """1열 bordered table, 행마다 CONTENT 하나씩·label 없음.

    ``entry.style``의 label/value style은 쓰지 않는다(border/width/
    cell_margin만) — 각 행의 실제 텍스트 style은 그 행의
    ``ResolvedContentBoxItem.body_style``다. 정렬(align)은 ``doc.styles.
    apply_paragraph_format()``으로는 표 셀 문단에 적용할 수 없어(그 API는
    ``doc.paragraphs`` 최상위 인덱스로만 대상을 찾는다) masthead 제목 셀과
    같은 방식(``_ensure_paragraph_alignment()``)으로 처리한다.
    """
    style = entry.style
    border_fill_id = doc.styles.ensure_border_fill(
        border_width=f"{style.border_width_mm} mm",
        border_color=style.border_color,
    )
    table = _add_table(
        doc,
        section,
        skeleton_pool,
        rows=len(entry.items),
        cols=1,
        border_fill_id_ref=border_fill_id,
        width=round(style.width_mm * _HWPUNIT_PER_MM),
    )
    if style.cell_margin_mm is not None:
        _set_table_cell_margin(table, style.cell_margin_mm)
    for row_index, item in enumerate(entry.items):
        char_pr = _ensure_run_for_style(doc, item.body_style)
        para_pr = _ensure_paragraph_alignment(doc, item.body_style.align.upper())
        table.set_cell_text(row_index, 0, item.sample_value)
        for paragraph in table.cell(row_index, 0).paragraphs:
            paragraph.char_pr_id_ref = char_pr
            paragraph.para_pr_id_ref = para_pr


#: masthead.slots가 선언할 수 있는 role별 실제 값 lookup — role 이름을 어느
#: ``ResolvedMasthead`` 필드/materialize 동작에 연결할지는 여기 한 곳에서만
#: 결정한다. 새 role을 추가하려면(이번 task 범위 밖) 이 dict와
#: ``_MASTHEAD_SLOT_MATERIALIZERS``만 늘리면 된다 — `_materialize_masthead()`
#: 자체는 role 이름으로 분기하지 않는다.
def _masthead_slot_width_by_role(masthead: ResolvedMasthead) -> Mapping[str, float]:
    return {
        "logo_left": masthead.logo_left_slot_width_mm,
        "title": masthead.title_slot_width_mm,
        "logo_right": masthead.logo_right_slot_width_mm,
    }


def _materialize_masthead(
    doc: Any, section: Any, masthead: ResolvedMasthead, skeleton_pool: list[Any]
) -> None:
    """[로고 | 문서명 | 로고] 1행 표를 문서 최상단에 만든다.

    일반 본문 문단이 아니라 표로 만드는 이유는 두 가지다: (1) 로고를 실제
    `hp:pic` 이미지 개체로 넣으려면 어차피 문단 안에 넣어야 하는데, 표 셀에
    넣으면 로고/문서명이 같은 줄에서 각자의 칸을 갖는다(문단 하나에 순서대로
    나열하면 칸 구분이 안 생긴다). (2) 표는 테두리를 그릴 수 있어
    "명확한 사각형/박스형 영역"이라는 이번 task의 요구를 만족한다 — 이는
    baseline이 관찰한 masthead 조판(표로 짜인 상단 영역)과도 일치한다.

    어느 칸이 어느 role인지는 이 함수가 정하지 않는다 — ``masthead.slots``
    (Institution Design Contract의 ``masthead.slots``에서 resolve()가 그대로
    옮긴 값)의 왼쪽→오른쪽 순서를 그대로 읽어 column index를 계산한다
    (masthead-structural-ownership task). 열 개수도 ``len(masthead.slots)``
    에서 오지 리터럴이 아니다 — 다만 이 authoring 버전은 정확히 3개 role
    (logo_left/title/logo_right 각 1개)만 지원하므로 실질적으로 항상 3이다.
    행 개수도 마찬가지로 ``masthead.row_count``에서 온다 — 이 값은 이
    함수가 아니라 resolve()가 검증하며(현재 이 authoring 버전이 지원하는
    유일한 값은 1), 여기서는 리터럴 ``1``을 쓰지 않고 그 필드를 그대로
    전달한다.
    """
    border_fill_id = doc.styles.ensure_border_fill(
        border_width=f"{masthead.border_width_mm} mm",
        border_color=masthead.border_color,
    )
    table = _add_table(
        doc,
        section,
        skeleton_pool,
        rows=masthead.row_count,
        cols=len(masthead.slots),
        border_fill_id_ref=border_fill_id,
        width=round(masthead.width_mm * _HWPUNIT_PER_MM),
        height=round(masthead.height_mm * _HWPUNIT_PER_MM),
    )
    _set_table_cell_margin(table, masthead.cell_margin_mm)

    # 각 칸 폭은 institution이 명시적으로 정한 값을 그대로 쓴다 — 로고
    # 크기나 cell_margin에서 유도하거나 width/3으로 균등 분배하지 않는다
    # (v3 visual QA: 왼쪽 로고 칸이 지나치게 크고 가운데 문서명 칸이
    # 과도하게 비어 보였다). 세 값의 합이 masthead.width_mm과 같음은
    # resolve()가 이미 검증했다. 폭의 나열 순서는 ``masthead.slots``의
    # 순서를 그대로 따른다 — 어느 role이 몇 번째 칸인지 여기서 다시
    # 가정하지 않는다.
    slot_width_by_role = _masthead_slot_width_by_role(masthead)
    table.set_column_widths([slot_width_by_role[role] for role in masthead.slots])

    # 로고/문서명 모두 각자의 칸 안에서 가운데 정렬한다. 문서명의 폰트/크기/
    # 색/굵기는 institution의 title_style_role에서 오지만(_ensure_run_for_style),
    # "칸 안에서 가운데"라는 배치 자체는 masthead 구조 자체가 요구하는
    # 값이라 title_style.align이 아니라 여기서 고정한다 — role의 align은
    # (masthead 밖에서 title role이 쓰일 일이 생기더라도) 그 문맥의 값으로
    # 남겨 둔다.
    center_para_pr_id = _ensure_paragraph_alignment(doc, "CENTER")

    for column_index, role in enumerate(masthead.slots):
        if role == "title":
            _materialize_masthead_title(doc, table, masthead, column_index, center_para_pr_id)
        elif role == "logo_left" and masthead.logo_left is not None:
            _materialize_masthead_logo(doc, table, column_index, masthead.logo_left, center_para_pr_id)
        elif role == "logo_right" and masthead.logo_right is not None:
            _materialize_masthead_logo(doc, table, column_index, masthead.logo_right, center_para_pr_id)

    if masthead.spacing_after_pt is not None:
        doc.styles.apply_paragraph_format(
            paragraph_index=doc.paragraphs.index(table.paragraph),
            spacing_after_pt=masthead.spacing_after_pt,
        )


def _ensure_paragraph_alignment(doc: Any, align: str) -> str:
    """표 셀 문단에 정렬을 적용한다.

    `doc.styles.apply_paragraph_format()`은 `doc.paragraphs`(최상위 문단)
    인덱스로만 대상을 찾아 표 셀 문단에는 쓸 수 없다(표 셀 문단은
    `section.paragraphs`에 잡히지 않는다 — 표 안에 더 깊이 있다). `hwpx`
    라이브러리에 표 셀 전용 정렬 API가 따로 없어, 그 상위 helper가 내부적으로
    쓰는 것과 같은 header 수준 API(`ensure_paragraph_alignment`)로 paraPr id를
    직접 얻어 문단의 `para_pr_id_ref`에 대입한다 — 새 XML 조작이 아니라 이미
    있는 raw id 발급 경로를 한 단계 더 직접 쓰는 것이다.
    """
    header = doc._root.headers[0]
    return header.ensure_paragraph_alignment(align)


def _materialize_masthead_logo(
    doc: Any,
    table: Any,
    col_index: int,
    logo: ResolvedLogo,
    para_pr_id: str,
) -> None:
    asset_path = Path(logo.asset_path)
    image_format = asset_path.suffix.lstrip(".").lower() or "png"
    binary_item = doc.media.add_image(asset_path.read_bytes(), image_format)
    cell = table.cell(0, col_index)
    paragraph = cell.paragraphs[0]
    paragraph.para_pr_id_ref = para_pr_id
    # 새 표 셀은 빈 텍스트 run(`<hp:run><hp:t/></hp:run>`)을 이미 갖고 있다.
    # 그림 run을 추가만 하면 이 빈 텍스트 run이 그대로 남아 build_text_
    # contexts()가 실제로는 아무 의미 없는 "빈 텍스트 노드"까지 하나 더
    # 세게 되고, build_separation_rules()가 그 위치에 규칙을 만들지 않으니
    # semantic classifier가 휴리스틱으로 다시 판정하게 된다 — 이 모듈의
    # 원칙("생성 시점 배치를 그대로 규칙으로 선언, 재추측하지 않음")과
    # 어긋난다. 로고 칸에는 애초에 텍스트가 없어야 하므로 그림을 넣기 전에
    # 기존 빈 run을 지운다.
    for run in list(paragraph.runs):
        paragraph.element.remove(run.element)
    paragraph.add_picture(
        str(binary_item),
        width=round(logo.width_mm * _HWPUNIT_PER_MM),
        height=round(logo.height_mm * _HWPUNIT_PER_MM),
    )


def _materialize_masthead_title(
    doc: Any, table: Any, masthead: ResolvedMasthead, col_index: int, para_pr_id: str
) -> None:
    char_pr = _ensure_run_for_style(doc, masthead.title_style)
    cell = table.cell(0, col_index)
    cell.set_text(masthead.title)
    for paragraph in cell.paragraphs:
        paragraph.char_pr_id_ref = char_pr
        paragraph.para_pr_id_ref = para_pr_id


def _set_table_cell_margin(table: Any, margin_mm: Mapping[str, float]) -> None:
    """표의 `<hp:inMargin>`(셀 안쪽 여백) 속성을 직접 설정한다.

    `doc.add_table()`은 Hancom 기본값(좌우 1.8mm/상하 0.5mm)을 고정으로
    만든다 — 이를 바꾸는 public API가 없다(라이브러리 소스 확인 완료:
    `oxml/table.py`의 `HwpxOxmlTable.create()`가 `_default_cell_inner_
    margin_attributes()`를 그대로 굳혀 넣는다). masthead는 로고가 셀에
    딱 붙지 않도록 그보다 넉넉한 여백이 필요해, 생성된 `<hp:inMargin>`
    엘리먼트의 속성을 직접 덮어쓴다 — 새 엘리먼트를 만들지 않고 기존
    구조에 있는 값만 바꾸는 좁은 조작이다.
    """
    in_margin = table.element.find(f"{{{_HP_NS}}}inMargin")
    if in_margin is None:  # pragma: no cover - defensive: hwpx always creates this
        raise HwpxTemplateAuthoringError("generated table is missing <hp:inMargin>")
    for side in ("left", "right", "top", "bottom"):
        in_margin.set(side, str(round(margin_mm[side] * _HWPUNIT_PER_MM)))
    table.mark_dirty()


def build_separation_rules(
    resolved: ResolvedAuthoringContract,
    source_hwpx: Path | str,
    *,
    section: str = "section0.xml",
) -> dict[str, Any]:
    """Deterministically declare FIXED/CONTENT roles from the same section
    order ``generate_source_hwpx()`` used to materialize *resolved*.

    This does not re-search the generated document by text content (two
    sections could share text). It replays ``resolved.sections`` in the same
    order the generator dispatched them, and matches that order positionally
    against the generated document's actual text nodes (for standalone
    paragraphs) and table indexes (for ``info_table`` sections) — both are
    read once from the real output via ``build_text_contexts()``, not
    assumed. A count mismatch is treated as an authoring/materializer
    inconsistency and raised, not guessed past.
    """
    try:
        with zipfile.ZipFile(source_hwpx) as package:
            entry_name = f"Contents/{section}"
            if entry_name not in package.namelist():
                raise HwpxTemplateAuthoringError(f"generated source is missing {entry_name}")
            root = ET.fromstring(package.read(entry_name))
    except zipfile.BadZipFile as exc:
        raise HwpxTemplateAuthoringError(f"generated source is not a readable HWPX ZIP: {exc}") from exc
    except ET.ParseError as exc:
        raise HwpxTemplateAuthoringError(f"generated source {section} is not well-formed XML: {exc}") from exc

    contexts = build_text_contexts(root, section)
    non_table_contexts = [context for context in contexts if context.location.table is None]
    table_indexes = sorted(
        {context.location.table for context in contexts if context.location.table is not None}
    )

    expected_entries = _expected_non_table_entries(resolved)
    if len(non_table_contexts) != len(expected_entries):
        raise HwpxTemplateAuthoringError(
            f"generated source has {len(non_table_contexts)} non-table text "
            f"node(s), expected {len(expected_entries)} from template_spec.sections; "
            "the generated document structure no longer matches what was authored"
        )
    table_sections = [
        entry
        for entry in resolved.sections
        if isinstance(entry, (ResolvedInfoTableSection, ResolvedSimpleTableSection, ResolvedContentBoxSection))
    ]
    expected_table_count = len(table_sections) + (1 if resolved.masthead is not None else 0)
    if len(table_indexes) != expected_table_count:
        raise HwpxTemplateAuthoringError(
            f"generated source has {len(table_indexes)} table(s), expected "
            f"{expected_table_count} from template_spec.sections"
        )

    rules: list[dict[str, Any]] = []
    for context, (role, placement) in zip(non_table_contexts, expected_entries, strict=True):
        rule: dict[str, Any] = {
            "role": role.value,
            "section": section,
            "text_node_index": context.location.text_node_index,
        }
        if placement is not None and role is TextRole.CONTENT:
            rule["field_id"] = _runtime_field_id(placement)
            if "prototype_level" in placement:
                rule["prototype_level"] = int(placement["prototype_level"])
        rules.append(rule)

    remaining_table_indexes = list(table_indexes)
    if resolved.masthead is not None:
        # masthead는 항상 generate_source_hwpx()가 만드는 첫 번째 표라서
        # table_indexes의 첫 항목이다 — masthead 중앙 셀의 문서명 하나만
        # FIXED_TEXT로 선언하고, 로고 칸은 텍스트 노드 자체가 없어 여기 낄
        # 일이 없다.
        masthead_table_index = remaining_table_indexes.pop(0)
        rules.append(
            {
                "role": TextRole.FIXED_TEXT.value,
                "section": section,
                "table": masthead_table_index,
                "row": 0,
                "col": resolved.masthead.slots.index("title"),
            }
        )
    for table_index, table_section in zip(remaining_table_indexes, table_sections, strict=True):
        if isinstance(table_section, ResolvedInfoTableSection):
            for row_index, row in enumerate(table_section.rows):
                table_row = row_index // table_section.pairs_per_row
                label_column = 2 * (row_index % table_section.pairs_per_row)
                rules.append({"role": TextRole.FIXED_LABEL.value, "section": section, "table": table_index, "row": table_row, "col": label_column})
                content_rule: dict[str, Any] = {"role": TextRole.CONTENT.value, "section": section, "table": table_index, "row": table_row, "col": label_column + 1}
                if resolved.semantic_placements:
                    content_rule["field_id"] = row.field_id
                rules.append(content_rule)
        elif isinstance(table_section, ResolvedContentBoxSection):
            for row_index, item in enumerate(table_section.items):
                content_rule = {"role": TextRole.CONTENT.value, "section": section, "table": table_index, "row": row_index, "col": 0}
                if resolved.semantic_placements:
                    content_rule["field_id"] = item.field_id
                rules.append(content_rule)
        else:
            for column_index in range(len(table_section.column_widths)):
                if table_section.header:
                    rules.append({"role": TextRole.FIXED_LABEL.value, "section": section, "table": table_index, "row": 0, "col": column_index})
            row_offset = 1 if table_section.header else 0
            for row_index, row in enumerate(table_section.rows, start=row_offset):
                for column_index, _ in enumerate(row):
                    rules.append({"role": TextRole.CONTENT.value, "section": section, "table": table_index, "row": row_index, "col": column_index, "field_id": f"{table_section.collection_field_id}[{row_index - row_offset}].{table_section.item_fields[column_index]}"})
    return {"rules": rules}


def _runtime_field_id(placement: Mapping[str, str]) -> str:
    item_field = placement.get("item_field")
    materialized_index = placement.get("materialized_index")
    if item_field is None or materialized_index is None:
        return placement["field_id"]
    return f"{placement['field_id']}[{materialized_index}].{item_field}"


def _expected_non_table_entries(
    resolved: ResolvedAuthoringContract,
) -> tuple[tuple[TextRole, Mapping[str, str] | None], ...]:
    """The (role, semantic placement) of every standalone (non-table)
    paragraph ``generate_source_hwpx()`` emits, in the same order it emits
    them. The placement half is ``None`` when *resolved* carries no semantic
    placements (legacy/no-semantic-contract path) — only the role is used
    then.

    ``ResolvedInfoTableSection`` contributes no standalone paragraph — its
    cells are handled separately by table index in
    ``build_separation_rules()``. When a masthead is present, a
    ``ResolvedTitleSection`` contributes no standalone paragraph either — its
    text was consumed by the masthead's center cell (also handled separately,
    as the masthead's own table entry). A non-hierarchy ``ResolvedBodySection``
    with ``heading_style is None`` contributes only its content paragraph, no
    heading paragraph. All three exclusions must be applied consistently
    whether or not semantic placements are in play, or the (role, placement)
    pairing drifts out of alignment with the roles actually materialized —
    this single function is the one place that decides it.
    """
    if resolved.semantic_placements:
        by_section_index: dict[int, list[Mapping[str, str]]] = {}
        for placement in resolved.semantic_placements:
            if "row_index" in placement:
                continue
            by_section_index.setdefault(int(placement["section_index"]), []).append(placement)
        pairs: list[tuple[TextRole, Mapping[str, str] | None]] = []
        for section_index, entry in enumerate(resolved.sections):
            if isinstance(entry, (ResolvedInfoTableSection, ResolvedSimpleTableSection)):
                continue
            if resolved.masthead is not None and isinstance(entry, ResolvedTitleSection):
                continue
            for placement in by_section_index.get(section_index, []):
                pairs.append((_semantic_text_role(placement["role"]), placement))
        return tuple(pairs)
    pairs = []
    for entry in resolved.sections:
        if isinstance(entry, ResolvedTitleSection):
            if resolved.masthead is not None:
                continue
            pairs.append((TextRole.FIXED_TEXT, None))
        elif isinstance(entry, ResolvedBodySection):
            if entry.hierarchy_items:
                pairs.extend((TextRole.CONTENT, None) for _ in entry.hierarchy_items)
            else:
                if entry.heading_style is not None:
                    pairs.append((TextRole.FIXED_TEXT, None))
                pairs.append((TextRole.CONTENT, None))
    return tuple(pairs)


def _semantic_text_role(value: str) -> TextRole:
    mapping = {
        "CONTENT": TextRole.CONTENT,
        "FIXED_LABEL": TextRole.FIXED_LABEL,
        "FIXED_TEXT": TextRole.FIXED_TEXT,
    }
    try:
        return mapping[value]
    except KeyError as exc:
        raise HwpxTemplateAuthoringError(
            f"unsupported semantic role in resolved placement: {value!r}"
        ) from exc




def write_separation_rules(rules: dict[str, Any], output_path: Path | str) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output


__all__ = [
    "HwpxTemplateAuthoringError",
    "TemplateSpec",
    "TitleSection",
    "InfoTableSection",
    "InfoTableRow",
    "BodySection",
    "ResolvedTextStyle",
    "ResolvedTableStyle",
    "ResolvedLogo",
    "ResolvedMasthead",
    "ResolvedTitleSection",
    "ResolvedInfoTableSection",
    "ResolvedBodySection",
    "ResolvedAuthoringContract",
    "load_template_spec",
    "generate_source_hwpx",
    "build_separation_rules",
    "write_separation_rules",
    "run_skill_subprocess",
]
