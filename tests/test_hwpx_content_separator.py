from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.templates.hwpx_content_separator import (
    _section_decisions,
    separate_hwpx_template_content,
)
from core.templates.hwpx_separation_rules import load_separation_rules


HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
    "<hh:beginNum/>"
    "</hh:head>"
)
CONTENT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
    "<opf:manifest>"
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    "</opf:manifest>"
    "<opf:spine><opf:itemref idref=\"section0\"/></opf:spine>"
    "</opf:package>"
)
SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="2">'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/>'
    '<hp:subList><hp:p><hp:run><hp:t>현안(이슈)보고</hp:t></hp:run></hp:p></hp:subList>'
    "</hp:tc><hp:tc><hp:cellAddr rowAddr=\"0\" colAddr=\"1\"/>"
    '<hp:subList><hp:p><hp:run><hp:t>가상자산 관련 이상거래 현황파악 진행현황</hp:t></hp:run></hp:p></hp:subList>'
    "</hp:tc></hp:tr></hp:tbl></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>□ 최근 이상매매 정황이 포착됨</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>※ 보고 일정은 별도 안내</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>※ 1페이지 하단에 보고자 및 연락처 등 표시</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>끝.</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)

STRUCTURED_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
    '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    '<hp:p><hp:run><hp:t>Ⅱ.</hp:t><hp:t>향후계획</hp:t></hp:run></hp:p>'
    '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>'
    '<hp:p><hp:run><hp:tbl rowCnt="1" colCnt="3"><hp:tr>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    '<hp:p><hp:run><hp:t>다</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/><hp:subList>'
    '<hp:p><hp:run><hp:t/></hp:run></hp:p></hp:subList></hp:tc>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="2"/><hp:subList>'
    '<hp:p><hp:run><hp:t>검토사항</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    '</hp:tr></hp:tbl></hp:run></hp:p>'
    '<hp:p><hp:run><hp:tbl rowCnt="2" colCnt="2">'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    '<hp:p><hp:run><hp:t>구분</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="1"/><hp:subList>'
    '<hp:p><hp:run><hp:t>검토 결과</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>'
    '<hp:tr><hp:tc><hp:cellAddr rowAddr="1" colAddr="0"/><hp:subList>'
    '<hp:p><hp:run><hp:t>담당 부서</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
    '<hp:tc><hp:cellAddr rowAddr="1" colAddr="1"/><hp:subList>'
    '<hp:p><hp:run><hp:t>디지털감독팀</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>'
    '</hp:tbl></hp:run></hp:p>'
    '<hp:p><hp:run><hp:t>사용자가 문서마다 작성하는 실제 검토 내용</hp:t></hp:run></hp:p>'
    '</hs:sec>'
)


def _write_hwpx(path: Path, section: str = SECTION) -> None:
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/section0.xml", section)
        package.writestr("settings.xml", "<settings/>")


