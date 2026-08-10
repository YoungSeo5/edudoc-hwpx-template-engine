"""placeholder마다 원본 레이아웃을 기록하고 렌더 결과에서 검증하는 공통 계약.

변경 전에는 보존할 서식이 한 종류 늘 때마다 분리기와 렌더러 양쪽에 같은 모양의
분기가 따로 추가됐고, 계약을 손으로 붙인 템플릿(금감원 원페이지)만 검증됐다.
금감원 원장보고처럼 section_paragraph_counts가 없는 템플릿은 렌더 시 서식 검증이
통째로 건너뛰어졌다.

여기서 확인하는 것:
- 분리 단계가 모든 placeholder에 layout_context를 기록하고 계약을 선언한다
- 계약이나 layout_context가 없으면 렌더가 거부한다
- 렌더 결과에서 문단 스타일, 문단 스타일의 header margin 정의, 셀 여백이
  바뀌면 렌더가 실패한다
- 반복 확장으로 문단 수가 바뀌는 섹션도 검증 대상으로 남는다
"""
from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderExecutionContext,
    load_content_fields,
    orchestrate_hwpx_render,
    render_candidate_roundtrip,
)
from core.templates.hwpx_content_separator import separate_hwpx_template_content
from core.templates.hwpx_layout_context import LAYOUT_CONTRACT

ROOT = Path(__file__).resolve().parents[2]
FSS = ROOT / "templates" / "institutions" / "금융감독원"
ONE_PAGE = FSS / "금감원 원페이지"
DIRECTOR_REPORT = FSS / "금감원 원장보고"
DIRECTOR_REPORT_CONTENT = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_director_report.input.json"
)
EXECUTION_CONTEXT = RenderExecutionContext(
    "테스트 요청자",
    datetime(2026, 8, 3, tzinfo=timezone.utc),
)

HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" '
    'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" version="1.4">'
    '<hh:refList><hh:paraProperties itemCnt="2">'
    '<hh:paraPr id="7"><hh:margin>'
    '<hc:intent value="-3360" unit="HWPUNIT"/>'
    '<hc:left value="0" unit="HWPUNIT"/>'
    "</hh:margin></hh:paraPr>"
    # 여백 정의가 같고 id만 다른 스타일: 스타일 정체성 자체가 계약임을 보이기 위한 것
    '<hh:paraPr id="8"><hh:margin>'
    '<hc:intent value="-3360" unit="HWPUNIT"/>'
    '<hc:left value="0" unit="HWPUNIT"/>'
    "</hh:margin></hh:paraPr>"
    "</hh:paraProperties></hh:refList></hh:head>"
)
SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">'
    '<hp:p paraPrIDRef="7"><hp:run><hp:t>기관이 실제로 작성한 본문 문장입니다</hp:t></hp:run></hp:p>'
    "</hs:sec>"
)
CONTENT_HPF = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" version="">'
    "<opf:metadata><opf:title>제목</opf:title></opf:metadata>"
    "</opf:package>"
)


def _write_source(path: Path, section: str = SECTION, header: str = HEADER) -> Path:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(
            "mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED
        )
        package.writestr("Contents/header.xml", header)
        package.writestr("Contents/content.hpf", CONTENT_HPF)
        package.writestr("Contents/section0.xml", section)
        package.writestr("settings.xml", "<settings/>")
    return path


def _separated(tmp_path: Path) -> Path:
    template_dir = tmp_path / "candidate"
    separate_hwpx_template_content(
        _write_source(tmp_path / "source.hwpx"),
        template_dir,
        template_id="layout_contract_demo",
        institution="demo",
    )
    return template_dir


def _roundtrip(template_dir: Path, output_name: str = "out.hwpx"):
    return render_candidate_roundtrip(
        template_dir,
        load_content_fields(template_dir / "content.sample.json"),
        template_dir / output_name,
    )


def _rewrite_map(template_dir: Path, change) -> None:
    path = template_dir / "placeholder_map.json"
    mapping = json.loads(path.read_text(encoding="utf-8"))
    change(mapping)
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _replace_in_source(template_dir: Path, part: str, old: str, new: str) -> None:
    """source.hwpx의 한 파트만 바꿔 렌더 결과가 계약을 깨도록 만든다."""
    source = template_dir / "source.hwpx"
    patched = template_dir / "patched.hwpx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(patched, "w") as updated:
        for info in original.infolist():
            payload = original.read(info.filename)
            if info.filename == part:
                text = payload.decode("utf-8")
                assert old in text
                payload = text.replace(old, new, 1).encode("utf-8")
            updated.writestr(info, payload)
    patched.replace(source)


def test_separation_records_a_layout_context_for_every_placeholder(tmp_path: Path) -> None:
    template_dir = _separated(tmp_path)

    mapping = json.loads(
        (template_dir / "placeholder_map.json").read_text(encoding="utf-8")
    )

    assert mapping["layout_contract"] == LAYOUT_CONTRACT
    assert mapping["fields"]
    for field in mapping["fields"]:
        assert field["layout_context"] == {"para_pr_id_ref": "7"}
    # 스타일 정의는 placeholder마다 복사되지 않고 문서 단위로 한 번만 기록된다.
    assert mapping["paragraph_style_margins"] == {
        "7": [
            {
                "intent": {"value": "-3360", "unit": "HWPUNIT"},
                "left": {"value": "0", "unit": "HWPUNIT"},
            }
        ]
    }


def test_render_refuses_a_placeholder_without_a_recorded_layout(tmp_path: Path) -> None:
    template_dir = _separated(tmp_path)
    _rewrite_map(
        template_dir,
        lambda mapping: [field.pop("layout_context") for field in mapping["fields"]],
    )

    with pytest.raises(HwpxTemplateRenderError) as error:
        _roundtrip(template_dir)

    assert "no recorded layout context" in str(error.value)


