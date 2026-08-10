"""core.adapters.hwpx_template_renderer: fill {{placeholder}}s -> filled HWPX.

Proves the renderer fills a template's placeholders from a content mapping
(honestly: missing fields stay {{placeholder}}, values are XML-escaped), and
repacks the filled sections into a byte-perfect copy of a base HWPX.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import hwpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xml.etree import ElementTree

from core.adapters.hwpx_alias_map import AliasMap, RepeatBlock
from core.templates.hwpx_layout_context import LAYOUT_CONTRACT, DocumentLayout
from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    fill_template_sections,
    load_content_fields,
    render_candidate_roundtrip,
    render_repeat_block,
    snapshot_source_hwpx,
    validate_hwpx_output,
)

ROOT = Path(__file__).resolve().parent.parent
FSS_DIR = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고 가상자산"
REGISTERED_FSS_DIRS = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고",
    FSS_DIR,
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원페이지",
)
BROTHER_HWPX = ROOT / "references" / "document-types" / "public-plan" / "브라더 공공기관 보고서 양식.hwpx"


def test_fill_fss_full_content_has_no_leftover() -> None:
    content = load_content_fields(FSS_DIR / "content.sample.json")
    sections, result = fill_template_sections(FSS_DIR, content)

    assert len(result.filled_fields) == 11
    assert result.missing_fields == []
    assert result.leftover_placeholders == []
    section0 = sections["Contents/section0.xml"]
    assert "가상자산감독국" in section0 and "{{" not in section0


def test_fill_reports_missing_and_keeps_placeholder() -> None:
    # only two of the mapped fields provided
    content = {"date_01": "(2026. 1. 1.)", "document_title_01": "테스트 제목"}
    sections, result = fill_template_sections(FSS_DIR, content)

    section0 = sections["Contents/section0.xml"]
    assert "(2026. 1. 1.)" in section0 and "테스트 제목" in section0
    assert set(result.filled_fields) == {"date_01", "document_title_01"}
    assert "body_paragraph_01" in result.missing_fields
    assert "{{body_paragraph_01}}" in section0            # kept, never invented
    assert "body_paragraph_01" in result.leftover_placeholders


def _parseable(template_xml: str) -> str:
    """네임스페이스 선언 없이 <hp:p>만 쓴 합성 조각도 파싱할 수 있게 감싼다."""
    try:
        ElementTree.fromstring(template_xml)
    except ElementTree.ParseError:
        return (
            '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f"{template_xml}</hp:sec>"
        )
    return template_xml


def _write_template_dir(
    tmp: Path,
    template_xml: str,
    field_id: str,
    header_xml: bytes | None = None,
) -> Path:
    (tmp / "template").mkdir(parents=True)
    (tmp / "template" / "section0.template.xml").write_text(template_xml, encoding="utf-8")
    if header_xml is None:
        header_xml = zipfile.ZipFile(BROTHER_HWPX).read("Contents/header.xml")
    # 합성 템플릿도 분리 단계와 같은 공개 API로 layout 계약을 기록한다.
    parseable = _parseable(template_xml)
    paragraphs = [
        node
        for node in ElementTree.fromstring(parseable).iter()
        if node.tag.rsplit("}", 1)[-1] == "p"
    ]
    placeholder = f"{{{{{field_id}}}}}"
    field = {
        "field_id": field_id,
        "placeholder": placeholder,
        "section": "section0.xml",
        "table": None,
        "row": None,
        "col": None,
        "paragraph_index": next(
            index
            for index, paragraph in enumerate(paragraphs)
            if placeholder in "".join(paragraph.itertext())
        ),
    }
    layout = DocumentLayout.read(parseable, header_xml)
    field["layout_context"] = layout.context_for(field)
    (tmp / "placeholder_map.json").write_text(
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
    return tmp


def test_fill_xml_escapes_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), "<hp:p><hp:t>{{x}}</hp:t></hp:p>", "x")
        sections, _ = fill_template_sections(tmp, {"x": "A & B < C"})
        assert "A &amp; B &lt; C" in sections["Contents/section0.xml"]


def test_fill_removes_stale_linesegarray_after_text_replacement() -> None:
    template_xml = (
        "<hp:p><hp:run><hp:t>{{x}}</hp:t></hp:run>"
        '<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray></hp:p>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), template_xml, "x")
        sections, _ = fill_template_sections(tmp, {"x": "새로 채운 긴 본문"})

    section0 = sections["Contents/section0.xml"]
    assert "새로 채운 긴 본문" in section0
    assert "<hp:linesegarray" not in section0


def test_fill_removes_cache_only_from_changed_section() -> None:
    changed_xml = (
        "<hp:p><hp:run><hp:t>{{x}}</hp:t></hp:run>"
        '<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray></hp:p>'
    )
    unchanged_xml = (
        "<hp:p><hp:run><hp:t>고정 본문</hp:t></hp:run>"
        '<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray></hp:p>'
    )
    with tempfile.TemporaryDirectory() as tmp:
        template_dir = _write_template_dir(Path(tmp), changed_xml, "x")
        (template_dir / "template" / "section1.template.xml").write_text(
            unchanged_xml,
            encoding="utf-8",
        )

        sections, result = fill_template_sections(template_dir, {"x": "변경 본문"})

    assert "<hp:linesegarray" not in sections["Contents/section0.xml"]
    assert sections["Contents/section1.xml"] == unchanged_xml
    assert "<hp:linesegarray" in sections["Contents/section1.xml"]
    assert result.leftover_placeholders == []


def test_fill_handles_short_long_and_newline_values() -> None:
    template_xml = (
        "<hp:p><hp:run><hp:t>{{x}}</hp:t></hp:run>"
        '<hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray></hp:p>'
    )
    values = (
        "짧은 문구",
        "긴 문구 " * 80,
        "첫째 줄\n둘째 줄",
    )
    for value in values:
        with tempfile.TemporaryDirectory() as tmp:
            template_dir = _write_template_dir(Path(tmp), template_xml, "x")

            sections, result = fill_template_sections(template_dir, {"x": value})

        section0 = sections["Contents/section0.xml"]
        assert escape(value) in section0
        assert result.leftover_placeholders == []
        assert "{{" not in section0
        assert "<hp:linesegarray" not in section0


def test_registered_fss_templates_render_text_shapes_without_placeholders() -> None:
    values = (
        "짧은 문구",
        "긴 문구 " * 80,
        "첫째 줄\n둘째 줄",
    )
    for template_dir in REGISTERED_FSS_DIRS:
        for index, value in enumerate(values):
            content = load_content_fields(template_dir / "content.sample.json")
            first_field = next(iter(content))
            content[first_field] = value
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / f"rendered-{index}.hwpx"

                result = render_candidate_roundtrip(
                    template_dir,
                    content,
                    output,
                )

                assert result.leftover_placeholders == []
                assert result.missing_fields == []
                with zipfile.ZipFile(output) as package:
                    for template_file in sorted(
                        (template_dir / "template").glob("section*.template.xml")
                    ):
                        section_number = re.search(r"section(\d+)", template_file.name)
                        assert section_number is not None
                        section_xml = package.read(
                            f"Contents/section{section_number.group(1)}.xml"
                        ).decode("utf-8")
                        assert "{{" not in section_xml
                        assert "<hp:linesegarray" not in section_xml
                validation = hwpx.validate_package(output)
                assert validation.ok is True
                assert list(validation.errors) == []


def test_render_replaces_only_section_in_base_hwpx() -> None:
    section0 = zipfile.ZipFile(BROTHER_HWPX).read("Contents/section0.xml").decode("utf-8")
    # turn the first non-empty <hp:t> into a placeholder, keep the rest byte-identical
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(f"<hp:t>{target}</hp:t>", "<hp:t>{{demo_field}}</hp:t>", 1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), template_xml, "demo_field")
        out = Path(tmp) / "rendered.hwpx"
        result = render_candidate_roundtrip(tmp, {"demo_field": "RENDER_OK"}, out, base_hwpx=BROTHER_HWPX)

        assert result.leftover_placeholders == []
        assert result.filled_fields == ["demo_field"]
        assert out.exists() and out.read_bytes()[:2] == b"PK"
        with zipfile.ZipFile(out) as z:
            assert z.namelist()[0] == "mimetype"           # base order preserved
            filled = z.read("Contents/section0.xml").decode("utf-8")
            assert "RENDER_OK" in filled and "{{" not in filled
            # everything else stays byte-identical to the base
            assert z.read("Contents/header.xml") == zipfile.ZipFile(BROTHER_HWPX).read("Contents/header.xml")


def test_self_contained_template_renders_without_external_base() -> None:
    """A template with a source.hwpx snapshot renders with no external base file."""
    section0 = zipfile.ZipFile(BROTHER_HWPX).read("Contents/section0.xml").decode("utf-8")
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(f"<hp:t>{target}</hp:t>", "<hp:t>{{demo_field}}</hp:t>", 1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), template_xml, "demo_field")
        snapshot_source_hwpx(BROTHER_HWPX, tmp)          # self-contain: byte copy of original
        assert (tmp / "source.hwpx").read_bytes() == BROTHER_HWPX.read_bytes()

        out = Path(tmp) / "rendered.hwpx"
        result = render_candidate_roundtrip(tmp, {"demo_field": "RENDER_OK"}, out)  # no base_hwpx

        assert result.leftover_placeholders == []
        with zipfile.ZipFile(out) as z:
            assert z.namelist()[0] == "mimetype"
            assert "RENDER_OK" in z.read("Contents/section0.xml").decode("utf-8")


def test_render_validates_output_by_default() -> None:
    """Default validate=True: the rendered HWPX passes strict package validation."""
    section0 = zipfile.ZipFile(BROTHER_HWPX).read("Contents/section0.xml").decode("utf-8")
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(f"<hp:t>{target}</hp:t>", "<hp:t>{{demo_field}}</hp:t>", 1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), template_xml, "demo_field")
        out = Path(tmp) / "rendered.hwpx"
        render_candidate_roundtrip(tmp, {"demo_field": "OK"}, out, base_hwpx=BROTHER_HWPX)  # validate=True
        validate_hwpx_output(out)  # explicit: no error means strict validation passed


def test_render_repairs_missing_hwpunitchar_root_namespace(tmp_path: Path) -> None:
    declaration = (
        b' xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"'
    )
    broken_base = tmp_path / "missing-namespace.hwpx"
    with zipfile.ZipFile(BROTHER_HWPX) as source, zipfile.ZipFile(
        broken_base,
        "w",
    ) as destination:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/header.xml" or re.fullmatch(
                r"Contents/section\d+\.xml",
                info.filename,
            ):
                payload = payload.replace(declaration, b"")
            destination.writestr(info, payload)

    broken_validation = hwpx.validate_package(broken_base)
    assert not broken_validation.ok
    assert any("hwpunitchar" in issue.message for issue in broken_validation.errors)

    section0 = zipfile.ZipFile(broken_base).read("Contents/section0.xml").decode("utf-8")
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(
        f"<hp:t>{target}</hp:t>",
        "<hp:t>{{demo_field}}</hp:t>",
        1,
    )
    template_dir = _write_template_dir(tmp_path / "candidate", template_xml, "demo_field")
    output = tmp_path / "rendered.hwpx"

    render_candidate_roundtrip(
        template_dir,
        {"demo_field": "RENDER_OK"},
        output,
        base_hwpx=broken_base,
    )

    validation = hwpx.validate_package(output)
    assert validation.ok
    with zipfile.ZipFile(output) as package:
        assert declaration.strip() in package.read("Contents/header.xml")
        assert declaration.strip() in package.read("Contents/section0.xml")


def test_render_without_any_base_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = _write_template_dir(Path(tmp), "<hp:p><hp:t>{{x}}</hp:t></hp:p>", "x")
        try:
            render_candidate_roundtrip(tmp, {"x": "v"}, Path(tmp) / "out.hwpx")
        except HwpxTemplateRenderError as exc:
            assert "self-contained" in str(exc)
        else:
            raise AssertionError("expected HwpxTemplateRenderError when no base is available")


def _repeat_alias_map() -> AliasMap:
    return AliasMap(
        template_id="repeat_guard",
        aliases={},
        blocks={
            "본문": RepeatBlock(
                anchor="body_paragraph_01",
                levels={
                    0: ("body_paragraph_01", "□ "),
                    1: ("body_bullet_01", " ◦ "),
                },
            )
        },
    )


def _repeat_xml(between: str) -> str:
    return (
        '<hp:p id="1" paraPrIDRef="1"><hp:run charPrIDRef="1">'
        "<hp:t>{{body_paragraph_01}}</hp:t></hp:run></hp:p>"
        + between
        + '<hp:p id="3" paraPrIDRef="2"><hp:run charPrIDRef="2">'
        "<hp:t>{{body_bullet_01}}</hp:t></hp:run></hp:p>"
    )


_REPEAT_ITEMS = {"body_paragraph_01": [[0, "가"], [1, "나"]]}


def test_repeat_block_keeps_deleting_blank_paragraphs_between_levels() -> None:
    blank = '<hp:p id="2" paraPrIDRef="1"><hp:run charPrIDRef="1"><hp:t></hp:t></hp:run></hp:p>'

    filled_xml, filled, _ = render_repeat_block(
        _repeat_xml(blank), _REPEAT_ITEMS, _repeat_alias_map().blocks
    )

    assert filled == {"body_paragraph_01", "body_bullet_01"}
    assert "□ 가" in filled_xml
    assert " ◦ 나" in filled_xml
    assert "{{" not in filled_xml


def test_repeat_block_refuses_to_delete_text_between_levels() -> None:
    note = (
        '<hp:p id="2" paraPrIDRef="1"><hp:run charPrIDRef="1">'
        "<hp:t>※ 금액은 백만원 단위로 표기</hp:t></hp:run></hp:p>"
    )

    try:
        render_repeat_block(
            _repeat_xml(note),
            _REPEAT_ITEMS,
            _repeat_alias_map().blocks,
        )
    except HwpxTemplateRenderError as exc:
        assert "※ 금액은 백만원 단위로 표기" in str(exc)
    else:
        raise AssertionError("expected HwpxTemplateRenderError for text inside the repeat region")


def test_repeat_block_refuses_to_delete_objects_between_levels() -> None:
    table = (
        '<hp:p id="2" paraPrIDRef="1"><hp:run charPrIDRef="1"><hp:tbl rowCnt="1" colCnt="1">'
        '<hp:tr><hp:tc><hp:subList><hp:p id="9"><hp:run charPrIDRef="1">'
        "<hp:t></hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr>"
        "</hp:tbl></hp:run></hp:p>"
    )

    try:
        render_repeat_block(
            _repeat_xml(table),
            _REPEAT_ITEMS,
            _repeat_alias_map().blocks,
        )
    except HwpxTemplateRenderError as exc:
        assert "'object'" in str(exc)
    else:
        raise AssertionError("expected HwpxTemplateRenderError for an object inside the repeat region")


if __name__ == "__main__":
    test_fill_fss_full_content_has_no_leftover()
    test_fill_reports_missing_and_keeps_placeholder()
    test_fill_xml_escapes_values()
    test_fill_removes_stale_linesegarray_after_text_replacement()
    test_fill_removes_cache_only_from_changed_section()
    test_fill_handles_short_long_and_newline_values()
    test_registered_fss_templates_render_text_shapes_without_placeholders()
    test_render_replaces_only_section_in_base_hwpx()
    test_self_contained_template_renders_without_external_base()
    test_render_validates_output_by_default()
    test_render_without_any_base_raises()
    test_repeat_block_keeps_deleting_blank_paragraphs_between_levels()
    test_repeat_block_refuses_to_delete_text_between_levels()
    test_repeat_block_refuses_to_delete_objects_between_levels()
    print("PASS: HWPX template renderer (fill + honest missing + byte-perfect repack)")