def test_separator_preserves_footer_instruction_as_fixed_text() -> None:
    # Given: a report with the exact fixed footer and a different ※ report text.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "template"
        rules = root / "content-separation-rules.json"
        _write_hwpx(source)
        rules.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "role": "fixed_text",
                            "section": "section0.xml",
                            "text_node_index": 4,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        # When: the source is separated into content and fixed template XML.
        result = separate_hwpx_template_content(
            source,
            output,
            template_id="demo_template",
            template_name="demo",
            institution="demo",
            rules_path=rules,
        )

        content = json.loads(result.content_sample.read_text(encoding="utf-8"))
        mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
        section_template = (output / "template" / "section0.template.xml").read_text(
            encoding="utf-8"
        )

        # Then: only the exact footer stays fixed; the other text remains replaceable.
        assert content["fields"]["document_title_01"] == "가상자산 관련 이상거래 현황파악 진행현황"
        assert content["fields"]["document_title_02"] == "※ 보고 일정은 별도 안내"
        assert content["fields"]["body_paragraph_01"] == "□ 최근 이상매매 정황이 포착됨"
        assert "footer_instruction_01" not in content["fields"]
        assert "가상자산 관련 이상거래 현황파악 진행현황" in section_template
        assert "{{document_title_01}}" not in section_template
        assert "{{document_title_02}}" in section_template
        assert "{{body_paragraph_01}}" in section_template
        assert "※ 1페이지 하단에 보고자 및 연락처 등 표시" in section_template
        assert "{{footer_instruction_01}}" not in section_template
        assert "현안(이슈)보고" in section_template
        assert "끝." in section_template
        table_field = next(
            entry
            for entry in mapping["fields"]
            if entry["field_id"] == "document_title_01"
        )
        assert table_field["replacement_mode"] == "table_cell"
        assert table_field["table"] == 0
        assert table_field["row"] == 0
        assert table_field["col"] == 1
        assert mapping["replacement_mode"] == "mixed"
        assert mapping["classification_rule_set"] == "structural-v1"
        assert mapping["template_rule_count"] == 1
        updated_template = json.loads((output / "template.json").read_text(encoding="utf-8"))
        assert updated_template["content_separation"]["status"] == "candidate"
        assert updated_template["rendering_rules"]["preserve_linesegarray"] is False
        review = result.review.read_text(encoding="utf-8")
        assert "- XML structure, style IDs, and table shapes are preserved." in review
        assert (
            "- Rendering removes `linesegarray` caches from changed sections so "
            "Hancom can recalculate text layout."
        ) in review
        assert (
            "- Rendering retains `linesegarray` caches in unchanged sections."
        ) in review
        assert (
            "- Non-table fields use `<hp:t>` placeholders; table fields use mapped cell coordinates."
            in review
        )
        assert "linesegarray are preserved" not in review


def test_separator_assigns_table_field_ids_in_document_order() -> None:
    # Given: a table value occurs before a later non-table document title.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "template"
        _write_hwpx(source)

        # When: content is separated into the template contract.
        result = separate_hwpx_template_content(
            source,
            output,
            template_id="document_order",
            institution="demo",
        )
        fields = json.loads(result.content_sample.read_text(encoding="utf-8"))["fields"]

        # Then: the table title keeps the first document-title identifier.
        assert fields["document_title_01"] == "가상자산 관련 이상거래 현황파악 진행현황"
        assert fields["document_title_02"] == "※ 보고 일정은 별도 안내"


def test_separator_records_section_ordinal_for_non_contiguous_filename(
    tmp_path: Path,
) -> None:
    # Given: the second extracted section is named section2.xml.
    section = tmp_path / "section2.xml"
    section.write_text(SECTION, encoding="utf-8")

    # When: its table fields are separated as the second package section.
    _, table_fields = _section_decisions(
        section,
        load_separation_rules(None),
        {},
        section_index=1,
    )

    # Then: the table-fill contract uses the package ordinal, not filename suffix 2.
    assert table_fields[0]["section_index"] == 1


def test_separator_uses_structure_roles_and_keeps_user_values_replaceable() -> None:
    # Given: section markers, table labels, and document-specific values share one HWPX.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "template"
        _write_hwpx(source, STRUCTURED_SECTION)

        # When: the source is separated using common structural rules only.
        result = separate_hwpx_template_content(
            source,
            output,
            template_id="structured_template",
            template_name="structured",
            institution="demo",
        )

        mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
        placeholders = {
            entry["sample_value"]: entry["placeholder"] for entry in mapping["fields"]
        }
        section_template = (output / "template" / "section0.template.xml").read_text(
            encoding="utf-8"
        )

        # Then: fixed structure stays literal, while per-document values stay replaceable.
        assert {
            "Ⅱ.",
            "다",
            "검토사항",
            "향후계획",
            "구분",
            "검토 결과",
            "담당 부서",
        }.isdisjoint(placeholders)
        assert "디지털감독팀" in placeholders
        assert "사용자가 문서마다 작성하는 실제 검토 내용" in placeholders
        assert "Ⅱ." in section_template
        assert "다" in section_template
        assert "검토사항" in section_template
        assert "향후계획" in section_template
        department_entry = next(
            entry
            for entry in mapping["fields"]
            if entry["sample_value"] == "디지털감독팀"
        )
        assert department_entry["replacement_mode"] == "table_cell"
        assert department_entry["table"] == 2
        assert department_entry["row"] == 1
        assert department_entry["col"] == 1
        assert "디지털감독팀" in section_template
        assert placeholders["디지털감독팀"] not in section_template
        assert placeholders["사용자가 문서마다 작성하는 실제 검토 내용"] in section_template


