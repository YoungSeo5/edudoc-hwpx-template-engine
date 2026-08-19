"""최종 문서 생성과 제작 중 QA를 두 경로로 분리한 계약.

- 승인 템플릿의 최종 생성: metadata 계약과 실행 문맥이 반드시 있어야 하고,
  content.hpf 9개 값이 갱신된다. 없으면 생성을 거부한다.
- 제작 중 후보 템플릿 QA: metadata 없이 구조·서식만 왕복하며
  content.hpf를 원본 그대로 둔다.

변경 전에는 metadata가 없으면 제목과 날짜 3개만 채우는 폴백 경로로 문서가
생성됐다.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapters.hwpx_template_input import (
    HwpxTemplateInputError,
    prepare_hwpx_template_input,
)
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    RenderExecutionContext,
    orchestrate_hwpx_render,
    render_candidate_roundtrip,
    snapshot_source_hwpx,
)
from core.templates.hwpx_layout_context import LAYOUT_CONTRACT, DocumentLayout

ROOT = Path(__file__).resolve().parents[2]
FSS_DIR = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
CONTENT_PATH = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_director_report.input.json"
)
BROTHER_HWPX = (
    ROOT / "references" / "document-types" / "public-plan"
    / "브라더 공공기관 보고서 양식.hwpx"
)
REQUESTED_AT = datetime(2026, 8, 5, 9, 30, 0, tzinfo=timezone.utc)
EXECUTION_CONTEXT = RenderExecutionContext("오영서", REQUESTED_AT)


def _content() -> dict:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def _hpf(package: Path) -> str:
    with zipfile.ZipFile(package) as archive:
        return archive.read("Contents/content.hpf").decode("utf-8")


def _candidate_template_dir(tmp_path: Path) -> Path:
    """alias_map.json이 없는 제작 중 템플릿 디렉터리."""
    section0 = zipfile.ZipFile(BROTHER_HWPX).read("Contents/section0.xml").decode("utf-8")
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(
        f"<hp:t>{target}</hp:t>", "<hp:t>{{demo_field}}</hp:t>", 1
    )
    (tmp_path / "template").mkdir(parents=True, exist_ok=True)
    (tmp_path / "template" / "section0.template.xml").write_text(
        template_xml,
        encoding="utf-8",
    )
    header_xml = zipfile.ZipFile(BROTHER_HWPX).read("Contents/header.xml")
    paragraphs = [
        node
        for node in ElementTree.fromstring(template_xml).iter()
        if node.tag.rsplit("}", 1)[-1] == "p"
    ]
    field = {
        "field_id": "demo_field",
        "placeholder": "{{demo_field}}",
        "section": "section0.xml",
        "table": None,
        "row": None,
        "col": None,
        "paragraph_index": next(
            index
            for index, paragraph in enumerate(paragraphs)
            if "{{demo_field}}" in "".join(paragraph.itertext())
        ),
    }
    layout = DocumentLayout.read(template_xml, header_xml)
    field["layout_context"] = layout.context_for(field)
    (tmp_path / "placeholder_map.json").write_text(
        json.dumps(
            {
                "layout_contract": LAYOUT_CONTRACT,
                "section_paragraph_counts": {"section0.xml": len(paragraphs)},
                "paragraph_style_margins": layout.margins_of_referenced_styles([field]),
                "fields": [field],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_source_hwpx(BROTHER_HWPX, tmp_path)
    return tmp_path


def _candidate_template_dir_with_metadata(tmp_path: Path) -> Path:
    template_dir = _candidate_template_dir(tmp_path)
    (template_dir / "alias_map.json").write_text(
        json.dumps(
            {
                "fields": {"입력": "demo_field"},
                "metadata": {
                    "title": {"field": "입력"},
                    "report_date": {"context": "requested_at"},
                    "description": {"field": "입력"},
                    "subject": {"field": "입력", "separator": ", "},
                    "keywords": {
                        "separator": ", ",
                        "sources": [{"field": "입력"}],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return template_dir


def test_template_without_alias_map_renders_canonical_content(
    tmp_path: Path,
) -> None:
    template_dir = _candidate_template_dir(tmp_path)

    output = tmp_path / "generic.hwpx"
    result = orchestrate_hwpx_render(
        template_dir,
        {"demo_field": "OK"},
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    assert result.filled_fields == ["demo_field"]
    assert output.is_file()


def test_final_generation_requires_an_execution_context() -> None:
    with pytest.raises(HwpxTemplateInputError, match="requires execution_context"):
        prepare_hwpx_template_input(FSS_DIR, _content())


def test_prepared_content_always_carries_package_metadata() -> None:
    prepared = prepare_hwpx_template_input(
        FSS_DIR,
        _content(),
        execution_context=EXECUTION_CONTEXT,
    )

    assert prepared.package_metadata.creator == "오영서"
    assert prepared.package_metadata.title == "가상자산 이상거래 대응 진행현황"


def test_candidate_roundtrip_leaves_content_hpf_untouched(tmp_path: Path) -> None:
    template_dir = _candidate_template_dir(tmp_path)
    output = tmp_path / "후보왕복.hwpx"

    result = render_candidate_roundtrip(template_dir, {"demo_field": "OK"}, output)

    assert result.title_updated is False
    assert _hpf(output) == _hpf(BROTHER_HWPX)


def test_candidate_roundtrip_still_fills_and_validates(tmp_path: Path) -> None:
    template_dir = _candidate_template_dir(tmp_path)
    output = tmp_path / "후보내용.hwpx"

    result = render_candidate_roundtrip(template_dir, {"demo_field": "왕복확인"}, output)

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")

    assert result.filled_fields == ["demo_field"]
    assert "왕복확인" in section
    assert "{{demo_field}}" not in section


def test_candidate_roundtrip_skips_declared_metadata_without_context(
    tmp_path: Path,
) -> None:
    template_dir = _candidate_template_dir_with_metadata(tmp_path)
    output = tmp_path / "후보_metadata.hwpx"

    result = render_candidate_roundtrip(template_dir, {"입력": "왕복확인"}, output)

    assert result.filled_fields == ["demo_field"]
    assert result.title_updated is False
    assert _hpf(output) == _hpf(BROTHER_HWPX)


def test_final_generation_updates_all_nine_metadata_values(tmp_path: Path) -> None:
    output = tmp_path / "최종.hwpx"

    result = orchestrate_hwpx_render(
        FSS_DIR,
        _content(),
        output,
        execution_context=EXECUTION_CONTEXT,
    )

    filled = _hpf(output)
    assert result.title_updated is True
    assert "<opf:title>가상자산 이상거래 대응 진행현황</opf:title>" in filled
    for name, value in (
        ("creator", "오영서"),
        ("lastsaveby", "오영서"),
        ("date", "2026. 7. 30."),
        ("CreatedDate", "2026-08-05T09:30:00Z"),
        ("ModifiedDate", "2026-08-05T09:30:00Z"),
    ):
        assert f'name="{name}"' in filled
        assert value in filled
