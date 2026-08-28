from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.templates.hwpx_content_separator import separate_hwpx_template_content
from core.templates.hwpx_semantic_classifier import SemanticAmbiguityError
from core.templates.hwpx_separation_rules import TextLocation, TextRole, load_separation_rules


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


# CONTENT/MARKER_CONTENT ↔ placeholder_map/separation rule 1:1 대응: 이 문서에는
# 서로 다른 텍스트를 가진 결정적 CONTENT 노드 두 개("안내문입니다",
# "두번째 안내문입니다")와, --rules로 fixed로 확정하는 ambiguous 노드
# ("- 부제 -") 하나가 있다. CONTENT 노드가 둘 이상이어야 "개수는 맞지만
# 서로 다른 노드가 뒤바뀌어 projection된" 경우를 실제로 구분해낼 수 있다.
_MULTI_CONTENT_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
    "<hp:p><hp:run><hp:t>안내문입니다</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>두번째 안내문입니다</hp:t></hp:run></hp:p>"
    "<hp:p><hp:run><hp:t>- 부제 -</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)


def test_placeholder_map_fields_match_content_semantic_decisions_one_to_one(
    tmp_path: Path,
) -> None:
    source = _source_hwpx_with_section(tmp_path, "fixed_ratio.hwpx", _MULTI_CONTENT_SECTION)
    output = tmp_path / "candidate"

    with pytest.raises(SemanticAmbiguityError) as excinfo:
        separate_hwpx_template_content(
            source, output, template_id="fixed_ratio", institution="demo"
        )
    (unresolved_entry,) = excinfo.value.resolution_skeleton

    # "rules"(role=content, 명시적 field_id, location selector)와 "resolutions"
    # (ambiguous 노드 확정)를 같은 --rules 파일에 함께 선언한다. 두 CONTENT
    # 노드에 서로 다른 field_id를 명시적으로 지정해야, projection된 field_id가
    # "그 노드 자신의" separation rule에서 왔는지(자신의 location으로 다시
    # 찾아낸 rule과 일치하는지) 검증할 수 있다 — 단순히 field_id가 두 개
    # 존재한다는 것만으로는 서로 뒤바뀐 경우를 잡아내지 못한다.
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "role": "content",
                        "section": "section0.xml",
                        "text_node_index": 0,
                        "field_id": "notice_one",
                    },
                    {
                        "role": "content",
                        "section": "section0.xml",
                        "text_node_index": 1,
                        "field_id": "notice_two",
                    },
                ],
                "resolutions": [
                    {
                        "decision_id": unresolved_entry["decision_id"],
                        "source_sha256": unresolved_entry["source_sha256"],
                        "text_sha256": unresolved_entry["text_sha256"],
                        "role": "fixed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    output2 = tmp_path / "candidate2"
    result = separate_hwpx_template_content(
        source,
        output2,
        template_id="fixed_ratio",
        institution="demo",
        rules_path=rules_path,
    )
    separation_rules = load_separation_rules(rules_path)

    classification = json.loads(
        (output2 / "semantic_classification.json").read_text(encoding="utf-8")
    )
    decisions_by_id = {item["decision_id"]: item for item in classification["node_decisions"]}
    content_like_ids = {
        item["decision_id"]
        for item in classification["node_decisions"]
        if item["role"] in ("content", "marker_content")
    }
    fixed_ids = {
        item["decision_id"]
        for item in classification["node_decisions"]
        if item["role"] == "fixed"
    }
    # 이 문서 구성 자체가 기대와 맞는지 먼저 고정한다: CONTENT류 2개, FIXED 1개.
    assert len(content_like_ids) == 2
    assert len(fixed_ids) == 1

    mapping = json.loads(result.placeholder_map.read_text(encoding="utf-8"))
    field_decision_ids = [field["semantic_decision_id"] for field in mapping["fields"]]

    # 1:1 bijection: placeholder_map의 semantic_decision_id 집합은 CONTENT/
    # MARKER_CONTENT decision_id 집합과 정확히 같아야 한다 (누락도, 중복
    # projection도, FIXED의 혼입도 없어야 한다).
    assert sorted(field_decision_ids) == sorted(content_like_ids)
    assert len(field_decision_ids) == len(set(field_decision_ids))
    assert not (set(field_decision_ids) & fixed_ids)

    # 각 필드가 "그 개수만큼 아무 CONTENT 노드에나" 대응하는 게 아니라, 자신의
    # semantic decision과 location·원문까지 정확히 일치해야 한다. field_id가
    # 맞는 개수로 채워졌더라도 location/sample_value가 다른 CONTENT 노드의
    # 것과 뒤바뀌어 있다면(잘못된 노드가 projection됐다면) 아래에서 실패한다.
    for field in mapping["fields"]:
        decision = decisions_by_id[field["semantic_decision_id"]]
        assert decision["role"] in ("content", "marker_content")
        location = decision["location"]
        assert field["text_node_index"] == location["text_node_index"]
        assert field["section"] == location["section"]
        assert field.get("table") == location["table"]
        assert field.get("row") == location["row"]
        assert field.get("col") == location["col"]
        assert (
            hashlib.sha256(field["sample_value"].encode("utf-8")).hexdigest()
            == decision["text_sha256"]
        )

    # 두 CONTENT 필드가 서로 다른 노드를 가리켜야 한다(뒤섞여 같은 노드를
    # 중복 참조하지 않는다).
    assert len({field["text_node_index"] for field in mapping["fields"]}) == 2

    # semantic decision ↔ placeholder ↔ separation rule 3자 대응. 각 필드의
    # field_id가 "어떤 rule에서든" 온 게 아니라, 정확히 "그 필드 자신의
    # location"에 걸리는 role=content separation rule에서 왔는지를, rules.json을
    # 다시 로드한 SeparationRules로 그 location을 직접 질의해 확인한다. 두
    # content rule의 field_id를 서로 다르게 선언했으므로(notice_one/notice_two),
    # 구현이 두 CONTENT 노드의 rule을 뒤바꿔 투영하면(동일한 rule 개수라도)
    # 아래 field_id 비교가 실패한다.
    for field in mapping["fields"]:
        decision = decisions_by_id[field["semantic_decision_id"]]
        location = TextLocation(
            section=decision["location"]["section"],
            text_node_index=decision["location"]["text_node_index"],
            table=decision["location"]["table"],
            row=decision["location"]["row"],
            col=decision["location"]["col"],
        )
        matching_rules = [rule for rule in separation_rules.rules if rule.matches(location)]
        assert len(matching_rules) == 1
        (matching_rule,) = matching_rules
        assert matching_rule.role is TextRole.CONTENT
        assert matching_rule.field_id == field["field_id"]
        assert separation_rules.field_id_for(location) == field["field_id"]

    # 두 separation rule 각각 정확히 자신이 선언한 location에만 걸려야 한다
    # (다른 CONTENT 노드의 location과 겹치지 않는다 = rule 자체의 permutation도 없다).
    notice_one_location = TextLocation(section="section0.xml", text_node_index=0, table=None, row=None, col=None)
    notice_two_location = TextLocation(section="section0.xml", text_node_index=1, table=None, row=None, col=None)
    assert separation_rules.field_id_for(notice_one_location) == "notice_one"
    assert separation_rules.field_id_for(notice_two_location) == "notice_two"

    # FIXED로 확정된 노드(- 부제 -)는 placeholder(이미 위에서 확인)뿐 아니라
    # role=content separation rule에도 걸리지 않는다.
    (fixed_decision_id,) = fixed_ids
    fixed_location_raw = decisions_by_id[fixed_decision_id]["location"]
    fixed_location = TextLocation(
        section=fixed_location_raw["section"],
        text_node_index=fixed_location_raw["text_node_index"],
        table=fixed_location_raw["table"],
        row=fixed_location_raw["row"],
        col=fixed_location_raw["col"],
    )
    assert separation_rules.role_for(fixed_location) is not TextRole.CONTENT
    assert separation_rules.field_id_for(fixed_location) is None


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
