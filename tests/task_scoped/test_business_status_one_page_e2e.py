from __future__ import annotations

import json
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import hwpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_template_renderer import render_candidate_roundtrip  # noqa: E402
from scripts.templates import author_hwpx_template  # noqa: E402

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_NS = {"hp": _HP}
_FIXTURES = ROOT / "tests" / "fixtures" / "business-status-one-page"
_REQUEST = _FIXTURES / "template_request.json"
_SEMANTIC = _FIXTURES / "semantic_contract.json"
_SPEC = _FIXTURES / "template_spec.json"
_DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / f"fixture-{name}.json").read_text(encoding="utf-8"))


def _section_root(output: Path) -> ET.Element:
    with zipfile.ZipFile(output) as package:
        return ET.fromstring(package.read("Contents/section0.xml"))


def _section_xml(output: Path) -> bytes:
    with zipfile.ZipFile(output) as package:
        return package.read("Contents/section0.xml")


def _paragraph_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{_HP}}}t"))


def _project_task_rows(root: ET.Element) -> list[ET.Element]:
    for table in root.findall(".//hp:tbl", _NS):
        rows = table.findall("./hp:tr", _NS)
        if rows and _paragraph_text(rows[0]) == "과제명추진단계진행률일정":
            return rows
    raise AssertionError("project_tasks table was not found")


def test_business_status_candidate_renders_sparse_normal_dense_without_state_leakage(
    tmp_path: Path,
) -> None:
    candidate_id = f"business_status_one_page_{uuid.uuid4().hex}"
    candidate = tmp_path / "template-candidates" / candidate_id

    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(_REQUEST),
            "--semantic-contract", str(_SEMANTIC),
            "--institution-design", str(_DESIGN),
            "--template-spec", str(_SPEC),
            "--institution", "edudoc",
            "--document-type", "사업 추진현황 1페이지 보고서",
            "--output-dir", str(candidate),
            "--allow-noncanonical-inputs-for-test",
            "--candidate-id", candidate_id,
            "--template-id", "edudoc-business-status-one-page-v1",
        ]
    )

    qa_report = json.loads((candidate / "qa.report.json").read_text(encoding="utf-8"))
    match exit_code:
        case 0:
            assert qa_report["ok"] is True
            assert qa_report["strict_validation"] == {
                "roundtrip.sample.hwpx": True,
                "roundtrip.test.hwpx": True,
            }
            assert {
                (item["passed"], item["expected_pages"], item["observed_pages"])
                for item in qa_report["native_page_validation"].values()
            } == {(True, 1, 1)}
        case 1:
            assert qa_report["error_code"] == "native_page_validation_failed"
            assert {
                item["reason"]
                for item in qa_report["native_page_validation"].values()
            } == {"native_page_validation_unavailable"}
        case unexpected:
            raise AssertionError(f"unexpected authoring exit code: {unexpected}")
    assert hwpx.validate_package(candidate / "roundtrip.sample.hwpx").ok is True
    assert hwpx.validate_package(candidate / "roundtrip.test.hwpx").ok is True
    semantic = json.loads(_SEMANTIC.read_text(encoding="utf-8"))
    placeholder_map = json.loads((candidate / "placeholder_map.json").read_text(encoding="utf-8"))
    content_fields = {
        element["field_id"]
        for element in semantic["elements"]
        if element["role"] == "CONTENT"
    }
    assert {
        field["field_id"].split("[", 1)[0]
        for field in placeholder_map["fields"]
    } == content_fields
    next_actions = next(
        collection
        for collection in placeholder_map["collections"]
        if collection["canonical_path"] == "next_actions"
    )
    action_prefixes = {
        prototype["prototype_level"]: prototype["fixed_prefix"]
        for prototype in next_actions["prototype_paragraphs"]
    }
    action_layout_prefixes = {1: " ", 2: "      "}
    action_style_ids = {
        field["prototype_level"]: field["layout_context"]["para_pr_id_ref"]
        for field in placeholder_map["fields"]
        if field["field_id"].startswith("next_actions[")
    }

    fixture_outputs: dict[str, Path] = {}
    fixture_xml: dict[str, bytes] = {}
    for name in ("sparse", "normal", "dense"):
        payload = _load_fixture(name)
        output = tmp_path / f"{name}.hwpx"
        result = render_candidate_roundtrip(candidate, payload["fields"], output)
        root = _section_root(output)
        tasks = payload["fields"]["project_tasks"]
        actions = payload["fields"]["next_actions"]

        assert result.leftover_placeholders == []
        assert result.missing_fields == []
        assert hwpx.validate_package(output).ok is True
        assert len(_project_task_rows(root)) == len(tasks) + 1
        assert [_paragraph_text(row) for row in _project_task_rows(root)[1:]] == [
            f"{item['task_name']}{item['stage']}{item['progress']}{item['schedule']}"
            for item in tasks
        ]
        action_paragraphs = [
            (_paragraph_text(paragraph), paragraph.get("paraPrIDRef"))
            for paragraph in root.findall("./hp:p", _NS)
            if paragraph.get("paraPrIDRef") in set(action_style_ids.values())
        ]
        assert action_paragraphs == [
            (
                f"{action_layout_prefixes[item['level']]}{action_prefixes[item['level']]}{item['text']}",
                action_style_ids[item["level"]],
            )
            for item in actions
        ]
        assert "{{" not in "".join(root.itertext())
        fixture_outputs[name] = output
        fixture_xml[name] = _section_xml(output)

    assert fixture_xml["sparse"] != fixture_xml["normal"]
    assert fixture_xml["sparse"] != fixture_xml["dense"]
    assert fixture_xml["normal"] != fixture_xml["dense"]
    assert "고위험 데이터 전환" not in _section_xml(fixture_outputs["sparse"]).decode("utf-8")

    for name in ("dense", "sparse", "normal"):
        payload = _load_fixture(name)
        rerendered = tmp_path / f"rerendered-{name}.hwpx"
        render_candidate_roundtrip(candidate, payload["fields"], rerendered)
        assert _section_xml(rerendered) == fixture_xml[name]
