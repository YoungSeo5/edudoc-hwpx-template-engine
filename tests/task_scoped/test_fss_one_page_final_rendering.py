from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from core.adapters.hwpx_template_input import RenderExecutionContext
from core.adapters.hwpx_template_renderer import validate_hwpx_output
from core.document_api import render_approved_document, validate_template_content
from core.document_api import service as document_service

ROOT = Path(__file__).resolve().parents[2]
ONE_PAGE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원페이지"
)
CONTENT_PATH = (
    ROOT / "tests" / "fixtures" / "template-content" / "fss_one_page.input.json"
)
EXECUTION_CONTEXT = RenderExecutionContext(
    requester_name="오영서",
    requested_at=datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc),
)


def _content() -> dict[str, str]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def _approved_one_page_root(tmp_path: Path) -> Path:
    registry_root = tmp_path / "institutions"
    destination = registry_root / "금융감독원" / "금감원 원페이지"
    shutil.copytree(ONE_PAGE_DIR, destination)
    template_path = destination / "template.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    template["status"] = "approved"
    template_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return registry_root


def test_one_page_prepares_human_input_into_template_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = json.loads(
        (ONE_PAGE_DIR / "template.json").read_text(encoding="utf-8")
    )
    assert template["status"] == "candidate"
    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", _approved_one_page_root(tmp_path))
    prepared = validate_template_content(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        EXECUTION_CONTEXT,
    )

    assert prepared.template_id == "fss_one_page"
    assert prepared.render_plan.field_values["content_01"] == (
        "주요 현안 진행상황 및 대응방안"
    )
    assert _content()["통계 주석"] == "주요 지표 기준"
    assert prepared.render_plan.field_values["stat_note_01"] == "* 주요 지표 기준"
    assert prepared.package_metadata.title == "주요 현안 진행상황 및 대응방안"
    assert prepared.package_metadata.subject == "주요 현안 진행상황"
    assert prepared.package_metadata.description == (
        "주요 현안의 진행 경과와 위험 요인을 점검한다."
    )
    assert prepared.package_metadata.report_date == "2026-08-06T08:00:00Z"
    assert prepared.package_metadata.keywords == (
        "주요 현안 진행상황 및 대응방안, 주요 현안 진행상황"
    )


def test_one_page_renders_through_the_approved_template_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", _approved_one_page_root(tmp_path))
    output = tmp_path / "금감원_원페이지.hwpx"

    result = render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
        hpf = package.read("Contents/content.hpf").decode("utf-8")
        preview = package.read("Preview/PrvText.txt").decode("utf-8")

    assert result.title_updated is True
    validate_hwpx_output(output)
    assert "{{" not in section
    assert "주요 현안 진행상황 및 대응방안" in section
    assert "(디지털금융국 현안대응팀, 2026. 8. 6.)" in section
    assert "* 주요 지표 기준" in section
    assert "† 세부 수치는 잠정치" in section
    assert "〈주요 현안 관련 현황〉" in section
    assert "⇨ 주요 위험을 조기에 포착해 필요한 대응 조치를 지속한다." in section
    assert "<opf:title>주요 현안 진행상황 및 대응방안</opf:title>" in hpf
    expected_metadata = {
        "creator": "오영서",
        "subject": "주요 현안 진행상황",
        "description": "주요 현안의 진행 경과와 위험 요인을 점검한다.",
        "lastsaveby": "오영서",
        "date": "2026-08-06T08:00:00Z",
        "keyword": "주요 현안 진행상황 및 대응방안, 주요 현안 진행상황",
        "CreatedDate": "2026-08-06T08:00:00Z",
        "ModifiedDate": "2026-08-06T08:00:00Z",
    }
    metadata = {
        element.attrib["name"]: element.text
        for element in ElementTree.fromstring(hpf).iter()
        if element.tag.endswith("meta") and "name" in element.attrib
    }
    for name, value in expected_metadata.items():
        assert metadata[name] == value
    assert "주요 현안 진행상황 및 대응방안" in preview


