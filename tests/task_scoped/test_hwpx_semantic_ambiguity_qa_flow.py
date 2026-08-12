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
