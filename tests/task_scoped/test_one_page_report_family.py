"""One-page report family contracts are resolved into generic authoring sections."""
from __future__ import annotations

import json
from pathlib import Path

from core.adapters.hwpx_template_authoring import (
    BodySection,
    InfoTableSection,
    TitleSection,
    load_template_spec,
)
from core.adapters.hwpx_authoring_resolve import resolve
from core.adapters.hwpx_template_authoring import generate_source_hwpx


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