def test_one_page_preserves_recorded_marker_paragraph_styles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping = json.loads(
        (ONE_PAGE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", _approved_one_page_root(tmp_path))
    prepared = validate_template_content(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        EXECUTION_CONTEXT,
    )
    output = tmp_path / "문단서식_검증.hwpx"
    render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        rendered_section = ElementTree.fromstring(package.read("Contents/section0.xml"))
        rendered_header = ElementTree.fromstring(package.read("Contents/header.xml"))
    raw_section = ElementTree.fromstring(
        (ONE_PAGE_DIR / "raw" / "section0.xml").read_bytes()
    )
    template_section = ElementTree.fromstring(
        (ONE_PAGE_DIR / "template" / "section0.template.xml").read_bytes()
    )
    namespace = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    raw_paragraphs = raw_section.findall(".//hp:p", namespace)
    template_paragraphs = template_section.findall(".//hp:p", namespace)
    rendered_paragraphs = rendered_section.findall(".//hp:p", namespace)

    assert len(raw_paragraphs) == mapping["section_paragraph_counts"]["section0.xml"]
    assert len(template_paragraphs) == len(raw_paragraphs)
    assert len(rendered_paragraphs) == len(raw_paragraphs)
    fields = {entry["field_id"]: entry for entry in mapping["fields"]}
    header_style_ids = {
        paragraph_style.attrib["id"]
        for paragraph_style in rendered_header.iter()
        if paragraph_style.tag.endswith("paraPr")
        and {node.tag.rsplit("}", 1)[-1] for node in paragraph_style.iter()}
        >= {"margin", "intent", "left"}
        and "id" in paragraph_style.attrib
    }
    marker_field_ids = {
        "body_bullet_01",
        "body_bullet_02",
        "stat_note_01",
        "detail_note_01",
        "body_bullet_03",
        "stat_note_02",
        "body_bullet_04",
        "body_bullet_05",
        "conclusion_01",
    }
    for field_id in marker_field_ids:
        field = fields[field_id]
        paragraph_index = field["paragraph_index"]
        expected_style = field["layout_context"]["para_pr_id_ref"]
        raw_paragraph = raw_paragraphs[paragraph_index]
        template_paragraph = template_paragraphs[paragraph_index]
        rendered_paragraph = rendered_paragraphs[paragraph_index]

        assert raw_paragraph.attrib.get("paraPrIDRef") == expected_style
        assert template_paragraph.attrib.get("paraPrIDRef") == expected_style
        assert rendered_paragraph.attrib.get("paraPrIDRef") == expected_style
        assert expected_style in header_style_ids
        assert field["placeholder"] in "".join(template_paragraph.itertext())
        assert prepared.render_plan.field_values[field_id] in "".join(
            rendered_paragraph.itertext()
        )

    for field in fields.values():
        if field["table"] is None:
            continue
        expected_margin = field["layout_context"]["cell_margin"]
        assert _cell_margin(raw_section, field) == expected_margin
        assert _cell_margin(template_section, field) == expected_margin
        assert _cell_margin(rendered_section, field) == expected_margin


def test_one_page_preserves_marker_leading_fwspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping = json.loads(
        (ONE_PAGE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", _approved_one_page_root(tmp_path))
    output = tmp_path / "marker_indent.hwpx"
    render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        rendered_section = ElementTree.fromstring(package.read("Contents/section0.xml"))
    raw_section = ElementTree.fromstring(
        (ONE_PAGE_DIR / "raw" / "section0.xml").read_bytes()
    )
    template_section = ElementTree.fromstring(
        (ONE_PAGE_DIR / "template" / "section0.template.xml").read_bytes()
    )
    namespace = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    raw_paragraphs = raw_section.findall(".//hp:p", namespace)
    template_paragraphs = template_section.findall(".//hp:p", namespace)
    rendered_paragraphs = rendered_section.findall(".//hp:p", namespace)

    marker_categories = {"body_bullet", "stat_note", "detail_note"}
    marker_fields = [
        field for field in mapping["fields"] if field["category"] in marker_categories
    ]
    assert marker_fields
    for field in marker_fields:
        paragraph_index = field["paragraph_index"]
        expected = _leading_fwspace_count(raw_paragraphs[paragraph_index])
        assert expected > 0
        assert field["layout_context"]["leading_fwspace_count"] == expected
        assert _leading_fwspace_count(template_paragraphs[paragraph_index]) == expected
        assert _leading_fwspace_count(rendered_paragraphs[paragraph_index]) == expected


def test_one_page_preserves_content_18_trailing_fwspaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping = json.loads(
        (ONE_PAGE_DIR / "placeholder_map.json").read_text(encoding="utf-8")
    )
    field = next(item for item in mapping["fields"] if item["field_id"] == "content_18")
    raw_section = (ONE_PAGE_DIR / "raw" / "section0.xml").read_bytes()
    template_section = (
        ONE_PAGE_DIR / "template" / "section0.template.xml"
    ).read_bytes()
    expected = _edge_fwspace_counts_at(raw_section, field["text_node_index"])

    assert expected == (0, 2)
    assert "leading_fwspace_count" not in field["layout_context"]
    assert field["layout_context"]["trailing_fwspace_count"] == expected[1]
    assert _edge_fwspace_counts_at(template_section, field["text_node_index"]) == expected

    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", _approved_one_page_root(tmp_path))
    output = tmp_path / "content_18_indent.hwpx"
    render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        rendered_section = package.read("Contents/section0.xml")
    assert _edge_fwspace_counts_at(rendered_section, field["text_node_index"]) == expected


def test_one_page_restores_table_cell_leading_fwspaces_after_skill_fill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_root = _approved_one_page_root(tmp_path)
    template_dir = registry_root / "금융감독원" / "금감원 원페이지"
    mapping_path = template_dir / "placeholder_map.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    field = next(item for item in mapping["fields"] if item["field_id"] == "content_15")
    expected = field["layout_context"]["leading_fwspace_count"]
    field["replacement_mode"] = "table_cell"
    mapping_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(document_service, "_TEMPLATE_ROOT", registry_root)

    output = tmp_path / "table_cell_indent.hwpx"
    render_approved_document(
        "금융감독원",
        "금감원 원페이지",
        _content(),
        output,
        EXECUTION_CONTEXT,
    )

    with zipfile.ZipFile(output) as package:
        rendered_section = ElementTree.fromstring(package.read("Contents/section0.xml"))
    assert _table_cell_leading_fwspace_count(rendered_section, field) == expected


def _cell_margin(section: ElementTree.Element, field: dict) -> dict[str, str] | None:
    local_name = lambda tag: tag.rsplit("}", 1)[-1]
    tables = [node for node in section.iter() if local_name(node.tag) == "tbl"]
    table = tables[field["table"]]
    cell = next(
        node
        for node in table.iter()
        if local_name(node.tag) == "tc"
        and any(
            local_name(child.tag) == "cellAddr"
            and child.attrib.get("rowAddr") == str(field["row"])
            and child.attrib.get("colAddr") == str(field["col"])
            for child in node
        )
    )
    margin = next(
        (child for child in cell if local_name(child.tag) == "cellMargin"),
        None,
    )
    return dict(margin.attrib) if margin is not None else None


def _leading_fwspace_count(paragraph: ElementTree.Element) -> int:
    local_name = lambda tag: tag.rsplit("}", 1)[-1]
    text = next((node for node in paragraph.iter() if local_name(node.tag) == "t"), None)
    if text is None:
        return 0
    count = 0
    for child in text:
        if local_name(child.tag) != "fwSpace":
            break
        count += 1
        if child.tail and child.tail.strip():
            break
    return count


def _edge_fwspace_counts_at(section: bytes, text_node_index: int) -> tuple[int, int]:
    root = ElementTree.fromstring(section)
    texts = [
        node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "t"
    ]
    text = texts[text_node_index]
    leading = 0
    if not (text.text and text.text.strip()):
        for child in text:
            if child.tag.rsplit("}", 1)[-1] != "fwSpace":
                break
            leading += 1
            if child.tail and child.tail.strip():
                break
    trailing = 0
    for child in reversed(text):
        if child.tail and child.tail.strip():
            break
        if child.tag.rsplit("}", 1)[-1] != "fwSpace":
            break
        trailing += 1
    return leading, trailing


def _table_cell_leading_fwspace_count(
    section: ElementTree.Element,
    field: dict,
) -> int:
    local_name = lambda tag: tag.rsplit("}", 1)[-1]
    tables = [node for node in section.iter() if local_name(node.tag) == "tbl"]
    table = tables[field["table"]]
    cell = next(
        node
        for node in table.iter()
        if local_name(node.tag) == "tc"
        and any(
            local_name(child.tag) == "cellAddr"
            and child.attrib.get("rowAddr") == str(field["row"])
            and child.attrib.get("colAddr") == str(field["col"])
            for child in node
        )
    )
    return _leading_fwspace_count(cell)
