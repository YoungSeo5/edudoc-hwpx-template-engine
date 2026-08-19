"""core.adapters.hwpx_authoring_resolve.resolve() unit tests.

institution-design-contract-v1 task의 핵심 신규 동작을 검증한다:
Institution Design Contract(role별 typography/table 기본값) +
``TemplateSpec``(role 이름 참조 + 제한된 override) -> 완전히 확정된
``ResolvedAuthoringContract``. 기존 ``hwpx_template_authoring.py`` 테스트
(``test_hwpx_template_authoring_weekly_report.py``)는 실제 weekly_report
authoring 파이프라인 전체(resolve() -> generate_source_hwpx() -> 생성된
HWPX XML)를 검증하고, 이 파일은 그 앞 단계인 ``resolve()`` 자체의 병합·
검증 규칙만 독립적으로 검증한다.

검증 대상:

A. institution default + 허용된 override -> 완전히 확정된 결과 (모든 필수
   속성이 non-null).
B. 금지된 override(font_family/color/bold, 표의 border/label_style_role/
   value_style_role) -> 실패. institution 정체성 값을 TemplateSpec이 임의로
   덮어쓸 수 없다는 Decision 1의 직접 증거.
C. institution design에 필수 속성(예: color)이 아예 없으면 실패 —
   hwpx skeleton으로 넘어가지 않는다는 이번 task의 핵심 조건.
D. section 종류 ↔ role 종류가 맞지 않는 참조(text 자리에 table role 이름,
   또는 존재하지 않는 이름) 거부.
E. info_table의 label/value가 서로 다른 typography role로 해석될 수 있다.
F. 표 style_override는 ``width_mm``만 허용되고 border/역할 참조는 금지된다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_authoring_resolve import (  # noqa: E402
    HwpxAuthoringResolveError,
    resolve,
)
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    InfoTableRow,
    InfoTableSection,
    TemplateSpec,
    TitleSection,
)

_PAGE_MARGINS_MM = {"left": 20.0, "right": 20.0, "top": 10.0, "bottom": 10.0}

_BASE_TEXT_ROLE: dict[str, Any] = {
    "font_family": "테스트고딕",
    "size_pt": 16,
    "color": "#123456",
    "bold": True,
    "align": "left",
}


def _write_institution_design(
    tmp_path: Path,
    styles: dict[str, Any],
    table: dict[str, Any] | None = None,
    *,
    name: str = "design.json",
) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "institution_design_version": "v1",
                "institution": "test-institution",
                "design_id": "test-design-v1",
                "evidence_reference": "docs/hwpx-layout-baseline.md",
                "defaults": {"page": {}, "styles": styles, "table": table or {}},
                "masthead": {"default": "none", "document_override_allowed": True},
                "assets": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _title_spec(style: str, override: dict[str, Any] | None = None) -> TemplateSpec:
    return TemplateSpec(
        template_spec_version="authoring-v2",
        page_margins_mm=_PAGE_MARGINS_MM,
        sections=(TitleSection(style=style, style_override=override or {}, text="제목"),),
    )


def _info_table_spec(
    table_role: str,
    *,
    style_override: dict[str, Any] | None = None,
    label_style_override: dict[str, Any] | None = None,
    value_style_override: dict[str, Any] | None = None,
) -> TemplateSpec:
    return TemplateSpec(
        template_spec_version="authoring-v2",
        page_margins_mm=_PAGE_MARGINS_MM,
        sections=(
            InfoTableSection(
                style=table_role,
                style_override=style_override or {},
                label_style_override=label_style_override or {},
                value_style_override=value_style_override or {},
                rows=(InfoTableRow(label="제목", field_id="f1", sample_value="v1"),),
            ),
        ),
    )


_INFO_TABLE_ROLE = {
    "width_mm": 170.0,
    "border_width_mm": 0.12,
    "border_color": "#BFBFBF",
    "label_style_role": "body",
    "value_style_role": "body",
    "label_width_ratio": 0.22,
}


# ---------------------------------------------------------------------------
# A. institution default + 허용된 override -> 완전히 확정된 결과.
# ---------------------------------------------------------------------------


def test_resolve_produces_fully_concrete_style_from_institution_default(tmp_path: Path) -> None:
    design_path = _write_institution_design(tmp_path, {"body": dict(_BASE_TEXT_ROLE)})
    spec = _title_spec("body")

    resolved = resolve(design_path, spec)
    style = resolved.sections[0].style

    assert style.font_family == "테스트고딕"
    assert style.size_pt == 16
    assert style.color == "#123456"
    assert style.bold is True
    assert style.align == "left"


def test_resolve_applies_allow_listed_override_without_changing_other_properties(
    tmp_path: Path,
) -> None:
    design_path = _write_institution_design(tmp_path, {"body": dict(_BASE_TEXT_ROLE)})
    spec = _title_spec("body", override={"size_pt": 20, "align": "center"})

    resolved = resolve(design_path, spec)
    style = resolved.sections[0].style

    assert style.size_pt == 20
    assert style.align == "center"
    # override되지 않은 속성은 institution 기본값 그대로 남는다.
    assert style.font_family == "테스트고딕"
    assert style.color == "#123456"
    assert style.bold is True


# ---------------------------------------------------------------------------
# B. 금지된 override(institution identity 값) -> 실패.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_key,forbidden_value",
    [("font_family", "다른 폰트"), ("color", "#FFFFFF"), ("bold", False)],
)
def test_resolve_rejects_forbidden_style_override(
    tmp_path: Path, forbidden_key: str, forbidden_value: Any
) -> None:
    design_path = _write_institution_design(tmp_path, {"body": dict(_BASE_TEXT_ROLE)})
    spec = _title_spec("body", override={forbidden_key: forbidden_value})

    with pytest.raises(HwpxAuthoringResolveError, match=forbidden_key):
        resolve(design_path, spec)


def test_resolve_rejects_table_border_and_role_reference_override(tmp_path: Path) -> None:
    design_path = _write_institution_design(
        tmp_path, {"body": dict(_BASE_TEXT_ROLE)}, {"info_table": dict(_INFO_TABLE_ROLE)}
    )

    with pytest.raises(HwpxAuthoringResolveError, match="border_width_mm"):
        resolve(
            design_path,
            _info_table_spec("info_table", style_override={"border_width_mm": 1.0}),
        )
    with pytest.raises(HwpxAuthoringResolveError, match="label_style_role"):
        resolve(
            design_path,
            _info_table_spec("info_table", style_override={"label_style_role": "other"}),
        )


# ---------------------------------------------------------------------------
# C. institution design에 필수 속성이 없으면 실패 — skeleton fallback 없음.
# ---------------------------------------------------------------------------


def test_resolve_rejects_role_missing_required_property(tmp_path: Path) -> None:
    incomplete_role = {key: value for key, value in _BASE_TEXT_ROLE.items() if key != "color"}
    design_path = _write_institution_design(tmp_path, {"body": incomplete_role})

    with pytest.raises(HwpxAuthoringResolveError, match="color"):
        resolve(design_path, _title_spec("body"))


def test_resolve_rejects_table_role_missing_required_property(tmp_path: Path) -> None:
    incomplete_table_role = {
        key: value for key, value in _INFO_TABLE_ROLE.items() if key != "border_color"
    }
    design_path = _write_institution_design(
        tmp_path, {"body": dict(_BASE_TEXT_ROLE)}, {"info_table": incomplete_table_role}
    )

    with pytest.raises(HwpxAuthoringResolveError, match="border_color"):
        resolve(design_path, _info_table_spec("info_table"))


# ---------------------------------------------------------------------------
# D. section 종류 ↔ role 종류 호환성 (존재하지 않는 이름 / 잘못된 네임스페이스).
# ---------------------------------------------------------------------------


def test_resolve_rejects_undefined_style_role(tmp_path: Path) -> None:
    design_path = _write_institution_design(tmp_path, {"body": dict(_BASE_TEXT_ROLE)})

    with pytest.raises(HwpxAuthoringResolveError, match="does_not_exist"):
        resolve(design_path, _title_spec("does_not_exist"))


def test_resolve_rejects_table_role_name_referenced_as_text_style(tmp_path: Path) -> None:
    # "info_table"은 defaults.table에만 정의되어 있고 defaults.styles에는
    # 없다 — title이 이 이름을 참조하면 같은 이름이 표 네임스페이스에
    # 존재해도 text 네임스페이스에서 찾지 못해 거부된다. section 종류 ↔
    # role 종류 호환성은 이 네임스페이스 분리 자체로 검증된다(하드코딩된
    # 문서 유형 enum 없이).
    design_path = _write_institution_design(
        tmp_path, {"body": dict(_BASE_TEXT_ROLE)}, {"info_table": dict(_INFO_TABLE_ROLE)}
    )

    with pytest.raises(HwpxAuthoringResolveError, match="info_table"):
        resolve(design_path, _title_spec("info_table"))


def test_resolve_rejects_undefined_table_role(tmp_path: Path) -> None:
    design_path = _write_institution_design(tmp_path, {"body": dict(_BASE_TEXT_ROLE)})

    with pytest.raises(HwpxAuthoringResolveError, match="does_not_exist"):
        resolve(design_path, _info_table_spec("does_not_exist"))


# ---------------------------------------------------------------------------
# E. info_table label/value가 서로 다른 typography role로 해석될 수 있다.
# ---------------------------------------------------------------------------


def test_resolve_info_table_label_and_value_use_different_roles(tmp_path: Path) -> None:
    label_role = dict(_BASE_TEXT_ROLE, color="#1F3864", bold=True)
    value_role = dict(_BASE_TEXT_ROLE, color="#000000", bold=False)
    table_role = dict(_INFO_TABLE_ROLE, label_style_role="label", value_style_role="value")
    design_path = _write_institution_design(
        tmp_path, {"label": label_role, "value": value_role}, {"info_table": table_role}
    )

    resolved = resolve(design_path, _info_table_spec("info_table"))
    table_style = resolved.sections[0].style

    assert table_style.label_style.color == "#1F3864"
    assert table_style.label_style.bold is True
    assert table_style.value_style.color == "#000000"
    assert table_style.value_style.bold is False


# ---------------------------------------------------------------------------
# F. 표 style_override는 width_mm만 허용된다.
# ---------------------------------------------------------------------------


def test_resolve_allows_table_width_override(tmp_path: Path) -> None:
    design_path = _write_institution_design(
        tmp_path, {"body": dict(_BASE_TEXT_ROLE)}, {"info_table": dict(_INFO_TABLE_ROLE)}
    )

    resolved = resolve(
        design_path, _info_table_spec("info_table", style_override={"width_mm": 150.0})
    )

    assert resolved.sections[0].style.width_mm == 150.0
    # override되지 않은 속성은 institution 기본값 그대로.
    assert resolved.sections[0].style.border_width_mm == 0.12
    assert resolved.sections[0].style.border_color == "#BFBFBF"


# ---------------------------------------------------------------------------
# G. masthead 3칸 폭은 institution이 명시한 값이어야 하고, 합이 width_mm과
#    정확히 일치해야 한다 (v3 visual QA P1 fix — width/3 균등분배나 로고
#    크기에서 유도한 값을 금지한다).
# ---------------------------------------------------------------------------


_MASTHEAD_LOGO_ASSET_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "template-contracts" / "assets"


def _write_masthead_design(
    tmp_path: Path,
    *,
    logo_left_slot_width_mm: float,
    title_slot_width_mm: float,
    logo_right_slot_width_mm: float,
    width_mm: float = 170.0,
) -> Path:
    path = tmp_path / "masthead_design.json"
    path.write_text(
        json.dumps(
            {
                "institution_design_version": "v1",
                "institution": "test-institution",
                "design_id": "test-design-v1",
                "evidence_reference": "docs/hwpx-layout-baseline.md",
                "defaults": {"page": {}, "styles": {"title": dict(_BASE_TEXT_ROLE)}, "table": {}},
                "masthead": {
                    "default": "required",
                    "document_override_allowed": True,
                    "width_mm": width_mm,
                    "height_mm": 22.0,
                    "border_width_mm": 0.4,
                    "border_color": "#123456",
                    "cell_margin_mm": {"left": 3.0, "right": 3.0, "top": 2.0, "bottom": 2.0},
                    "title_style_role": "title",
                    "logo_left_asset_id": "test_logo_left",
                    "logo_left_width_mm": 10.0,
                    "logo_left_height_mm": 10.0,
                    "logo_right_asset_id": "test_logo_right",
                    "logo_right_width_mm": 10.0,
                    "logo_right_height_mm": 10.0,
                    "logo_left_slot_width_mm": logo_left_slot_width_mm,
                    "title_slot_width_mm": title_slot_width_mm,
                    "logo_right_slot_width_mm": logo_right_slot_width_mm,
                },
                "assets": [
                    {"asset_id": "test_logo_left", "path": str(_MASTHEAD_LOGO_ASSET_DIR / "test-logo-left.png")},
                    {"asset_id": "test_logo_right", "path": str(_MASTHEAD_LOGO_ASSET_DIR / "test-logo-right.png")},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_resolve_accepts_explicit_masthead_slot_widths_summing_to_width(tmp_path: Path) -> None:
    design_path = _write_masthead_design(
        tmp_path, logo_left_slot_width_mm=35.0, title_slot_width_mm=100.0, logo_right_slot_width_mm=35.0
    )
    spec = _title_spec("title")

    resolved = resolve(design_path, spec)

    assert resolved.masthead is not None
    assert resolved.masthead.logo_left_slot_width_mm == 35.0
    assert resolved.masthead.title_slot_width_mm == 100.0
    assert resolved.masthead.logo_right_slot_width_mm == 35.0
    # width/3 균등분배가 아니라 institution이 서로 다른 값을 명시했다는 증거.
    assert resolved.masthead.logo_left_slot_width_mm != resolved.masthead.title_slot_width_mm


def test_resolve_rejects_masthead_slot_widths_not_summing_to_width(tmp_path: Path) -> None:
    design_path = _write_masthead_design(
        tmp_path, logo_left_slot_width_mm=35.0, title_slot_width_mm=100.0, logo_right_slot_width_mm=40.0
    )
    spec = _title_spec("title")

    with pytest.raises(HwpxAuthoringResolveError, match="logo_left_slot_width_mm"):
        resolve(design_path, spec)
