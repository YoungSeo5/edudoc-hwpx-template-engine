from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from core.adapters.hwpx_authoring_resolve import resolve
from core.adapters.hwpx_template_authoring import generate_source_hwpx, load_template_spec


ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"
SPEC = ROOT / "tests" / "fixtures" / "business-status-one-page" / "template_spec.json"


def test_native_hierarchy_intent_retains_resolved_body_left_indent(tmp_path: Path) -> None:
    resolved = resolve(DESIGN, load_template_spec(SPEC))
    source = generate_source_hwpx(resolved, tmp_path / "source.hwpx")

    paragraph_namespace = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    head_namespace = "{http://www.hancom.co.kr/hwpml/2011/head}"
    core_namespace = "{http://www.hancom.co.kr/hwpml/2011/core}"
    with zipfile.ZipFile(source) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
        header_root = ET.fromstring(package.read("Contents/header.xml"))

    hierarchy_paragraphs = {
        "".join(text.text or "" for text in paragraph.iter(f"{paragraph_namespace}t")): paragraph
        for paragraph in section_root.iter(f"{paragraph_namespace}p")
    }
    for text, expected_intent in {
        " ◦ 운영기관 협약 마무리": "-2990",
        "      * 권역별 실행계획 확인": "-4410",
    }.items():
        paragraph = hierarchy_paragraphs[text]
        para_pr = next(
            candidate
            for candidate in header_root.iter(f"{head_namespace}paraPr")
            if candidate.get("id") == paragraph.get("paraPrIDRef")
        )
        margin = next(para_pr.iter(f"{head_namespace}margin"))
        assert next(margin.iter(f"{core_namespace}left")).get("value") == "1417"
        assert next(margin.iter(f"{core_namespace}intent")).get("value") == expected_intent