def test_separator_is_deterministic_for_the_same_source() -> None:
    # Given: one HWPX source and two fresh output directories.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        _write_hwpx(source, STRUCTURED_SECTION)

        # When: the same source is separated twice.
        first = separate_hwpx_template_content(
            source,
            root / "first",
            template_id="structured_template",
            institution="demo",
        )
        second = separate_hwpx_template_content(
            source,
            root / "second",
            template_id="structured_template",
            institution="demo",
        )

        # Then: every content-separation derivative is byte-identical.
        assert first.content_sample.read_bytes() == second.content_sample.read_bytes()
        assert first.placeholder_map.read_bytes() == second.placeholder_map.read_bytes()
        assert first.review.read_bytes() == second.review.read_bytes()
        assert (
            first.output_dir / "template" / "section0.template.xml"
        ).read_bytes() == (
            second.output_dir / "template" / "section0.template.xml"
        ).read_bytes()


def _one_paragraph_section(text: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
        "</hs:sec>"
    )


def _write_two_section_hwpx(path: Path, section0: str, section1: str) -> None:
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
        "<opf:manifest>"
        '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
        '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
        '<opf:item id="section1" href="Contents/section1.xml" media-type="application/xml"/>'
        "</opf:manifest>"
        '<opf:spine><opf:itemref idref="section0"/><opf:itemref idref="section1"/></opf:spine>'
        "</opf:package>"
    )
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", content)
        package.writestr("Contents/section0.xml", section0)
        package.writestr("Contents/section1.xml", section1)
        package.writestr("settings.xml", "<settings/>")


def test_separator_assigns_globally_unique_field_ids_across_sections() -> None:
    # Given: two sections whose replaceable content collides under per-section numbering.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "template"
        _write_two_section_hwpx(
            source,
            _one_paragraph_section("첫째 섹션의 실제 작성 내용입니다"),
            _one_paragraph_section("둘째 섹션의 실제 작성 내용입니다"),
        )

        # When: the source is separated into content and template XML.
        result = separate_hwpx_template_content(
            source, output, template_id="multi_section", institution="demo"
        )

        content = json.loads(result.content_sample.read_text(encoding="utf-8"))
        mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
        field_ids = [entry["field_id"] for entry in mapping["fields"]]

        # Then: field ids stay globally unique, so no section overwrites another's value.
        assert len(field_ids) == len(set(field_ids))
        assert len(content["fields"]) == len(mapping["fields"])
        sections = {entry["section"] for entry in mapping["fields"]}
        assert {"section0.xml", "section1.xml"} <= sections
        assert "첫째 섹션의 실제 작성 내용입니다" in content["fields"].values()
        assert "둘째 섹션의 실제 작성 내용입니다" in content["fields"].values()


def test_separator_records_paragraph_style_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source.hwpx"
        output = root / "template"
        header = HEADER.replace(
            "<hh:beginNum/>",
            '<hh:paraPr id="7"><hh:margin>'
            '<hc:intent xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" value="-3360"/>'
            '<hc:left xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" value="0"/>'
            "</hh:margin></hh:paraPr>",
        )
        section = SECTION.replace("<hp:p>", '<hp:p paraPrIDRef="7">')
        with zipfile.ZipFile(source, "w") as package:
            package.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
            package.writestr("Contents/header.xml", header)
            package.writestr("Contents/content.hpf", CONTENT)
            package.writestr("Contents/section0.xml", section)
            package.writestr("settings.xml", "<settings/>")

        result = separate_hwpx_template_content(
            source, output, template_id="styled_template", institution="demo"
        )

        mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
        assert mapping["section_paragraph_counts"] == {"section0.xml": 7}
        assert all(
            entry["layout_context"]["para_pr_id_ref"] == "7"
            for entry in mapping["fields"]
        )
        assert all(isinstance(entry["paragraph_index"], int) for entry in mapping["fields"])
        assert all(
            entry["layout_context"]["cell_margin"] is None
            for entry in mapping["fields"]
            if entry["table"] is not None
        )


if __name__ == "__main__":
    test_separator_preserves_footer_instruction_as_fixed_text()
    print("PASS: HWPX content separator")
