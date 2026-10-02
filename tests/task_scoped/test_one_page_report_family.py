"""One-page report family contracts are resolved into generic authoring sections."""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from core.adapters.hwpx_template_authoring import (
    BodySection,
    InfoTableSection,
    TitleSection,
    build_separation_rules,
    load_template_spec,
    write_separation_rules,
)
from core.adapters.hwpx_authoring_resolve import resolve
from core.adapters.hwpx_template_authoring import generate_source_hwpx
from scripts.templates import qa_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"


def test_one_page_recipe_expands_generic_components_in_declared_order(tmp_path: Path) -> None:
    recipe = tmp_path / "recipe.json"
    recipe.write_text(
        json.dumps(
            {
                "family": "one_page_report",
                "recipe_version": "v1",
                "required_components": ["masthead"],
                "component_defaults": {
                    "title_block": {"style": "title"},
                    "header_info": {"style": "info_table"},
                    "section": {"heading_style": "section_title", "body_style": "body"},
                },
            }
        ),
        encoding="utf-8",
    )
    spec_path = tmp_path / "report.json"
    spec_path.write_text(
        json.dumps(
            {
                "template_spec_version": "one-page-report-v1",
                "document_family": "one_page_report",
                "family_recipe": str(recipe),
                "page": {"margins_mm": {"left": 20, "right": 20, "top": 10, "bottom": 10}},
                "components": [
                    {"type": "masthead"},
                    {"type": "title_block", "text": "프로젝트 현황"},
                    {
                        "type": "header_info",
                        "rows": [{"label": "작성일", "field_id": "written_on", "sample_value": "2026-08-18"}],
                    },
                    {"type": "section", "heading_text": "핵심 요약", "field_id": "summary", "sample_value": "요약"},
                ],
            }
        ),
        encoding="utf-8",
    )

    spec = load_template_spec(spec_path)

    assert spec.document_family == "one_page_report"
    assert [type(section) for section in spec.sections] == [
        TitleSection,
        InfoTableSection,
        BodySection,
    ]


