"""template_spec(authoring-v2, section 기반) + Institution Design Contract ->
resolve() -> 자체 source.hwpx -> 기존 qa_hwpx_template.py candidate 연결 검증.

이 테스트는 section 기반 authoring 어댑터(core.adapters.hwpx_template_authoring)
+ resolver(core.adapters.hwpx_authoring_resolve)가
docs/tasks/template-create-authoring-v2.md와
docs/tasks/institution-design-contract-v1.md의 완료 조건을 만족하는지
증명한다:

1. TemplateSpec이 title/info_table/body_section의 순서를 데이터로 표현한다.
2. generate_source_hwpx()가 고정 "제목+2열 표" shape을 전제하지 않는다
   (info_table이 없는 spec을 생성해 표가 실제로 없는지 직접 증명).
3. page 값과, resolve()가 확정한 typography/table 값이 실제 생성 HWPX에
   반영된다(XML로 직접 확인).
4. 생성 위치를 기반으로 FIXED/CONTENT separation rules가 생성된다(텍스트
   재검색이 아니라 생성 시점 배치 순서 기반).
5. repeat_section 같은 미허용 section type은 거부된다.
6. 자체 생성 source.hwpx가 기존 qa_hwpx_template.py candidate 파이프라인을
   그대로 통과한다.
7. institution-design-contract-v1 회귀: institution이 명시한 색이 생성된
   HWPX의 실제 charPr에 적용되고, hwpx skeleton 기본값(예: 관찰된
   ``#2E74B5``)을 물려받지 않는다. info_table label/value 셀도 마찬가지다.

이 파일은 이전 "제목+2열 표 고정, page/heading_style/table_style/footer만
override" 설계(폐기)를 검증하던 이전 버전을 완전히 대체했다(authoring-v2).
institution-design-contract-v1은 그 위에서 TemplateSpec의 style 필드를
인라인 값에서 institution role 참조로 바꿨다 — 그래서 이 파일의 모든
``generate_source_hwpx()``/``build_separation_rules()`` 호출이
``resolve()``를 거친 ``ResolvedAuthoringContract``를 쓰도록 갱신됐다(이전
버전은 ``TemplateSpec``을 직접 넘겼다). ``template_spec.styles``가 role
존재를 스스로 검증하던 옛 테스트(``test_load_template_spec_rejects_style_
reference_to_undefined_role``)도 같은 이유로 ``resolve()``를 검증하도록
바뀌었다 — TemplateSpec은 더 이상 role의 존재를 알지 못한다(그 판단은
resolve()로 옮겨갔다).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_authoring_resolve import (  # noqa: E402
    HwpxAuthoringResolveError,
    resolve,
)
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    HwpxTemplateAuthoringError,
    InfoTableSection,
    TitleSection,
    build_separation_rules,
    generate_source_hwpx,
    load_template_spec,
    write_separation_rules,
)
from core.templates.hwpx_semantic_classifier import classify_document_semantics  # noqa: E402
from core.templates.hwpx_semantic_contract import SemanticRole  # noqa: E402
from core.templates.hwpx_separation_rules import load_separation_rules  # noqa: E402
from scripts.templates import qa_hwpx_template  # noqa: E402
from validators.hwpx_package_rules import validate as validate_hwpx_package  # noqa: E402

FIXTURE = (
    ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report.template_spec.json"
)
INSTITUTION_DESIGN_FIXTURE = (
    ROOT / "tests" / "fixtures" / "template-contracts" / "edudoc.institution_design.json"
)

_NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
}
_HWPUNIT_PER_MM = 7200 / 25.4


def _read_source_xml(source_hwpx: Path) -> tuple[ET.Element, ET.Element]:
    with zipfile.ZipFile(source_hwpx) as package:
        header_root = ET.fromstring(package.read("Contents/header.xml"))
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
    return header_root, section_root


def _para_pr(header_root: ET.Element, para_pr_id_ref: str) -> ET.Element:
    for para_pr in header_root.iter(f"{{{_NS['hh']}}}paraPr"):
        if para_pr.get("id") == para_pr_id_ref:
            return para_pr
    raise AssertionError(f"paraPr id={para_pr_id_ref!r} not found in header.xml")


def _char_pr(header_root: ET.Element, char_pr_id_ref: str) -> ET.Element:
    for char_pr in header_root.iter(f"{{{_NS['hh']}}}charPr"):
        if char_pr.get("id") == char_pr_id_ref:
            return char_pr
    raise AssertionError(f"charPr id={char_pr_id_ref!r} not found in header.xml")


def _border_fill(header_root: ET.Element, border_fill_id_ref: str) -> ET.Element:
    for border_fill in header_root.iter(f"{{{_NS['hh']}}}borderFill"):
        if border_fill.get("id") == border_fill_id_ref:
            return border_fill
    raise AssertionError(f"borderFill id={border_fill_id_ref!r} not found in header.xml")


def _paragraphs_in_order(section_root: ET.Element) -> list[ET.Element]:
    # section root의 직계 자식 <hp:p>만 문서 최상위 문단이다. 표 셀 안의
    # <hp:p>는 <hp:tc> 아래 더 깊이 있으므로 재귀 iter()로 걷으면 섞여
    # 들어온다 — 직계 자식만 취해 표 앵커 문단(표를 담은 문단)과 셀 내부
    # 문단을 구분한다.
    return list(section_root.findall(f"{{{_NS['hp']}}}p"))


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(t.text or "" for t in paragraph.iter(f"{{{_NS['hp']}}}t"))


def _cell_paragraphs(section_root: ET.Element) -> list[ET.Element]:
    return list(section_root.iter(f"{{{_NS['hp']}}}tc"))


def _write_spec(tmp_path: Path, data: dict, name: str = "spec.template_spec.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _resolved_from_fixture(tmp_path: Path):
    spec = load_template_spec(FIXTURE)
    return resolve(INSTITUTION_DESIGN_FIXTURE, spec)


def _masthead_free_design(tmp_path: Path) -> Path:
    # INSTITUTION_DESIGN_FIXTURE는 masthead.default="required"다(institution-
    # design-contract-v1 visual-layout task). 이 fixture를 그대로 쓰면
    # generate_source_hwpx()가 항상 masthead 표를 만든다 — "info_table이
    # 없으면 표가 아예 없다"를 증명하려는 테스트는 masthead까지 꺼야
    # 원래 의도(표 유무는 오직 info_table section 유무로 결정된다)를
    # 그대로 검증할 수 있다. styles/table 값은 fixture와 동일하게 두고
    # masthead만 끈다.
    data = json.loads(INSTITUTION_DESIGN_FIXTURE.read_text(encoding="utf-8"))
    data["masthead"] = {"default": "none", "document_override_allowed": True}
    # masthead를 껐으니 로고 asset도 필요 없다 — asset path는 이 design.json
    # 자신의 디렉터리 기준 상대 경로라, tmp_path에 파일만 새로 쓰면
    # 원본 fixture 옆의 assets/를 가리키지 못해 존재하지 않는 파일로 실패한다.
    data["assets"] = []
    path = tmp_path / "design_no_masthead.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _masthead_table(section_root: ET.Element) -> ET.Element:
    tables = section_root.findall(f".//{{{_NS['hp']}}}tbl")
    if not tables:
        raise AssertionError("no <hp:tbl> found in generated section")
    return tables[0]  # masthead는 항상 generate_source_hwpx()가 만드는 첫 번째 표다.


def _masthead_title_cell_text(section_root: ET.Element) -> str:
    masthead = _masthead_table(section_root)
    cells = masthead.findall(f".//{{{_NS['hp']}}}tc")
    # [로고 왼쪽 | 문서명 | 로고 오른쪽] — _MASTHEAD_TITLE_COLUMN(=1)과 맞춘다.
    return _paragraph_text(cells[1])


# ---------------------------------------------------------------------------
# 1) TemplateSpec이 section 순서를 데이터로 표현한다.
# ---------------------------------------------------------------------------


def test_load_template_spec_parses_sections_in_order() -> None:
    spec = load_template_spec(FIXTURE)

    assert spec.template_spec_version == "authoring-v2"
    assert len(spec.sections) == 5
    assert isinstance(spec.sections[0], TitleSection)
    assert spec.sections[0].text == "주간업무보고서"
    assert isinstance(spec.sections[1], InfoTableSection)
    assert [row.label for row in spec.sections[1].rows] == ["보고 기간"]
    assert [entry.type for entry in spec.sections[2:]] == [
        "body_section",
        "body_section",
        "body_section",
    ]
    assert [entry.heading_text for entry in spec.sections[2:]] == [
        "금주 업무",
        "주요 이슈",
        "차주 계획",
    ]


def test_load_template_spec_requires_page_with_no_fallback(tmp_path: Path) -> None:
    # baseline 값은 Python 상수로 존재하지 않는다 — page가 없으면 기본값으로
    # 채우지 않고 거부한다. (institution-design-contract-v1: template_spec에
    # 더 이상 최상위 styles 블록이 없다 — style은 section마다 institution
    # role 이름을 참조할 뿐이라, "styles가 없으면 거부" 검증 대상 자체가
    # 사라졌다. 이 테스트는 그래서 page 요구사항만 남긴다.)
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))

    without_page = {k: v for k, v in base.items() if k != "page"}
    with pytest.raises(HwpxTemplateAuthoringError, match="page"):
        load_template_spec(_write_spec(tmp_path, without_page, "no_page.json"))


def test_load_template_spec_rejects_repeat_section_type(tmp_path: Path) -> None:
    # 완료 조건: repeat_section은 예약도 되어 있지 않다 — 허용 타입이 아니다.
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base["sections"].append({"type": "repeat_section", "items": []})
    spec_path = _write_spec(tmp_path, base, "repeat.json")

    with pytest.raises(HwpxTemplateAuthoringError, match="title.*info_table.*body_section"):
        load_template_spec(spec_path)


def test_resolve_rejects_style_reference_to_undefined_role(tmp_path: Path) -> None:
    # institution-design-contract-v1: role 존재 검증은 이제 resolve()의
    # 책임이다 — load_template_spec()은 style 필드가 비어있지 않은
    # 문자열인지만 본다(TemplateSpec 혼자서는 어떤 role이 존재하는지 알 수
    # 없다: 그 정보는 Institution Design Contract에만 있다).
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base["sections"][0]["style"] = "does_not_exist"
    spec_path = _write_spec(tmp_path, base, "bad_style_ref.json")

    spec = load_template_spec(spec_path)
    with pytest.raises(HwpxAuthoringResolveError, match="does_not_exist"):
        resolve(INSTITUTION_DESIGN_FIXTURE, spec)


# ---------------------------------------------------------------------------
# 2) generate_source_hwpx()가 고정 "제목+2열 표" shape을 전제하지 않는다.
# ---------------------------------------------------------------------------


def test_generate_source_hwpx_produces_no_table_when_spec_has_no_info_table(
    tmp_path: Path,
) -> None:
    spec = load_template_spec(
        _write_spec(
            tmp_path,
            {
                "template_spec_version": "authoring-v2",
                "page": {
                    "margins_mm": {"left": 20.0, "right": 20.0, "top": 10.0, "bottom": 10.0}
                },
                "sections": [
                    {"type": "title", "style": "title", "text": "제목만 있는 문서"},
                    {
                        "type": "body_section",
                        "heading_style": "title",
                        "body_style": "body",
                        "heading_text": "본문",
                        "field_id": "body",
                        "sample_value": "표가 없는 문서",
                    },
                ],
            },
            "no_table.json",
        )
    )
    # masthead가 있으면 항상 표를 하나 만든다(로고+문서명 상자) — "표가
    # 없다"를 증명하려는 이 테스트의 의도(표 유무는 오직 info_table section
    # 유무로 결정된다)를 그대로 지키려면 masthead까지 꺼야 한다.
    resolved = resolve(_masthead_free_design(tmp_path), spec)

    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    _, section_root = _read_source_xml(source_hwpx)

    assert section_root.find(f".//{{{_NS['hp']}}}tbl") is None
    paragraphs = _paragraphs_in_order(section_root)
    texts = [_paragraph_text(p) for p in paragraphs]
    assert texts == ["제목만 있는 문서", "본문", "표가 없는 문서"]


def test_generate_source_hwpx_follows_section_order(tmp_path: Path) -> None:
    resolved = _resolved_from_fixture(tmp_path)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    header_root, section_root = _read_source_xml(source_hwpx)

    # 문서명("주간업무보고서")은 masthead가 있을 때 표준 문단이 아니라
    # masthead 표 중앙 셀 안에 들어간다 — 별도로 확인한다(아래).
    non_table_paragraphs = [
        p
        for p in _paragraphs_in_order(section_root)
        if p.find(f".//{{{_NS['hp']}}}tbl") is None
    ]
    texts = [_paragraph_text(p) for p in non_table_paragraphs]
    assert texts == [
        "■ 금주 업무",
        "신규 기능 A 개발 완료, 정기 점검 수행",
        "■ 주요 이슈",
        "협력 부서 일정 지연으로 통합 테스트 1주 연기",
        "■ 차주 계획",
        "통합 테스트 진행 및 결과 보고",
    ]
    tables = section_root.findall(f".//{{{_NS['hp']}}}tbl")
    assert len(tables) == 2  # masthead(로고+문서명) + info_table
    assert _masthead_title_cell_text(section_root) == "주간업무보고서"


def test_generate_source_hwpx_places_masthead_before_all_body_content_in_actual_document_order(
    tmp_path: Path,
) -> None:
    """v3 visual QA P0-1 회귀: 실제 생성된 section0.xml의 최상위 <hp:p> 순서
    그대로(텍스트 재검색이나 표/비표 분리 없이) masthead -> info_table ->
    금주 업무(heading+body) -> 주요 이슈(heading+body) -> 차주 계획
    (heading+body) 순이어야 한다.

    v3에서는 "■ 금주 업무" heading이 skeleton 문단을 masthead보다 먼저
    가로채, 실제 문서 순서상 masthead 표보다 **앞에** 나왔다(사람 육안
    QA로 발견) — 이 테스트는 그 정확한 결함을 재현하는 조건(문서 최상위
    <hp:p> 물리적 순서)으로 검증한다.
    """
    resolved = _resolved_from_fixture(tmp_path)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    _, section_root = _read_source_xml(source_hwpx)

    top_level_paragraphs = _paragraphs_in_order(section_root)

    def kind(paragraph: ET.Element) -> str:
        if paragraph.find(f".//{{{_NS['hp']}}}tbl") is not None:
            return "table"
        return _paragraph_text(paragraph)

    observed = [kind(p) for p in top_level_paragraphs]
    assert observed == [
        "table",  # masthead
        "table",  # info_table
        "■ 금주 업무",
        "신규 기능 A 개발 완료, 정기 점검 수행",
        "■ 주요 이슈",
        "협력 부서 일정 지연으로 통합 테스트 1주 연기",
        "■ 차주 계획",
        "통합 테스트 진행 및 결과 보고",
    ]
    # 첫 번째 표가 masthead임을 문서명 텍스트로 다시 한번 직접 확인한다
    # (표 두 개의 순서 자체가 뒤바뀌는 회귀까지 잡기 위해).
    assert _masthead_title_cell_text(section_root) == "주간업무보고서"


def test_generate_source_hwpx_refuses_existing_output(tmp_path: Path) -> None:
    resolved = _resolved_from_fixture(tmp_path)
    output = tmp_path / "source.hwpx"
    generate_source_hwpx(resolved, output)

    with pytest.raises(HwpxTemplateAuthoringError):
        generate_source_hwpx(resolved, output)


# ---------------------------------------------------------------------------
# 3) page 값과 resolve()가 확정한 typography/table 값이 실제 생성 HWPX에
#    반영된다.
# ---------------------------------------------------------------------------


def test_generate_source_hwpx_materializes_page_and_styles(tmp_path: Path) -> None:
    resolved = _resolved_from_fixture(tmp_path)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    header_root, section_root = _read_source_xml(source_hwpx)

    margin = section_root.find(f".//{{{_NS['hp']}}}margin")
    assert margin is not None
    for side, mm in resolved.page_margins_mm.items():
        assert margin.get(side) == str(round(mm * _HWPUNIT_PER_MM)), side

    # 문서명은 masthead 표 중앙 셀 안에 있다 — institution의 title role이
    # align="center"이므로 셀 문단도 가운데 정렬이어야 한다.
    tables = section_root.findall(f".//{{{_NS['hp']}}}tbl")
    masthead_table, info_table = tables[0], tables[1]
    title_cells = masthead_table.findall(f".//{{{_NS['hp']}}}tc")
    title_paragraph = title_cells[1].find(f".//{{{_NS['hp']}}}p")
    para_pr = _para_pr(header_root, title_paragraph.get("paraPrIDRef"))
    align = para_pr.find(f"{{{_NS['hh']}}}align")
    assert align is not None and align.get("horizontal") == "CENTER"
    run = title_paragraph.find(f"{{{_NS['hp']}}}run")
    char_pr = _char_pr(header_root, run.get("charPrIDRef"))
    assert char_pr.get("height") == str(round(17 * 100))  # fixture의 title.size_pt

    paragraphs = _paragraphs_in_order(section_root)
    body_paragraph = next(
        p for p in paragraphs if _paragraph_text(p) == "신규 기능 A 개발 완료, 정기 점검 수행"
    )
    body_run = body_paragraph.find(f"{{{_NS['hp']}}}run")
    body_char_pr = _char_pr(header_root, body_run.get("charPrIDRef"))
    assert body_char_pr.get("height") == str(round(13 * 100))  # fixture의 body.size_pt

    border_fill = _border_fill(header_root, info_table.get("borderFillIDRef"))
    left_border = border_fill.find(f"{{{_NS['hh']}}}leftBorder")
    assert left_border is not None and left_border.get("width") == "0.12 mm"
    sz = info_table.find(f"{{{_NS['hp']}}}sz")
    assert sz is not None
    assert sz.get("width") == str(round(170.0 * _HWPUNIT_PER_MM))


# ---------------------------------------------------------------------------
# 3-2) v3 visual QA P0-2 회귀: heading_rule_width_mm(구분선)이 institution
#      design에 실제로 설정돼 있을 때도, 바로 다음 body 문단이 그 구분선을
#      물려받지 않는다. (edudoc weekly-report design 자체는 이제
#      heading_rule_width_mm을 쓰지 않으므로, 이 capability가 실제로 켜졌을
#      때의 leak 방지는 별도의 최소 institution design으로 직접 검증한다 —
#      capability는 schema에 남아 있고(다른 문서가 쓸 수 있음), 이 테스트가
#      그 capability 자체의 동작을 계속 보증한다.)
# ---------------------------------------------------------------------------


def _heading_rule_design(tmp_path: Path) -> Path:
    design = {
        "institution_design_version": "v1",
        "institution": "test-institution",
        "design_id": "test-design-v1",
        "evidence_reference": "docs/hwpx-layout-baseline.md",
        "defaults": {
            "page": {},
            "styles": {
                "heading": {
                    "font_family": "테스트고딕",
                    "size_pt": 16,
                    "color": "#123456",
                    "bold": True,
                    "align": "left",
                    "heading_rule_width_mm": 0.3,
                    "marker": "■ ",
                },
                "body": {
                    "font_family": "테스트고딕",
                    "size_pt": 13,
                    "color": "#000000",
                    "bold": False,
                    "align": "left",
                },
            },
            "table": {},
        },
        "masthead": {"default": "none", "document_override_allowed": True},
        "assets": [],
    }
    path = tmp_path / "heading_rule_design.json"
    path.write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")
    return path


def test_body_paragraph_does_not_inherit_heading_rule_from_preceding_heading(
    tmp_path: Path,
) -> None:
    spec = load_template_spec(
        _write_spec(
            tmp_path,
            {
                "template_spec_version": "authoring-v2",
                "page": {
                    "margins_mm": {"left": 20.0, "right": 20.0, "top": 10.0, "bottom": 10.0}
                },
                "sections": [
                    {
                        "type": "body_section",
                        "heading_style": "heading",
                        "body_style": "body",
                        "heading_text": "구분선 있는 heading",
                        "field_id": "body1",
                        "sample_value": "구분선이 없어야 하는 body",
                    },
                ],
            },
            "heading_rule.json",
        )
    )
    resolved = resolve(_heading_rule_design(tmp_path), spec)
    header_root, section_root = _read_source_xml(
        generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    )

    paragraphs = _paragraphs_in_order(section_root)
    heading_paragraph = next(p for p in paragraphs if _paragraph_text(p) == "■ 구분선 있는 heading")
    body_paragraph = next(
        p for p in paragraphs if _paragraph_text(p) == "구분선이 없어야 하는 body"
    )

    # paraPrIDRef 자체가 달라야 한다 — inherit_style=True로 body가 heading의
    # paraPr을 그대로 이어받으면 이 값이 같아진다(P0-2의 근본 원인).
    assert heading_paragraph.get("paraPrIDRef") != body_paragraph.get("paraPrIDRef")

    def bottom_border(paragraph: ET.Element) -> ET.Element | None:
        para_pr = _para_pr(header_root, paragraph.get("paraPrIDRef"))
        border = para_pr.find(f"{{{_NS['hh']}}}border")
        if border is None:
            return None
        border_fill = _border_fill(header_root, border.get("borderFillIDRef"))
        return border_fill.find(f"{{{_NS['hh']}}}bottomBorder")

    heading_bottom = bottom_border(heading_paragraph)
    body_bottom = bottom_border(body_paragraph)

    assert heading_bottom is not None and heading_bottom.get("type") == "SOLID"
    assert heading_bottom.get("width") == "0.3 mm"
    assert body_bottom is None or body_bottom.get("type") == "NONE"


# ---------------------------------------------------------------------------
# 3-3) v3 visual QA P1 회귀: title > section heading > body > metadata(info
#      table label/value) typography 위계가 성립한다. 특정 pt 값을 하드코딩
#      하지 않고 ResolvedAuthoringContract에서 읽은 값끼리 순서만 비교한다
#      — fixture의 실제 숫자가 바뀌어도 위계 자체가 깨지면 이 테스트가
#      실패해야 한다는 뜻이다.
# ---------------------------------------------------------------------------


def test_typography_hierarchy_title_heading_body_metadata_strictly_decreases(
    tmp_path: Path,
) -> None:
    resolved = _resolved_from_fixture(tmp_path)

    assert resolved.masthead is not None
    title_size = resolved.masthead.title_style.size_pt

    body_sections = [s for s in resolved.sections if s.type == "body_section"]
    assert body_sections
    heading_size = body_sections[0].heading_style.size_pt
    body_size = body_sections[0].body_style.size_pt

    info_tables = [s for s in resolved.sections if s.type == "info_table"]
    assert info_tables
    metadata_size = info_tables[0].style.label_style.size_pt
    assert info_tables[0].style.value_style.size_pt == metadata_size

    assert title_size > heading_size > body_size > metadata_size


# ---------------------------------------------------------------------------
# 7) institution-design-contract-v1 회귀: institution이 명시한 color/font가
#    실제 생성 HWPX에 적용되고, hwpx skeleton 기본값(관찰된 ``#2E74B5``)을
#    물려받지 않는다.
# ---------------------------------------------------------------------------


def test_generate_source_hwpx_applies_institution_color_not_skeleton_default(
    tmp_path: Path,
) -> None:
    """원래 버그의 재현 + 수정 확인.

    기존 원인: ``_materialize_paragraph()``가
    ``doc.styles.ensure_run(size=style.size_pt)``만 호출해 ``color``/``font``
    를 넘기지 않았다. hwpx 라이브러리의 ``_run_style_predicate``는
    color/font가 ``None``이면 비교를 건너뛰므로, 새 charPr을 만들 때
    header의 첫 번째(사실상 id=0) charPr — skeleton 기본값(관찰된
    ``#2E74B5``) — 을 그대로 물려받았다.

    지금은 ``resolve()``가 확정한 ``ResolvedTextStyle.color``/``font_family``
    를 ``_ensure_run_for_style()``이 ``ensure_run(color=..., font=...)``로
    항상 명시적으로 전달한다 — skeleton의 어떤 charPr도 이 값을 흐리게 할
    수 없다.
    """
    resolved = _resolved_from_fixture(tmp_path)
    header_root, section_root = _read_source_xml(
        generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    )

    # 문서명은 이제 masthead 표 중앙 셀 안에 있다(institution-design-
    # contract-v1 visual-layout task) — 표준 문단이 아니라 셀에서 찾는다.
    masthead_table = _masthead_table(section_root)
    title_cell = masthead_table.findall(f".//{{{_NS['hp']}}}tc")[1]
    title_paragraph = title_cell.find(f".//{{{_NS['hp']}}}p")
    run = title_paragraph.find(f"{{{_NS['hp']}}}run")
    char_pr = _char_pr(header_root, run.get("charPrIDRef"))

    # tests/fixtures/template-contracts/edudoc.institution_design.json의
    # "title" role이 명시한 값 — hwpx skeleton 기본값 #2E74B5와 다르다.
    assert char_pr.get("textColor") == "#1F3864"
    assert char_pr.get("textColor") != "#2E74B5"
    font_ref = char_pr.find(f"{{{_NS['hh']}}}fontRef")
    assert font_ref is not None
    hangul_face_id = font_ref.get("hangul")
    assert hangul_face_id is not None
    font_face = next(
        face
        for face in header_root.iter(f"{{{_NS['hh']}}}font")
        if face.get("id") == hangul_face_id
    )
    assert font_face.get("face") == "함초롬돋움"
    bold = char_pr.find(f"{{{_NS['hh']}}}bold")
    assert bold is not None  # institution role의 bold: true가 적용됨


def test_generate_source_hwpx_applies_info_table_label_and_value_typography(
    tmp_path: Path,
) -> None:
    """info_table의 label/value 셀 typography도 institution design에서 온
    값을 명시적으로 쓴다 — ``set_cell_text(..., preserve_format=True)``만
    쓰면 셀이 이미 갖고 있던(또는 skeleton의) charPr이 새어 들어올 수
    있는데, ``_materialize_info_table()``이 텍스트를 쓴 뒤 각 셀 문단의
    ``char_pr_id_ref``를 institution role에서 온 값으로 명시적으로
    덮어써 그 leak을 막는다.
    """
    resolved = _resolved_from_fixture(tmp_path)
    header_root, section_root = _read_source_xml(
        generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    )

    cells = _cell_paragraphs(section_root)
    label_cell = next(cell for cell in cells if _paragraph_text(cell) == "보고 기간")
    value_cell = next(cell for cell in cells if _paragraph_text(cell) == "2026-08-04 ~ 2026-08-08")

    label_run = label_cell.find(f".//{{{_NS['hp']}}}run")
    value_run = value_cell.find(f".//{{{_NS['hp']}}}run")
    label_char_pr = _char_pr(header_root, label_run.get("charPrIDRef"))
    value_char_pr = _char_pr(header_root, value_run.get("charPrIDRef"))

    # tests/fixtures/template-contracts/edudoc.institution_design.json의
    # info_table_label/info_table_value role 값 — 서로 다르다(라벨은 굵게+
    # 강조색, 값은 일반).
    assert label_char_pr.get("textColor") == "#1F3864"
    assert label_char_pr.find(f"{{{_NS['hh']}}}bold") is not None
    assert value_char_pr.get("textColor") == "#000000"
    assert value_char_pr.find(f"{{{_NS['hh']}}}bold") is None
    assert label_char_pr.get("id") != value_char_pr.get("id")


# ---------------------------------------------------------------------------
# 4) 생성 위치 기반 FIXED/CONTENT separation rules.
# ---------------------------------------------------------------------------


def test_build_separation_rules_leave_no_ambiguous_semantic_decision(tmp_path: Path) -> None:
    resolved = _resolved_from_fixture(tmp_path)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")
    rules_dict = build_separation_rules(resolved, source_hwpx)
    rules_path = write_separation_rules(rules_dict, tmp_path / "rules.json")

    rules = load_separation_rules(rules_path)
    with zipfile.ZipFile(source_hwpx) as package:
        root = ET.fromstring(package.read("Contents/section0.xml"))
    decisions = classify_document_semantics(root, "section0.xml", rules)

    assert decisions
    ambiguous = [d for d in decisions if d.role is SemanticRole.AMBIGUOUS]
    assert not ambiguous, [d.location for d in ambiguous]

    content_decisions = [d for d in decisions if d.role is SemanticRole.CONTENT]
    assert len(content_decisions) == 4
    fixed_decisions = [d for d in decisions if d.role is SemanticRole.FIXED]
    assert len(fixed_decisions) == 5


def test_build_separation_rules_detects_structure_mismatch(tmp_path: Path) -> None:
    # spec과 실제로 생성된 source.hwpx가 서로 다른 문서를 가리키면(즉 spec이
    # 만든 게 아닌 hwpx를 잘못 넘기면) 조용히 잘못된 규칙을 만들지 않고 거부한다.
    resolved = _resolved_from_fixture(tmp_path)
    other_spec = load_template_spec(
        _write_spec(
            tmp_path,
            {
                "template_spec_version": "authoring-v2",
                "page": {
                    "margins_mm": {"left": 20.0, "right": 20.0, "top": 10.0, "bottom": 10.0}
                },
                "sections": [
                    {"type": "title", "style": "title", "text": "다른 문서"},
                    # masthead가 title section의 텍스트를 이미 소비하므로,
                    # skeleton 문단을 재사용할 body_section이 하나는 있어야
                    # generate_source_hwpx()가 "최소 하나의 title/body_section"
                    # 요건에 걸리지 않는다(이 테스트의 목적은 그 요건이 아니라
                    # build_separation_rules()의 구조 불일치 감지다).
                    {
                        "type": "body_section",
                        "heading_style": "section_title",
                        "body_style": "body",
                        "heading_text": "다른 섹션",
                        "field_id": "other_body",
                        "sample_value": "다른 본문",
                    },
                ],
            },
            "other.json",
        )
    )
    other_resolved = resolve(INSTITUTION_DESIGN_FIXTURE, other_spec)
    other_source = generate_source_hwpx(other_resolved, tmp_path / "other_source.hwpx")

    with pytest.raises(HwpxTemplateAuthoringError, match="non-table text"):
        build_separation_rules(resolved, other_source)


# ---------------------------------------------------------------------------
# 6) 자체 생성 source.hwpx가 기존 candidate QA 파이프라인을 통과한다.
# ---------------------------------------------------------------------------


def test_authored_source_hwpx_becomes_a_qa_candidate_via_existing_pipeline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    resolved = _resolved_from_fixture(tmp_path)
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "authoring" / "source.hwpx")
    rules_path = write_separation_rules(
        build_separation_rules(resolved, source_hwpx), tmp_path / "authoring" / "rules.json"
    )

    candidate_dir = tmp_path / "candidate"
    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(source_hwpx),
            "--output-dir",
            str(candidate_dir),
            "--institution",
            "edudoc",
            "--document-type",
            "주간업무보고서",
            "--rules",
            str(rules_path),
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0, summary
    assert summary["ok"] is True
    assert summary["status"] == "candidate"
    assert summary["strict_validation"] == {
        "roundtrip.sample.hwpx": True,
        "roundtrip.test.hwpx": True,
    }

    for required in (
        "template.json",
        "placeholder_map.json",
        "content.sample.json",
        "template.review.md",
        "source.hwpx",
        "semantic_classification.json",
        "roundtrip.sample.hwpx",
        "roundtrip.test.hwpx",
        "qa.report.json",
    ):
        assert (candidate_dir / required).is_file(), required

    template = json.loads((candidate_dir / "template.json").read_text(encoding="utf-8"))
    assert template["status"] == "candidate"
    assert template["content_separation"].get("semantic_status") == "resolved"

    placeholder_map = json.loads(
        (candidate_dir / "placeholder_map.json").read_text(encoding="utf-8")
    )
    assert len(placeholder_map["fields"]) == 4

    semantic = json.loads(
        (candidate_dir / "semantic_classification.json").read_text(encoding="utf-8")
    )
    assert semantic["unresolved_count"] == 0
    ambiguous = [d for d in semantic["node_decisions"] if d["role"] == "ambiguous"]
    assert not ambiguous, ambiguous

    report = validate_hwpx_package(candidate_dir / "roundtrip.sample.hwpx")
    assert report.passed, report.summary()
