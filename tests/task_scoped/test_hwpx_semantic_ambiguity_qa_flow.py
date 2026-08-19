from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.templates.hwpx_content_separator import separate_hwpx_template_content
from core.templates.hwpx_semantic_classifier import SemanticAmbiguityError


SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:run><hp:t>- 부제 -</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)
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
    '<opf:spine><opf:itemref idref="section0"/></opf:spine>'
    "</opf:package>"
)


def _source_hwpx(tmp_path: Path) -> Path:
    import zipfile

    source = tmp_path / "marker.hwpx"
    with zipfile.ZipFile(source, "w") as package:
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/section0.xml", SECTION)
    return source


def _source_hwpx_with_section(tmp_path: Path, name: str, section: str) -> Path:
    import zipfile

    source = tmp_path / name
    with zipfile.ZipFile(source, "w") as package:
        package.writestr("Contents/header.xml", HEADER)
        package.writestr("Contents/content.hpf", CONTENT)
        package.writestr("Contents/section0.xml", section)
    return source


# 회귀: 사람이 "fixed"로 확정한 same-node 표식 경계 노드가 legacy 구조 분류기의
# CONTENT 판정에 덮여 template XML에서 원문 대신 placeholder로 지워지던 문제.
# FIXED는 legacy 판정과 무관하게 원본 <hp:t> 본문을 그대로 유지해야 한다.
_FIXED_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:run><hp:t>안내문입니다</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>- 부제 -</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)