def test_two_one_page_specs_share_recipe_and_materialize_without_document_branches(tmp_path: Path) -> None:
    weekly = load_template_spec(ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json")
    project = load_template_spec(ROOT / "tests/fixtures/template-spec/project_one_page.template_spec.json")

    assert weekly.document_family == project.document_family == "one_page_report"
    assert weekly.family_recipe_path == project.family_recipe_path
    assert weekly.component_types[0] == project.component_types[0] == "masthead"
    assert weekly.component_types[-1] == "footer_note"
    assert project.component_types[-1] == "footer_note"
    assert generate_source_hwpx(resolve(DESIGN, weekly), tmp_path / "weekly.hwpx").is_file()
    assert generate_source_hwpx(resolve(DESIGN, project), tmp_path / "project.hwpx").is_file()


def test_one_page_recipe_groups_metadata_and_preserves_section_hierarchy_without_field_branches(
    tmp_path: Path,
    sandbox_qa_registry: Path,
) -> None:
    weekly = load_template_spec(ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json")

    period_info = next(
        section
        for section in weekly.sections
        if isinstance(section, InfoTableSection) and [row.field_id for row in section.rows] == ["report_period"]
    )
    paired_info = next(
        section
        for section in weekly.sections
        if isinstance(section, InfoTableSection) and [row.field_id for row in section.rows] == [
            "author",
            "audience",
            "written_on",
            "document_category",
        ]
    )
    assert period_info.pairs_per_row == 1
    assert paired_info.pairs_per_row == 2
    assert [section.type for section in weekly.sections].count("body_section") == 5
    assert [section.type for section in weekly.sections].count("simple_table") == 1

    source = generate_source_hwpx(resolve(DESIGN, weekly), tmp_path / "weekly.hwpx")
    with zipfile.ZipFile(source) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
        header_root = ET.fromstring(package.read("Contents/header.xml"))
    tables = section_root.findall(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl")
    period_metadata = next(
        table for table in tables if table.get("rowCnt") == "1" and table.get("colCnt") == "2"
    )
    paired_metadata = next(
        table for table in tables if table.get("rowCnt") == "2" and table.get("colCnt") == "4"
    )

    period_widths = [
        int(cell.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz").get("width"))
        for cell in period_metadata.findall(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}tc")
    ]
    paired_widths = [
        int(cell.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz").get("width"))
        for cell in paired_metadata.findall(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}tc")[:4]
    ]
    assert period_widths[0] > paired_widths[0]
    assert paired_widths[0] == paired_widths[2]
    assert abs(paired_widths[1] - paired_widths[3]) <= 1

    heading = next(
        paragraph
        for paragraph in section_root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}p")
        if "".join(text.text or "" for text in paragraph.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}t"))
        == "□ 이번 주 핵심 요약"
    )
    heading_format = next(
        para_pr
        for para_pr in header_root.iter("{http://www.hancom.co.kr/hwpml/2011/head}paraPr")
        if para_pr.get("id") == heading.get("paraPrIDRef")
    )
    assert heading_format.find("{http://www.hancom.co.kr/hwpml/2011/head}breakSetting").get("keepWithNext") == "1"

    table_texts = [
        "".join(text.text or "" for text in table.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}t"))
        for table in tables
    ]
    paragraph_texts = [
        "".join(text.text or "" for text in paragraph.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}t"))
        for paragraph in section_root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}p")
    ]
    assert "□ 다음 주 계획" in paragraph_texts
    assert "◦ 통합 테스트" in paragraph_texts
    assert all("\n" not in paragraph_text for paragraph_text in paragraph_texts)
    assert any("업무명상태일정업무 A완료8/14업무 B진행8/21" == table_text for table_text in table_texts)

    rules = write_separation_rules(
        build_separation_rules(resolve(DESIGN, weekly), source),
        tmp_path / "rules.json",
    )
    candidate = sandbox_qa_registry / "candidates" / "candidate"
    assert qa_hwpx_template.main(
        [
            "--source",
            str(source),
            "--output-dir",
            str(candidate),
            "--institution",
            "edudoc",
            "--document-type",
            "주간업무보고서",
            "--rules",
            str(rules),
        ]
    ) == 0
    values = json.loads((candidate / "content.sample.json").read_text(encoding="utf-8"))["fields"].values()
    assert "◦ 통합 테스트" in values
    assert "업무 A" in values


def test_one_page_template_specs_select_supported_variants_without_family_defaults(
    tmp_path: Path,
) -> None:
    recipe = json.loads(
        (ROOT / "templates/institutions/edudoc/_families/one_page_report/recipe.json").read_text(
            encoding="utf-8"
        )
    )
    assert "row_groups" not in recipe["component_defaults"]["header_info"]

    weekly_raw = json.loads(
        (ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json").read_text(
            encoding="utf-8"
        )
    )
    project_raw = json.loads(
        (ROOT / "tests/fixtures/template-spec/project_one_page.template_spec.json").read_text(
            encoding="utf-8"
        )
    )
    weekly_header = next(component for component in weekly_raw["components"] if component["type"] == "header_info")
    project_header = next(component for component in project_raw["components"] if component["type"] == "header_info")
    assert weekly_header["row_groups"] == [
        {"row_count": 1, "pairs_per_row": 1, "style": "one_page_metadata_wide"},
        {"row_count": 4, "pairs_per_row": 2, "style": "one_page_metadata_pairs"},
    ]
    assert project_header["row_groups"] == [
        {"row_count": 2, "pairs_per_row": 1, "style": "one_page_metadata_wide"}
    ]

    weekly_markers = {
        component["heading_style_override"]["marker"]
        for component in weekly_raw["components"]
        if component["type"] in {"section", "callout", "footer_note"}
    }
    project_markers = {
        component["heading_style_override"]["marker"]
        for component in project_raw["components"]
        if component["type"] in {"section", "status_table", "callout", "footer_note"}
    }
    assert weekly_markers == {"□ "}
    assert project_markers == {"○ "}

    weekly = load_template_spec(ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json")
    project = load_template_spec(ROOT / "tests/fixtures/template-spec/project_one_page.template_spec.json")
    weekly_source = generate_source_hwpx(resolve(DESIGN, weekly), tmp_path / "weekly.hwpx")
    project_source = generate_source_hwpx(resolve(DESIGN, project), tmp_path / "project.hwpx")

    namespace = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    with zipfile.ZipFile(weekly_source) as package:
        weekly_root = ET.fromstring(package.read("Contents/section0.xml"))
        weekly_header = ET.fromstring(package.read("Contents/header.xml"))
    with zipfile.ZipFile(project_source) as package:
        project_root = ET.fromstring(package.read("Contents/section0.xml"))
    weekly_paragraphs = [
        "".join(text.text or "" for text in paragraph.iter(f"{namespace}t"))
        for paragraph in weekly_root.iter(f"{namespace}p")
    ]
    project_paragraphs = [
        "".join(text.text or "" for text in paragraph.iter(f"{namespace}t"))
        for paragraph in project_root.iter(f"{namespace}p")
    ]
    assert "□ 이번 주 핵심 요약" in weekly_paragraphs
    assert "□ 이슈 및 리스크" in weekly_paragraphs
    assert "없음" in weekly_paragraphs
    assert "○ 핵심 요약" in project_paragraphs
    assert "○ 추진 현황" in project_paragraphs

    weekly_heading = next(
        paragraph
        for paragraph in weekly_root.iter(f"{namespace}p")
        if "".join(text.text or "" for text in paragraph.iter(f"{namespace}t")) == "□ 이번 주 핵심 요약"
    )
    heading_style = next(
        style
        for style in weekly_header.iter("{http://www.hancom.co.kr/hwpml/2011/head}paraPr")
        if style.get("id") == weekly_heading.get("paraPrIDRef")
    )
    assert heading_style.find("{http://www.hancom.co.kr/hwpml/2011/head}align").get("horizontal") == "LEFT"
    assert heading_style.find("{http://www.hancom.co.kr/hwpml/2011/head}breakSetting").get("keepWithNext") == "1"
    assert any(
        table.get("rowCnt") == "2" and table.get("colCnt") == "2"
        for table in project_root.iter(f"{namespace}tbl")
    )


def test_one_page_recipe_materializes_native_hierarchy_and_structured_status_table(
    tmp_path: Path,
) -> None:
    raw = json.loads(
        (ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json").read_text(
            encoding="utf-8"
        )
    )
    spec_path = tmp_path / "structured.template_spec.json"
    spec_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    source = generate_source_hwpx(resolve(DESIGN, load_template_spec(spec_path)), tmp_path / "structured.hwpx")
    with zipfile.ZipFile(source) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
        header_root = ET.fromstring(package.read("Contents/header.xml"))

    paragraph_namespace = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    head_namespace = "{http://www.hancom.co.kr/hwpml/2011/head}"
    paragraphs = {
        "".join(text.text or "" for text in paragraph.iter(f"{paragraph_namespace}t")): paragraph
        for paragraph in section_root.iter(f"{paragraph_namespace}p")
    }
    assert {"□ 다음 주 계획", "◦ 통합 테스트", "◦ 결과 보고", "◦ 운영 이관"} <= paragraphs.keys()
    assert all("\n" not in text for text in paragraphs)

    hierarchy_formats = {
        text: next(
            para_pr
            for para_pr in header_root.iter(f"{head_namespace}paraPr")
            if para_pr.get("id") == paragraph.get("paraPrIDRef")
        )
        for text, paragraph in paragraphs.items()
        if text in {"□ 다음 주 계획", "◦ 통합 테스트"}
    }
    core_namespace = "{http://www.hancom.co.kr/hwpml/2011/core}"
    top_level_margin = next(hierarchy_formats["□ 다음 주 계획"].iter(f"{head_namespace}margin"))
    child_margin = next(hierarchy_formats["◦ 통합 테스트"].iter(f"{head_namespace}margin"))
    assert next(top_level_margin.iter(f"{core_namespace}left")).get("value") == "1417"
    assert next(top_level_margin.iter(f"{core_namespace}intent")).get("value") == "-2240"
    assert next(child_margin.iter(f"{core_namespace}intent")).get("value") == "-2990"
    assert all(para_pr.find(f"{head_namespace}tabPr") is None for para_pr in hierarchy_formats.values())

    tables = section_root.findall(f".//{paragraph_namespace}tbl")
    status_table = next(table for table in tables if table.get("rowCnt") == "3" and table.get("colCnt") == "3")
    status_texts = ["".join(text.text or "" for text in cell.iter(f"{paragraph_namespace}t")) for cell in status_table.iter(f"{paragraph_namespace}tc")]
    assert status_texts == ["업무명", "상태", "일정", "업무 A", "완료", "8/14", "업무 B", "진행", "8/21"]
