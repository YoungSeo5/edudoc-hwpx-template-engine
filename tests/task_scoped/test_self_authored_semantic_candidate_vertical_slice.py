from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path

from scripts.templates import author_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
REQUEST = ROOT / "tests/fixtures/template-contracts/weekly-report.template_request.json"
SEMANTIC = ROOT / "tests/fixtures/template-contracts/weekly-report.semantic_contract.json"
DESIGN = ROOT / "tests/fixtures/template-contracts/edudoc.institution_design.json"
SPEC = ROOT / "tests/fixtures/template-spec/weekly_report.template_spec.json"


def test_authoring_cli_persists_a_semantic_candidate_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    candidate_id = f"cand_vertical_slice_{uuid.uuid4().hex}"
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(REQUEST),
            "--semantic-contract", str(SEMANTIC),
            "--institution-design", str(DESIGN),
            "--template-spec", str(SPEC),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--candidate-id", candidate_id,
            "--template-id", f"tpl_{uuid.uuid4().hex}",
        ]
    )
    summary = json.loads(capsys.readouterr().out)
    candidate = ROOT / "sandbox/template-candidates" / candidate_id

    assert exit_code == 0, summary
    assert summary["ok"] is True
    assert summary["status"] == "candidate"
    for name in (
        "template_request.json",
        "semantic_contract.json",
        "institution_design.json",
        "template_spec.json",
        "source.hwpx",
        "placeholder_map.json",
        "qa.report.json",
        "separation_rules.json",
        "resolved_authoring_contract.json",
        "template.json",
        "template.review.md",
        "roundtrip.sample.hwpx",
        "roundtrip.test.hwpx",
    ):
        assert (candidate / name).is_file(), name

    contract = json.loads((candidate / "semantic_contract.json").read_text(encoding="utf-8"))
    placeholder_map = json.loads((candidate / "placeholder_map.json").read_text(encoding="utf-8"))
    content_elements = [entry for entry in contract["elements"] if entry["role"] == "CONTENT"]
    placeholder_fields = placeholder_map["fields"]
    placeholder_counts = Counter(entry["field_id"] for entry in placeholder_fields)
    content_field_ids = {entry["field_id"] for entry in content_elements}

    assert set(placeholder_counts) == content_field_ids
    for field_id in content_field_ids:
        assert placeholder_counts[field_id] == 1

    rules = json.loads((candidate / "separation_rules.json").read_text(encoding="utf-8"))["rules"]
    for field in placeholder_fields:
        matching_rules = [
            rule
            for rule in rules
            if rule["section"] == field["section"]
            and rule.get("table") == field.get("table")
            and rule.get("row") == field.get("row")
            and rule.get("col") == field.get("col")
            and (
                field.get("table") is not None
                or rule.get("text_node_index") == field["text_node_index"]
            )
        ]
        assert len(matching_rules) == 1, field["field_id"]
        rule = matching_rules[0]
        assert rule["role"] == "content"
        assert rule["field_id"] == field["field_id"]
    assert json.loads((candidate / "qa.report.json").read_text(encoding="utf-8"))["ok"] is True


def test_semantic_role_binding_rejects_a_content_placement_redeclared_as_fixed(
    tmp_path: Path,
    capsys,
) -> None:
    semantic = json.loads(SEMANTIC.read_text(encoding="utf-8"))
    current_week = next(entry for entry in semantic["elements"] if entry["element_id"] == "current_week")
    current_week.pop("field_id")
    current_week.pop("description")
    current_week.pop("required")
    current_week.pop("cardinality")
    current_week.pop("content_type")
    current_week["role"] = "FIXED_LABEL"
    current_week["text"] = "금주 업무"
    invalid_contract = tmp_path / "semantic.json"
    invalid_contract.write_text(json.dumps(semantic, ensure_ascii=False), encoding="utf-8")

    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(REQUEST),
            "--semantic-contract", str(invalid_contract),
            "--institution-design", str(DESIGN),
            "--template-spec", str(SPEC),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--candidate-id", f"cand_invalid_{uuid.uuid4().hex}",
        ]
    )
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert summary["stage"] == "authoring"
    assert "absent" in summary["error"]


def test_authoring_cli_rejects_mismatched_template_request_id(
    tmp_path: Path,
    capsys,
) -> None:
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    request["request_id"] = "different-request"
    invalid_request = tmp_path / "request.json"
    invalid_request.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(invalid_request),
            "--semantic-contract", str(SEMANTIC),
            "--institution-design", str(DESIGN),
            "--template-spec", str(SPEC),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--candidate-id", f"cand_request_mismatch_{uuid.uuid4().hex}",
        ]
    )
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert summary["stage"] == "authoring"
    assert "template_request_id" in summary["error"]