def test_fixed_resolution_preserves_original_text_node_verbatim(tmp_path: Path) -> None:
    source = _source_hwpx_with_section(tmp_path, "fixed.hwpx", _FIXED_SECTION)
    output = tmp_path / "candidate"

    with pytest.raises(SemanticAmbiguityError) as excinfo:
        separate_hwpx_template_content(
            source, output, template_id="fixed_resolved", institution="demo"
        )
    (unresolved_entry,) = excinfo.value.resolution_skeleton

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "resolutions": [
                    {
                        "decision_id": unresolved_entry["decision_id"],
                        "source_sha256": unresolved_entry["source_sha256"],
                        "text_sha256": unresolved_entry["text_sha256"],
                        "role": "fixed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output2 = tmp_path / "candidate2"
    result = separate_hwpx_template_content(
        source,
        output2,
        template_id="fixed_resolved",
        institution="demo",
        rules_path=rules_path,
    )

    mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
    assert all(field["sample_value"] != "- 부제 -" for field in mapping["fields"])
    template_xml = (output2 / "template" / "section0.template.xml").read_text(encoding="utf-8")
    assert "<hp:t>- 부제 -</hp:t>" in template_xml


# 회귀: 표 셀 안의 단일 text node에 대한 MARKER_CONTENT 확정이 placeholder_map.json
# 에는 marker_content로 정상 기록되면서도, template XML에는 projection되지 않고
# 원문 전체("- 부제1 -")가 그대로 남던 문제. prefix/suffix는 보존하고 content span
# 만 placeholder로 바뀌어야 한다.
_TABLE_MARKER_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:run><hp:t>안내문입니다</hp:t></hp:run></hp:p>"
    '<hp:p><hp:run><hp:tbl rowCnt="2" colCnt="1"><hp:tr>'
    '<hp:tc><hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
    "<hp:p><hp:run><hp:t>제목 입력</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
    "</hp:tr><hp:tr>"
    '<hp:tc><hp:cellAddr rowAddr="1" colAddr="0"/><hp:subList>'
    "<hp:p><hp:run><hp:t>- 부제1 -</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
    "</hp:tr></hp:tbl></hp:run></hp:p>"
    "</hs:sec>"
)


def test_marker_content_resolution_projects_placeholder_inside_table_cell(
    tmp_path: Path,
) -> None:
    source = _source_hwpx_with_section(tmp_path, "table_marker.hwpx", _TABLE_MARKER_SECTION)
    output = tmp_path / "candidate"

    with pytest.raises(SemanticAmbiguityError) as excinfo:
        separate_hwpx_template_content(
            source, output, template_id="table_marker_resolved", institution="demo"
        )
    (unresolved_entry,) = excinfo.value.resolution_skeleton
    span = unresolved_entry["decision"]["span"]

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "resolutions": [
                    {
                        "decision_id": unresolved_entry["decision_id"],
                        "source_sha256": unresolved_entry["source_sha256"],
                        "text_sha256": unresolved_entry["text_sha256"],
                        "role": "marker_content",
                        "marker_prefix_raw": span["marker_prefix_raw"],
                        "marker_suffix_raw": span["marker_suffix_raw"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output2 = tmp_path / "candidate2"
    result = separate_hwpx_template_content(
        source,
        output2,
        template_id="table_marker_resolved",
        institution="demo",
        rules_path=rules_path,
    )

    mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
    field = next(
        entry
        for entry in mapping["fields"]
        if entry["semantic_role"] == "marker_content"
    )
    assert field["replacement_mode"] == "hp_t_text_marker_span"
    template_xml = (output2 / "template" / "section0.template.xml").read_text(encoding="utf-8")
    assert f"- {field['placeholder']} -" in template_xml
    assert "<hp:t>- 부제1 -</hp:t>" not in template_xml


def test_ambiguous_candidate_stops_before_placeholder_artifacts_and_leaves_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "candidate"

    with pytest.raises(SemanticAmbiguityError) as excinfo:
        separate_hwpx_template_content(
            _source_hwpx(tmp_path),
            output,
            template_id="marker_ambiguous",
            institution="demo",
        )

    assert not (output / "placeholder_map.json").exists()
    assert not (output / "content.sample.json").exists()
    assert (output / "raw" / "section0.xml").exists()
    assert (output / "template" / "section0.template.xml").exists()
    assert (output / "semantic_classification.json").exists()
    assert (output / "template.review.md").exists()

    template = json.loads((output / "template.json").read_text(encoding="utf-8"))
    assert template["status"] == "candidate"
    assert template["content_separation"]["semantic_status"] == "ambiguous"
    assert template["content_separation"]["unresolved_count"] == 1

    unresolved = excinfo.value.unresolved
    assert len(unresolved) == 1
    assert unresolved[0]["text_node_index"] == 0
    skeleton = excinfo.value.resolution_skeleton
    assert len(skeleton) == 1
    assert skeleton[0]["role"] is None
    assert skeleton[0]["decision_id"] == unresolved[0]["decision_id"]


def test_marker_content_resolution_preserves_marker_and_fills_only_content(
    tmp_path: Path,
) -> None:
    source = _source_hwpx(tmp_path)
    output = tmp_path / "candidate"

    with pytest.raises(SemanticAmbiguityError) as excinfo:
        separate_hwpx_template_content(
            source, output, template_id="marker_resolved", institution="demo"
        )
    (unresolved_entry,) = excinfo.value.resolution_skeleton
    decision = unresolved_entry["decision"]
    span = decision["span"]

    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "resolutions": [
                    {
                        "decision_id": unresolved_entry["decision_id"],
                        "source_sha256": unresolved_entry["source_sha256"],
                        "text_sha256": unresolved_entry["text_sha256"],
                        "role": "marker_content",
                        "marker_prefix_raw": span["marker_prefix_raw"],
                        "marker_suffix_raw": span["marker_suffix_raw"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output2 = tmp_path / "candidate2"
    result = separate_hwpx_template_content(
        source,
        output2,
        template_id="marker_resolved",
        institution="demo",
        rules_path=rules_path,
    )

    mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
    (field,) = mapping["fields"]
    assert field["sample_value"] == "부제"
    assert field["replacement_mode"] == "hp_t_text_marker_span"
    assert field["semantic_role"] == "marker_content"
    template_xml = (output2 / "template" / "section0.template.xml").read_text(encoding="utf-8")
    assert f"- {field['placeholder']} -" in template_xml