def test_render_refuses_a_template_that_declares_no_layout_contract(tmp_path: Path) -> None:
    template_dir = _separated(tmp_path)
    _rewrite_map(template_dir, lambda mapping: mapping.pop("layout_contract"))

    with pytest.raises(HwpxTemplateRenderError) as error:
        _roundtrip(template_dir)

    assert f"declares no {LAYOUT_CONTRACT}" in str(error.value)


def test_render_fails_when_the_paragraph_style_changes(tmp_path: Path) -> None:
    """기록을 갱신하지 않고 템플릿 문단 스타일만 바뀌면 렌더가 거부한다."""
    template_dir = _separated(tmp_path)
    section = template_dir / "template" / "section0.template.xml"
    section.write_text(
        section.read_text(encoding="utf-8").replace(
            'paraPrIDRef="7"', 'paraPrIDRef="8"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(HwpxTemplateRenderError) as error:
        _roundtrip(template_dir)

    assert "para_pr_id_ref changed in the rendered document" in str(error.value)


def test_render_fails_when_the_style_margin_definition_changes(tmp_path: Path) -> None:
    """변경 전 규칙("intent/left가 있어야 한다")을 대체하는 검증."""
    template_dir = _separated(tmp_path)
    _replace_in_source(
        template_dir, "Contents/header.xml", '<hc:intent value="-3360"', '<hc:intent value="0"'
    )

    with pytest.raises(HwpxTemplateRenderError) as error:
        _roundtrip(template_dir)

    assert "paragraph style 7 margins changed in the rendered document" in str(error.value)


def test_render_fails_when_a_mapped_cell_margin_changes(tmp_path: Path) -> None:
    mapping = json.loads(
        (ONE_PAGE / "placeholder_map.json").read_text(encoding="utf-8")
    )
    celled = next(
        field for field in mapping["fields"] if field["layout_context"].get("cell_margin")
    )
    output = tmp_path / "one-page.hwpx"

    mapping["fields"] = [
        {
            **field,
            "layout_context": {
                **field["layout_context"],
                "cell_margin": {**field["layout_context"]["cell_margin"], "left": "9999"},
            },
        }
        if field["field_id"] == celled["field_id"]
        else field
        for field in mapping["fields"]
    ]
    template_dir = tmp_path / "one-page"
    template_dir.mkdir()
    for name in ("source.hwpx", "content.sample.json"):
        (template_dir / name).write_bytes((ONE_PAGE / name).read_bytes())
    (template_dir / "template").mkdir()
    for item in (ONE_PAGE / "template").iterdir():
        (template_dir / "template" / item.name).write_bytes(item.read_bytes())
    (template_dir / "placeholder_map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(HwpxTemplateRenderError) as error:
        render_candidate_roundtrip(
            template_dir,
            load_content_fields(template_dir / "content.sample.json"),
            output,
        )

    assert "cell_margin changed in the rendered document" in str(error.value)


def test_repeat_expanded_section_is_still_layout_checked(tmp_path: Path) -> None:
    """반복 확장으로 문단이 늘어난 섹션에도 계약이 적용된다.

    변경 전 금감원 원장보고는 section_paragraph_counts가 없어 렌더 시 서식 검증이
    통째로 건너뛰어졌다.
    """
    mapping = json.loads(
        (DIRECTOR_REPORT / "placeholder_map.json").read_text(encoding="utf-8")
    )
    assert mapping["layout_contract"] == LAYOUT_CONTRACT
    assert all("layout_context" in field for field in mapping["fields"])

    content = json.loads(DIRECTOR_REPORT_CONTENT.read_text(encoding="utf-8"))
    expanded = tmp_path / "확장.hwpx"

    # 반복 항목을 넣어 문단 수가 원본보다 늘어난 상태로 렌더된다.
    orchestrate_hwpx_render(
        DIRECTOR_REPORT,
        content,
        expanded,
        execution_context=EXECUTION_CONTEXT,
    )
    with zipfile.ZipFile(expanded) as package:
        rendered = package.read("Contents/section0.xml").decode("utf-8")
    assert rendered.count("<hp:p ") + rendered.count("<hp:p>") > (
        mapping["section_paragraph_counts"]["section0.xml"]
    )

    # 확장 구간 밖의 문단 스타일이 바뀌면 계약이 그것을 잡아낸다.
    outside = next(
        field
        for field in mapping["fields"]
        if field["field_id"] == "date_01"
    )
    broken = dict(mapping)
    broken["fields"] = [
        {
            **field,
            "layout_context": {
                **field["layout_context"],
                "para_pr_id_ref": "9999",
            },
        }
        if field["field_id"] == outside["field_id"]
        else field
        for field in mapping["fields"]
    ]
    template_dir = _copy_template(DIRECTOR_REPORT, tmp_path / "director", broken)

    with pytest.raises(HwpxTemplateRenderError) as error:
        orchestrate_hwpx_render(
            template_dir,
            content,
            tmp_path / "실패.hwpx",
            execution_context=EXECUTION_CONTEXT,
        )

    assert "para_pr_id_ref changed in the rendered document" in str(error.value)
    assert "date_01" in str(error.value)


def _copy_template(source: Path, destination: Path, mapping: dict) -> Path:
    destination.mkdir(parents=True)
    for name in ("source.hwpx", "content.sample.json", "alias_map.json"):
        if (source / name).is_file():
            (destination / name).write_bytes((source / name).read_bytes())
    (destination / "template").mkdir()
    for item in (source / "template").iterdir():
        (destination / "template" / item.name).write_bytes(item.read_bytes())
    (destination / "placeholder_map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination
