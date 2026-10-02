from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

from scripts.templates import author_hwpx_template


ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONTRACTS = ROOT / "templates" / "self-authored" / "edudoc" / "주간업무보고서"
SOURCE_DESIGN = ROOT / "templates" / "institutions" / "edudoc" / "_design" / "design.json"


def _canonical_inputs(registry_root: Path) -> tuple[Path, Path]:
    canonical = registry_root / "self-authored" / "edudoc" / "주간업무보고서"
    shutil.copytree(SOURCE_CONTRACTS, canonical)
    spec_path = canonical / "template_spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["family_recipe"] = "../../../provision/edudoc/_families/one_page_report/recipe.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return canonical, registry_root / "provision" / "edudoc" / "_design" / "design.json"


def _production_args(canonical: Path, *, institution_design: Path) -> argparse.Namespace:
    return argparse.Namespace(
        template_request=canonical / "template_request.json",
        semantic_contract=canonical / "semantic_contract.json",
        template_spec=canonical / "template_spec.json",
        institution_design=institution_design,
        institution="edudoc",
        document_type="주간업무보고서",
    )


def test_production_generation_rejects_a_sandbox_24pt_design_snapshot(tmp_path: Path, sandbox_author_registry: Path) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    experimental = tmp_path / "sandbox" / "template-candidates" / "spacing-24" / "institution_design.json"
    experimental.parent.mkdir(parents=True)
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design["defaults"]["styles"]["one_page_body"]["spacing_after_pt"] = 24
    experimental.write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical self-authored input"):
        author_hwpx_template._validate_production_inputs(
            _production_args(canonical, institution_design=experimental),
            sandbox_author_registry / "candidates" / "candidate",
            sandbox_author_registry,
        )


def test_production_generation_rejects_a_test_fixture_input_at_any_output_path(tmp_path: Path, sandbox_author_registry: Path) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    args = _production_args(canonical, institution_design=design_path)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"

    with pytest.raises(ValueError, match="canonical self-authored input"):
        author_hwpx_template._validate_production_inputs(
            args,
            tmp_path / "candidate",
            sandbox_author_registry,
        )


def test_noncanonical_inputs_require_explicit_test_only_opt_in(tmp_path: Path, sandbox_author_registry: Path) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    args = _production_args(canonical, institution_design=design_path)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"
    args.allow_noncanonical_inputs_for_test = True

    author_hwpx_template._validate_production_inputs(args, tmp_path / "candidate", sandbox_author_registry)

    with pytest.raises(ValueError, match="requires a sandbox registry"):
        author_hwpx_template._validate_production_inputs(
            args,
            ROOT / "candidate",
            ROOT,
        )


def test_noncanonical_test_opt_in_rejects_nested_production_candidate_path(sandbox_author_registry: Path) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    args = _production_args(canonical, institution_design=design_path)
    args.template_spec = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report_one_page.template_spec.json"
    args.allow_noncanonical_inputs_for_test = True

    args.output_dir = sandbox_author_registry / "candidates" / "candidate" / "nested"
    args.candidate_id = "nested"
    assert author_hwpx_template._run(
        args,
        sandbox_author_registry,
        sandbox_author_registry / "_tmp" / "unused",
    ) == 1


def test_self_authored_candidate_records_all_input_provenance(tmp_path: Path, sandbox_author_registry: Path) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    candidate = sandbox_author_registry / "candidates" / "candidate"
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(canonical / "template_request.json"),
            "--semantic-contract", str(canonical / "semantic_contract.json"),
            "--template-spec", str(canonical / "template_spec.json"),
            "--institution-design", str(design_path),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--output-dir", str(candidate),
            "--template-id", "provenance-test",
        ]
    )

    assert exit_code in (0, 1)
    provenance = json.loads((candidate / "authoring_input.provenance.json").read_text(encoding="utf-8"))
    assert provenance["institution_design"]["path"] == str(design_path)
    assert provenance["template_spec"]["path"] == str(canonical / "template_spec.json")
    assert provenance["semantic_contract"]["contract_id"] == "weekly-report-semantic-v2"
    assert provenance["reference_scope"] == {"mode": "institution_baseline_only"}


def test_authoring_uses_registry_design_even_when_package_design_differs(
    sandbox_author_registry: Path,
) -> None:
    canonical, design_path = _canonical_inputs(sandbox_author_registry)
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design["defaults"]["styles"]["one_page_body"]["color"] = "#112233"
    design_path.write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")
    candidate = sandbox_author_registry / "candidates" / "registry-design"

    author_hwpx_template.main([
        "--template-request", str(canonical / "template_request.json"),
        "--semantic-contract", str(canonical / "semantic_contract.json"),
        "--template-spec", str(canonical / "template_spec.json"),
        "--institution-design", str(design_path),
        "--institution", "edudoc", "--document-type", "주간업무보고서",
        "--output-dir", str(candidate), "--template-id", "registry-design",
    ])

    assert "#112233" in (candidate / "resolved_authoring_contract.json").read_text(encoding="utf-8")
    assert "#112233" not in SOURCE_DESIGN.read_text(encoding="utf-8")
