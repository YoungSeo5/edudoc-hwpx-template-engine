"""Resolve a ``TemplateSpec`` + Institution Design Contract into a
``ResolvedAuthoringContract``.

이 모듈은 institution-design-contract-v1 task의 핵심 신규 코드다. 배경은
``core.adapters.hwpx_template_authoring`` 모듈 docstring과
``docs/tasks/institution-design-contract-v1.md``에 있다 — 요약하면:
``TemplateSpec``의 section들은 institution style role **이름**만 들고 있고,
그 role의 실제 font/size/color/bold/align 값은 여기서만 조회한다.
``generate_source_hwpx()``는 이 모듈이 만든 ``ResolvedAuthoringContract``만
소비하며, style 해석·institution default 조회·override 병합을 스스로 하지
않는다 — 그 판단은 전부 여기, ``resolve()`` 한 곳에서 끝난다.

책임:

1. Institution Design Contract 로드/입력 검증(``load_institution_design_contract()``).
2. ``TemplateSpec`` 각 section이 참조하는 style role 이름을 그 계약의
   ``defaults.styles``(문자 style) / ``defaults.table``(표 style)에서 조회한다.
   어느 네임스페이스에서 찾는지 자체가 section 종류 ↔ role 종류 호환성
   검사다 — title/body_section의 style은 항상 ``defaults.styles``에서만,
   info_table의 style은 항상 ``defaults.table``에서만 찾는다. 존재하지
   않는 이름, 또는 잘못된 네임스페이스(예: table role 이름을 title의
   style로 참조)는 여기서 실패한다.
3. ``TemplateSpec``의 (있다면) override를 병합한다 — allow-list 밖의 key를
   override하면 실패한다(기관 정체성 값을 문서가 임의로 덮어쓰지 못하게).
4. 병합 후에도 필수 속성(font_family/size_pt/color/bold/align, 표는
   width_mm/border_width_mm/border_color/label_style_role/value_style_role)이
   비어 있으면 실패한다 — ``hwpx`` skeleton 기본값으로 넘어가지 않는다.
5. 완전히 확정된 ``ResolvedAuthoringContract``를 반환한다.

override 허용 범위(Decision 1, 이번 task의 확정 결정): 문서별로 바꿀 수 있는
것은 텍스트 style의 ``size_pt``/``align``, 표 style의 ``width_mm``뿐이다.
``font_family``/``color``/``bold``와 표의 ``border_width_mm``/``border_color``/
``label_style_role``/``value_style_role``은 기관 정체성 값이라 TemplateSpec이
override할 수 없다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .hwpx_template_authoring import (
    BodySection,
    InfoTableSection,
    ResolvedAuthoringContract,
    ResolvedBodySection,
    ResolvedInfoTableSection,
    ResolvedLogo,
    ResolvedMasthead,
    ResolvedSection,
    ResolvedTableStyle,
    ResolvedTextStyle,
    ResolvedTitleSection,
    Section,
    TemplateSpec,
    TitleSection,
    _VALID_ALIGNS,
)
from .hwpx_semantic_contract import SemanticBinding

_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

_TEXT_ROLE_REQUIRED = ("font_family", "size_pt", "color", "bold", "align")
_TEXT_ROLE_OPTIONAL_NUMERIC = (
    "line_spacing_percent",
    "spacing_before_pt",
    "spacing_after_pt",
    "indent_left_mm",
)
_TABLE_ROLE_REQUIRED = (
    "width_mm",
    "border_width_mm",
    "border_color",
    "label_style_role",
    "value_style_role",
    "label_width_ratio",
)
#: 문서 최상단 masthead가 실제로 필요할 때(``masthead.default == "required"``)
#: Institution Design Contract가 반드시 갖춰야 하는 속성. 하나라도 없으면
#: resolve()는 실패한다 — masthead 없이 조용히 넘어가거나 빈 박스를 만들지
#: 않는다.
_MASTHEAD_REQUIRED_WHEN_ACTIVE = (
    "width_mm",
    "height_mm",
    "border_width_mm",
    "border_color",
    "cell_margin_mm",
    "title_style_role",
    "logo_left_asset_id",
    "logo_left_width_mm",
    "logo_left_height_mm",
    "logo_right_asset_id",
    "logo_right_width_mm",
    "logo_right_height_mm",
    "logo_left_slot_width_mm",
    "title_slot_width_mm",
    "logo_right_slot_width_mm",
)
#: 세 칸 폭 합이 masthead.width_mm과 벌어질 수 있는 최대 오차(mm) — 부동소수
#: 반올림만 허용하고, "대략 맞음"은 통과시키지 않는다.
_MASTHEAD_SLOT_WIDTH_TOLERANCE_MM = 0.01
_CELL_MARGIN_SIDES = ("left", "right", "top", "bottom")

#: Decision 1의 확정 allow-list. 기관 정체성 값(font_family/color/bold/표
#: border/표 label·value role 참조)은 여기 없다 — 문서가 override할 수 없다.
_TEXT_OVERRIDE_ALLOWED_KEYS = frozenset({"size_pt", "align"})
_TABLE_OVERRIDE_ALLOWED_KEYS = frozenset({"width_mm"})


class HwpxAuthoringResolveError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 1. Institution Design Contract 로드/입력 검증.
# ---------------------------------------------------------------------------


def load_institution_design_contract(path: Path | str) -> dict[str, Any]:
    """Load and validate an Institution Design Contract against the shape
    declared in ``docs/contracts/institution-design-contract.schema.json``.

    Returns ``{"styles": {...}, "table": {...}, "masthead": {...}, "assets":
    {asset_id: absolute_path}}`` — only the parsed sub-shape ``resolve()``
    actually consumes. A missing file, invalid JSON, or a role/masthead/asset
    that fails schema-required-property/type checks raises before any
    ``TemplateSpec`` section is examined. Asset ``path`` values are resolved
    relative to *path*'s own directory and the referenced file's existence is
    checked here — a dangling asset reference is a load-time failure, not a
    materialize-time crash.
    """
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HwpxAuthoringResolveError(
            f"cannot read institution design contract: {source} ({exc})"
        ) from exc
    if not isinstance(data, dict):
        raise HwpxAuthoringResolveError(
            f"institution design contract root must be an object: {source}"
        )

    required_top_level = (
        "institution_design_version",
        "institution",
        "design_id",
        "evidence_reference",
        "defaults",
        "masthead",
    )
    missing_top_level = [key for key in required_top_level if key not in data]
    if missing_top_level:
        raise HwpxAuthoringResolveError(
            f"institution design contract {source} is missing required key(s): {missing_top_level}"
        )

    defaults = data["defaults"]
    if not isinstance(defaults, dict):
        raise HwpxAuthoringResolveError(
            f"institution design contract {source}: 'defaults' must be an object"
        )

    styles_raw = defaults.get("styles", {})
    if not isinstance(styles_raw, dict):
        raise HwpxAuthoringResolveError(
            f"institution design contract {source}: 'defaults.styles' must be an object"
        )
    table_raw = defaults.get("table", {})
    if not isinstance(table_raw, dict):
        raise HwpxAuthoringResolveError(
            f"institution design contract {source}: 'defaults.table' must be an object"
        )

    styles = {name: _parse_institution_text_role(name, value) for name, value in styles_raw.items()}
    table = {name: _parse_institution_table_role(name, value) for name, value in table_raw.items()}
    masthead = _parse_institution_masthead(data["masthead"])
    assets = _parse_institution_assets(source.parent, data.get("assets", []))
    return {"styles": styles, "table": table, "masthead": masthead, "assets": assets}


def _parse_positive_number(context: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise HwpxAuthoringResolveError(f"{context} must be a positive number")
    return float(value)


def _parse_nonnegative_number(context: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise HwpxAuthoringResolveError(f"{context} must be a non-negative number")
    return float(value)


def _parse_hex_color(context: str, value: Any) -> str:
    if not isinstance(value, str) or not _COLOR_PATTERN.match(value):
        raise HwpxAuthoringResolveError(f"{context} must be a '#RRGGBB' hex color string")
    return value


def _parse_institution_text_role(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HwpxAuthoringResolveError(f"defaults.styles.{name} must be an object")
    missing = [key for key in _TEXT_ROLE_REQUIRED if value.get(key) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"defaults.styles.{name} is missing required propert"
            f"{'y' if len(missing) == 1 else 'ies'}: {missing}"
        )

    font_family = value["font_family"]
    if not isinstance(font_family, str) or not font_family.strip():
        raise HwpxAuthoringResolveError(f"defaults.styles.{name}.font_family must be a non-empty string")
    bold = value["bold"]
    if not isinstance(bold, bool):
        raise HwpxAuthoringResolveError(f"defaults.styles.{name}.bold must be a boolean")
    align = value["align"]
    if align not in _VALID_ALIGNS:
        raise HwpxAuthoringResolveError(
            f"defaults.styles.{name}.align must be one of {_VALID_ALIGNS}, got {align!r}"
        )

    parsed: dict[str, Any] = {
        "font_family": font_family,
        "size_pt": _parse_positive_number(f"defaults.styles.{name}.size_pt", value["size_pt"]),
        "color": _parse_hex_color(f"defaults.styles.{name}.color", value["color"]),
        "bold": bold,
        "align": align,
    }
    if "line_spacing_percent" in value and value["line_spacing_percent"] is not None:
        parsed["line_spacing_percent"] = _parse_positive_number(
            f"defaults.styles.{name}.line_spacing_percent", value["line_spacing_percent"]
        )
    for key in ("spacing_before_pt", "spacing_after_pt", "indent_left_mm"):
        if key in value and value[key] is not None:
            parsed[key] = _parse_nonnegative_number(f"defaults.styles.{name}.{key}", value[key])
    if "heading_rule_width_mm" in value and value["heading_rule_width_mm"] is not None:
        parsed["heading_rule_width_mm"] = _parse_positive_number(
            f"defaults.styles.{name}.heading_rule_width_mm", value["heading_rule_width_mm"]
        )
    if "marker" in value and value["marker"] is not None:
        marker = value["marker"]
        if not isinstance(marker, str) or not marker:
            raise HwpxAuthoringResolveError(f"defaults.styles.{name}.marker must be a non-empty string")
        parsed["marker"] = marker
    return parsed


def _parse_institution_table_role(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HwpxAuthoringResolveError(f"defaults.table.{name} must be an object")
    missing = [key for key in _TABLE_ROLE_REQUIRED if value.get(key) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"defaults.table.{name} is missing required propert"
            f"{'y' if len(missing) == 1 else 'ies'}: {missing}"
        )

    label_style_role = value["label_style_role"]
    if not isinstance(label_style_role, str) or not label_style_role.strip():
        raise HwpxAuthoringResolveError(
            f"defaults.table.{name}.label_style_role must be a non-empty string"
        )
    value_style_role = value["value_style_role"]
    if not isinstance(value_style_role, str) or not value_style_role.strip():
        raise HwpxAuthoringResolveError(
            f"defaults.table.{name}.value_style_role must be a non-empty string"
        )
    label_width_ratio = value["label_width_ratio"]
    if (
        not isinstance(label_width_ratio, (int, float))
        or isinstance(label_width_ratio, bool)
        or not (0 < label_width_ratio < 1)
    ):
        raise HwpxAuthoringResolveError(
            f"defaults.table.{name}.label_width_ratio must be a number strictly between 0 and 1"
        )

    return {
        "width_mm": _parse_positive_number(f"defaults.table.{name}.width_mm", value["width_mm"]),
        "border_width_mm": _parse_positive_number(
            f"defaults.table.{name}.border_width_mm", value["border_width_mm"]
        ),
        "border_color": _parse_hex_color(f"defaults.table.{name}.border_color", value["border_color"]),
        "label_style_role": label_style_role,
        "value_style_role": value_style_role,
        "label_width_ratio": float(label_width_ratio),
    }


def _parse_institution_masthead(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HwpxAuthoringResolveError("institution design contract 'masthead' must be an object")
    default = value.get("default")
    if default not in ("required", "none"):
        raise HwpxAuthoringResolveError("masthead.default must be 'required' or 'none'")
    if default != "required":
        # default가 'none'이면 이번 문서는 masthead를 쓰지 않는다 — 나머지
        # masthead 속성(로고/치수 등)은 요구하지도, 읽지도 않는다.
        return {"default": default}

    missing = [key for key in _MASTHEAD_REQUIRED_WHEN_ACTIVE if value.get(key) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"institution design masthead.default='required' but is missing required "
            f"propert{'y' if len(missing) == 1 else 'ies'}: {missing}"
        )

    parsed: dict[str, Any] = {
        "default": default,
        "width_mm": _parse_positive_number("masthead.width_mm", value["width_mm"]),
        "height_mm": _parse_positive_number("masthead.height_mm", value["height_mm"]),
        "border_width_mm": _parse_positive_number("masthead.border_width_mm", value["border_width_mm"]),
        "border_color": _parse_hex_color("masthead.border_color", value["border_color"]),
        "cell_margin_mm": _parse_cell_margin("masthead.cell_margin_mm", value["cell_margin_mm"]),
    }
    title_style_role = value["title_style_role"]
    if not isinstance(title_style_role, str) or not title_style_role.strip():
        raise HwpxAuthoringResolveError("masthead.title_style_role must be a non-empty string")
    parsed["title_style_role"] = title_style_role

    for side in ("left", "right"):
        asset_key = f"logo_{side}_asset_id"
        asset_id = value[asset_key]
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise HwpxAuthoringResolveError(f"masthead.{asset_key} must be a non-empty string")
        parsed[asset_key] = asset_id
        parsed[f"logo_{side}_width_mm"] = _parse_positive_number(
            f"masthead.logo_{side}_width_mm", value[f"logo_{side}_width_mm"]
        )
        parsed[f"logo_{side}_height_mm"] = _parse_positive_number(
            f"masthead.logo_{side}_height_mm", value[f"logo_{side}_height_mm"]
        )

    # 세 칸 폭은 institution이 명시적으로 정한 값이어야 한다 — 로고 크기나
    # cell_margin에서 암묵적으로 유도하거나 width/3으로 균등 분배하지 않는다
    # (v3 visual QA: 왼쪽 로고 칸은 지나치게 크고 가운데 문서명 칸은 과도하게
    # 넓어 보였다 — 이는 칸 폭이 "로고 크기 + 여백"으로만 계산돼 institution이
    # 실제로 결정할 수 있는 값이 아니었기 때문이다).
    slot_keys = ("logo_left_slot_width_mm", "title_slot_width_mm", "logo_right_slot_width_mm")
    for key in slot_keys:
        parsed[key] = _parse_positive_number(f"masthead.{key}", value[key])
    slot_total = sum(parsed[key] for key in slot_keys)
    if abs(slot_total - parsed["width_mm"]) > _MASTHEAD_SLOT_WIDTH_TOLERANCE_MM:
        raise HwpxAuthoringResolveError(
            "masthead.logo_left_slot_width_mm + title_slot_width_mm + "
            f"logo_right_slot_width_mm ({slot_total}) must equal masthead.width_mm "
            f"({parsed['width_mm']})"
        )

    if "spacing_after_pt" in value and value["spacing_after_pt"] is not None:
        parsed["spacing_after_pt"] = _parse_nonnegative_number(
            "masthead.spacing_after_pt", value["spacing_after_pt"]
        )
    return parsed


def _parse_cell_margin(context: str, value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise HwpxAuthoringResolveError(f"{context} must be an object")
    missing = [side for side in _CELL_MARGIN_SIDES if value.get(side) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"{context} is missing required side{'s' if len(missing) != 1 else ''}: {missing}"
        )
    return {side: _parse_nonnegative_number(f"{context}.{side}", value[side]) for side in _CELL_MARGIN_SIDES}


def _parse_institution_assets(base_dir: Path, raw: Any) -> dict[str, Path]:
    if not isinstance(raw, list):
        raise HwpxAuthoringResolveError("institution design contract 'assets' must be an array")
    assets: dict[str, Path] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HwpxAuthoringResolveError(f"assets[{index}] must be an object")
        asset_id = item.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise HwpxAuthoringResolveError(f"assets[{index}].asset_id must be a non-empty string")
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise HwpxAuthoringResolveError(f"assets[{index}].path must be a non-empty string")
        resolved_path = (base_dir / path_value).resolve()
        if not resolved_path.is_file():
            raise HwpxAuthoringResolveError(
                f"assets[{index}] ({asset_id!r}) file does not exist: {resolved_path}"
            )
        assets[asset_id] = resolved_path
    return assets


# ---------------------------------------------------------------------------
# 2-5. role 조회 + override 병합 + 완결성 검증.
# ---------------------------------------------------------------------------


def resolve(
    institution_design_path: Path | str,
    spec: TemplateSpec,
    semantic_binding: SemanticBinding | None = None,
) -> ResolvedAuthoringContract:
    """Resolve *spec* against the Institution Design Contract at
    *institution_design_path* into a ``ResolvedAuthoringContract``.

    Raises ``HwpxAuthoringResolveError`` — never falls back to an ``hwpx``
    library skeleton default — when a referenced role does not exist, an
    override key is outside the allow-list, or a role is missing a required
    property after merge. ``generate_source_hwpx()`` must never be reached
    with an unresolved value; this function is where that is decided.

    Page margins are not merged here: ``TemplateSpec.page_margins_mm`` is
    already fully required (every one of ``left``/``right``/``top``/``bottom``)
    by ``load_template_spec()``, so there is no gap for an institution
    ``defaults.page`` value to fill in this version.
    """
    design = load_institution_design_contract(institution_design_path)
    styles = design["styles"]
    tables = design["table"]

    resolved_sections: list[ResolvedSection] = [
        _resolve_section(entry, styles, tables) for entry in spec.sections
    ]
    masthead = _resolve_masthead(design["masthead"], design["assets"], styles, spec)
    return ResolvedAuthoringContract(
        page_margins_mm=spec.page_margins_mm,
        sections=tuple(resolved_sections),
        semantic_contract_id=(
            semantic_binding.contract.contract_id if semantic_binding is not None else None
        ),
        institution_design_id=spec.institution_design_id,
        semantic_placements=(
            semantic_binding.placements if semantic_binding is not None else ()
        ),
        masthead=masthead,
    )


def _resolve_masthead(
    design_masthead: Mapping[str, Any],
    assets: Mapping[str, Path],
    styles: Mapping[str, Mapping[str, Any]],
    spec: TemplateSpec,
) -> ResolvedMasthead | None:
    if design_masthead.get("default") != "required":
        return None
    title_section = next(
        (entry for entry in spec.sections if isinstance(entry, TitleSection)), None
    )
    if title_section is None:
        raise HwpxAuthoringResolveError(
            "institution design requires a masthead (masthead.default='required') but "
            "template_spec has no 'title' section to supply the document name"
        )
    title_style = _resolve_text_role(
        styles,
        design_masthead["title_style_role"],
        {},
        context="masthead title_style_role",
    )
    return ResolvedMasthead(
        title=title_section.text,
        title_style=title_style,
        width_mm=design_masthead["width_mm"],
        height_mm=design_masthead["height_mm"],
        border_width_mm=design_masthead["border_width_mm"],
        border_color=design_masthead["border_color"],
        cell_margin_mm=design_masthead["cell_margin_mm"],
        spacing_after_pt=design_masthead.get("spacing_after_pt"),
        logo_left=_resolve_masthead_logo(assets, design_masthead, "left"),
        logo_right=_resolve_masthead_logo(assets, design_masthead, "right"),
        logo_left_slot_width_mm=design_masthead["logo_left_slot_width_mm"],
        title_slot_width_mm=design_masthead["title_slot_width_mm"],
        logo_right_slot_width_mm=design_masthead["logo_right_slot_width_mm"],
    )


def _resolve_masthead_logo(
    assets: Mapping[str, Path], design_masthead: Mapping[str, Any], side: str
) -> ResolvedLogo:
    asset_id = design_masthead[f"logo_{side}_asset_id"]
    asset_path = assets.get(asset_id)
    if asset_path is None:
        raise HwpxAuthoringResolveError(
            f"masthead logo_{side}_asset_id references undefined asset {asset_id!r}; "
            "declare it under the Institution Design Contract's assets"
        )
    return ResolvedLogo(
        asset_path=str(asset_path),
        width_mm=design_masthead[f"logo_{side}_width_mm"],
        height_mm=design_masthead[f"logo_{side}_height_mm"],
    )


def _resolve_section(
    entry: Section,
    styles: Mapping[str, Mapping[str, Any]],
    tables: Mapping[str, Mapping[str, Any]],
) -> ResolvedSection:
    if isinstance(entry, TitleSection):
        style = _resolve_text_role(
            styles, entry.style, entry.style_override, context=f"title section style {entry.style!r}"
        )
        return ResolvedTitleSection(style=style, text=entry.text)
    if isinstance(entry, BodySection):
        heading_style = _resolve_text_role(
            styles,
            entry.heading_style,
            entry.heading_style_override,
            context=f"body_section heading_style {entry.heading_style!r}",
        )
        body_style = _resolve_text_role(
            styles,
            entry.body_style,
            entry.body_style_override,
            context=f"body_section body_style {entry.body_style!r}",
        )
        return ResolvedBodySection(
            heading_style=heading_style,
            body_style=body_style,
            heading_text=entry.heading_text,
            field_id=entry.field_id,
            sample_value=entry.sample_value,
        )
    if isinstance(entry, InfoTableSection):
        table_style = _resolve_table_role(
            tables,
            styles,
            entry.style,
            entry.style_override,
            entry.label_style_override,
            entry.value_style_override,
        )
        return ResolvedInfoTableSection(style=table_style, rows=entry.rows)
    raise HwpxAuthoringResolveError(f"unhandled section type: {entry!r}")  # pragma: no cover


def _resolve_text_role(
    styles: Mapping[str, Mapping[str, Any]],
    role_name: str,
    override: Mapping[str, Any],
    *,
    context: str,
) -> ResolvedTextStyle:
    role = styles.get(role_name)
    if role is None:
        raise HwpxAuthoringResolveError(
            f"{context} references undefined style role {role_name!r}; declare it under "
            "the Institution Design Contract's defaults.styles"
        )

    merged = dict(role)
    for key in override:
        if key not in _TEXT_OVERRIDE_ALLOWED_KEYS:
            raise HwpxAuthoringResolveError(
                f"{context}: style_override cannot set {key!r}; only "
                f"{sorted(_TEXT_OVERRIDE_ALLOWED_KEYS)} may be overridden by a TemplateSpec "
                "for a text style role — font/color/weight are institution identity"
            )
    if "size_pt" in override:
        merged["size_pt"] = _parse_positive_number(f"{context} style_override.size_pt", override["size_pt"])
    if "align" in override:
        align = override["align"]
        if align not in _VALID_ALIGNS:
            raise HwpxAuthoringResolveError(
                f"{context} style_override.align must be one of {_VALID_ALIGNS}, got {align!r}"
            )
        merged["align"] = align

    missing = [key for key in _TEXT_ROLE_REQUIRED if merged.get(key) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"{context} (role {role_name!r}) is missing required propert"
            f"{'y' if len(missing) == 1 else 'ies'} after merge: {missing}"
        )

    return ResolvedTextStyle(
        font_family=merged["font_family"],
        size_pt=float(merged["size_pt"]),
        color=merged["color"],
        bold=bool(merged["bold"]),
        align=merged["align"],
        line_spacing_percent=merged.get("line_spacing_percent"),
        spacing_before_pt=merged.get("spacing_before_pt"),
        spacing_after_pt=merged.get("spacing_after_pt"),
        indent_left_mm=merged.get("indent_left_mm"),
        heading_rule_width_mm=merged.get("heading_rule_width_mm"),
        marker=merged.get("marker"),
    )


def _resolve_table_role(
    tables: Mapping[str, Mapping[str, Any]],
    styles: Mapping[str, Mapping[str, Any]],
    role_name: str,
    override: Mapping[str, Any],
    label_style_override: Mapping[str, Any],
    value_style_override: Mapping[str, Any],
) -> ResolvedTableStyle:
    role = tables.get(role_name)
    if role is None:
        raise HwpxAuthoringResolveError(
            f"info_table style references undefined table role {role_name!r}; declare it "
            "under the Institution Design Contract's defaults.table"
        )

    merged = dict(role)
    for key in override:
        if key not in _TABLE_OVERRIDE_ALLOWED_KEYS:
            raise HwpxAuthoringResolveError(
                f"info_table style {role_name!r}: style_override cannot set {key!r}; only "
                f"{sorted(_TABLE_OVERRIDE_ALLOWED_KEYS)} may be overridden by a TemplateSpec "
                "for a table style role — border/label/value are institution identity"
            )
    if "width_mm" in override:
        merged["width_mm"] = _parse_positive_number(
            f"info_table {role_name!r} style_override.width_mm", override["width_mm"]
        )

    missing = [key for key in _TABLE_ROLE_REQUIRED if merged.get(key) is None]
    if missing:
        raise HwpxAuthoringResolveError(
            f"info_table table role {role_name!r} is missing required propert"
            f"{'y' if len(missing) == 1 else 'ies'} after merge: {missing}"
        )

    label_style = _resolve_text_role(
        styles,
        merged["label_style_role"],
        label_style_override,
        context=f"info_table {role_name!r} label_style_role",
    )
    value_style = _resolve_text_role(
        styles,
        merged["value_style_role"],
        value_style_override,
        context=f"info_table {role_name!r} value_style_role",
    )
    return ResolvedTableStyle(
        width_mm=float(merged["width_mm"]),
        border_width_mm=float(merged["border_width_mm"]),
        border_color=merged["border_color"],
        label_style=label_style,
        value_style=value_style,
        label_width_ratio=float(merged["label_width_ratio"]),
    )


__all__ = [
    "HwpxAuthoringResolveError",
    "load_institution_design_contract",
    "resolve",
]
