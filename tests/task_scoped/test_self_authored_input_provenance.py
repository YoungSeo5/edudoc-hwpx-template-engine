from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.templates import author_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "templates" / "self-authored" / "edudoc" / "주간업무보고서"
DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"


def _production_args(*, institution_design: Path) -> argparse.Namespace:
    return argparse.Namespace(
        template_request=CANONICAL / "template_request.json",
        semantic_contract=CANONICAL / "semantic_contract.json",
        template_spec=CANONICAL / "template_spec.json",
        institution_design=institution_design,
        institution="edudoc",
        document_type="주간업무보고서",
    )


def test_production_generation_rejects_a_sandbox_24pt_design_snapshot(tmp_path: Path) -> None:
    experimental = tmp_path / "sandbox" / "template-candidates" / "spacing-24" / "institution_design.json"
    experimental.parent.mkdir(parents=True)
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    design["defaults"]["styles"]["one_page_body"]["spacing_after_pt"] = 24
    experimental.write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical self-authored input"):
        author_hwpx_template._validate_production_inputs(
            _production_args(institution_design=experimental),
            ROOT / "sandbox" / "template-candidates" / "candidate",
        )


def test_production_generation_rejects_a_test_fixture_input_at_any_output_path(tmp_path: Path) -> None:
    args = _production_args(institution_design=DESIGN)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"

    with pytest.raises(ValueError, match="canonical self-authored input"):
        author_hwpx_template._validate_production_inputs(
            args,
            tmp_path / "candidate",
        )


def test_noncanonical_inputs_require_explicit_test_only_opt_in(tmp_path: Path) -> None:
    args = _production_args(institution_design=DESIGN)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"
    args.allow_noncanonical_inputs_for_test = True

    author_hwpx_template._validate_production_inputs(args, tmp_path / "candidate")

    with pytest.raises(ValueError, match="cannot create a production candidate"):
        author_hwpx_template._validate_production_inputs(
            args,
            ROOT / "sandbox" / "template-candidates" / "candidate",
        )


def test_noncanonical_test_opt_in_rejects_nested_production_candidate_path() -> None:
    args = _production_args(institution_design=DESIGN)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"
    args.allow_noncanonical_inputs_for_test = True

    with pytest.raises(ValueError, match="cannot create a production candidate"):
        author_hwpx_template._validate_production_inputs(
            args,
            ROOT / "sandbox" / "template-candidates" / "candidate" / "nested",
        )


def test_self_authored_candidate_records_all_input_provenance(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(CANONICAL / "template_request.json"),
            "--semantic-contract", str(CANONICAL / "semantic_contract.json"),
            "--template-spec", str(CANONICAL / "template_spec.json"),
            "--institution-design", str(DESIGN),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--output-dir", str(candidate),
            "--template-id", "provenance-test",
        ]
    )

    assert exit_code in (0, 1)
    provenance = json.loads((candidate / "authoring_input.provenance.json").read_text(encoding="utf-8"))
    assert provenance["institution_design"]["path"] == str(DESIGN)
    assert provenance["template_spec"]["path"] == str(CANONICAL / "template_spec.json")
    assert provenance["semantic_contract"]["contract_id"] == "weekly-report-semantic-v2"
    assert provenance["reference_scope"] == {"mode": "institution_baseline_only"}
