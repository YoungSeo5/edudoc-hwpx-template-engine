#!/usr/bin/env python3
"""Author a self-generated HWPX source from a ``template_spec`` and run it
through the existing candidate QA pipeline.

이 스크립트는 세 단계를 조합한다.

1. template_spec 로드 (core.adapters.hwpx_template_authoring.load_template_spec).
2. template_spec + Institution Design Contract ->
   core.adapters.hwpx_authoring_resolve.resolve()로 Resolved Authoring
   Contract 생성 — style role 조회·override 병합·완결성 검증이 전부 여기서
   끝난다. 이 스크립트는 그 판단에 관여하지 않는다.
3. Resolved Authoring Contract -> core.adapters.hwpx_template_authoring으로
   source.hwpx + --rules 파일 생성, 그 source.hwpx를 기존
   qa_hwpx_template.py에 --source로 그대로 넘겨 subprocess 호출(기존 CLI
   재사용, 리팩터링하지 않음).

resolve()를 우회해 template_spec을 바로 generate_source_hwpx()에 넣는 경로는
없다 — institution-design-contract-v1 task 이전에는 template_spec이 인라인
style 값을 직접 들고 있어 그런 경로가 가능했지만, 지금 template_spec의 style
필드는 institution role 이름일 뿐이라 resolve() 없이는 애초에 완결된 값이
아니다.

candidate 승인·등록(register_hwpx_template.py)과 최종 렌더
(render_hwpx_template.py) 연결은 이 스크립트의 범위가 아니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_authoring_resolve import (  # noqa: E402
    HwpxAuthoringResolveError,
    resolve,
)
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    HwpxTemplateAuthoringError,
    TemplateSpec,
    build_separation_rules,
    generate_source_hwpx,
    load_template_spec,
    run_skill_subprocess,
    validate_semantic_placements,
    write_separation_rules,
)
from core.adapters.hwpx_semantic_contract import (  # noqa: E402
    SemanticContractError,
    bind_semantic_contract,
    load_semantic_contract,
    write_resolved_authoring_contract,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "template_spec에서 자체 HWPX source를 생성하고, 기존 "
            "qa_hwpx_template.py로 candidate를 만든다."
        )
    )
    parser.add_argument("--template-request", required=True, type=Path, help="TemplateRequest JSON")
    parser.add_argument("--semantic-contract", required=True, type=Path, help="Semantic Template Contract JSON")
    parser.add_argument("--template-spec", required=True, type=Path, help="template_spec JSON")
    parser.add_argument(
        "--institution-design",
        required=True,
        type=Path,
        help="Institution Design Contract JSON (docs/contracts/institution-design-contract.schema.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="테스트용 candidate 출력 폴더; 생략하면 sandbox/template-candidates 아래에 생성",
    )
    parser.add_argument("--candidate-id", help="candidate 식별자(생략하면 cand_<uuid>)")
    parser.add_argument("--institution", required=True, help="기관명")
    parser.add_argument("--document-type", required=True, help="문서 유형")
    parser.add_argument("--template-id", help="템플릿 식별자(생략하면 자동 생성)")
    args = parser.parse_args(argv)

    candidate_id = args.candidate_id or f"cand_{uuid.uuid4().hex}"
    candidate_dir = args.output_dir or (ROOT / "sandbox" / "template-candidates" / candidate_id)
    authoring_dir = candidate_dir.parent / f"{candidate_dir.name}.authoring"
    try:
        template_request = _load_contract(args.template_request, "TemplateRequest")
        semantic_raw = _load_contract(args.semantic_contract, "Semantic Contract")
        institution_design = _load_contract(args.institution_design, "Institution Design Contract")
        spec = load_template_spec(args.template_spec)
        semantic = load_semantic_contract(args.semantic_contract)
        _validate_contract_identities(
            template_request,
            semantic_raw,
            institution_design,
            spec,
            args.institution,
            args.document_type,
        )
        binding = bind_semantic_contract(semantic, spec)
        placements = validate_semantic_placements(semantic_raw, spec)
        resolved = replace(
            resolve(args.institution_design, spec, binding),
            semantic_placements=placements,
        )
        authoring_dir.mkdir(parents=True, exist_ok=False)
        source_hwpx = generate_source_hwpx(
            resolved,
            authoring_dir / "source.hwpx",
        )
        rules = build_separation_rules(resolved, source_hwpx)
        rules_path = write_separation_rules(rules, authoring_dir / "rules.json")
        _stage_contract_artifacts(args, semantic.contract_id, resolved, rules_path, authoring_dir)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        HwpxTemplateAuthoringError,
        HwpxAuthoringResolveError,
        SemanticContractError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "authoring",
                    "template_spec": str(args.template_spec),
                    "output_dir": str(candidate_dir),
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    qa_script = ROOT / "scripts" / "templates" / "qa_hwpx_template.py"
    cmd = [
        sys.executable,
        str(qa_script),
        "--source",
        str(source_hwpx),
        "--output-dir",
        str(candidate_dir),
        "--institution",
        args.institution,
        "--document-type",
        args.document_type,
        "--rules",
        str(rules_path),
        "--contract-artifact-dir",
        str(authoring_dir / "contracts"),
    ]
    if args.template_id:
        cmd.extend(["--template-id", args.template_id])
    required_native_pages = _required_native_pages(spec)
    if required_native_pages is not None:
        cmd.extend(["--required-native-pages", str(required_native_pages)])

    try:
        completed = run_skill_subprocess(cmd)
    except HwpxTemplateAuthoringError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "qa",
                    "template_spec": str(args.template_spec),
                    "output_dir": str(candidate_dir),
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    sys.stdout.write(completed.stdout)
    if completed.stderr.strip():
        sys.stderr.write(completed.stderr)
    return completed.returncode


def _stage_contract_artifacts(
    args: argparse.Namespace,
    semantic_contract_id: str,
    resolved: object,
    rules_path: Path,
    authoring_dir: Path,
) -> None:
    contracts = authoring_dir / "contracts"
    contracts.mkdir()
    shutil.copy2(args.template_request, contracts / "template_request.json")
    shutil.copy2(args.semantic_contract, contracts / "semantic_contract.json")
    template_spec_payload = _load_contract(args.template_spec, "template_spec")
    recipe_value = template_spec_payload.get("family_recipe")
    if isinstance(recipe_value, str) and recipe_value:
        recipe_path = Path(recipe_value)
        if not recipe_path.is_absolute():
            recipe_path = args.template_spec.parent / recipe_path
        shutil.copy2(recipe_path, contracts / "family_recipe.json")
        template_spec_payload["family_recipe"] = "family_recipe.json"
    (contracts / "template_spec.json").write_text(
        json.dumps(template_spec_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(args.institution_design, contracts / "institution_design.json")
    shutil.copy2(rules_path, contracts / "separation_rules.json")
    design_digest = hashlib.sha256(args.institution_design.read_bytes()).hexdigest()
    (contracts / "institution_design.provenance.json").write_text(
        json.dumps(
            {
                "path": str(args.institution_design),
                "sha256": design_digest,
                "design_id": resolved.institution_design_id,
                "semantic_contract_id": semantic_contract_id,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_resolved_authoring_contract(resolved, contracts / "resolved_authoring_contract.json")


def _required_native_pages(spec: TemplateSpec) -> int | None:
    if not spec.family_recipe_path:
        return None
    recipe = _load_contract(Path(spec.family_recipe_path), "family recipe")
    value = recipe.get("native_page_count")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("family recipe native_page_count must be a positive integer")
    return value


def _load_contract(path: Path, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {name}: {path} ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{name} root must be an object")
    return raw


def _required_contract_value(contract: dict[str, object], name: str, key: str) -> str:
    value = contract.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return value


def _validate_contract_identities(
    template_request: dict[str, object],
    semantic_contract: dict[str, object],
    institution_design: dict[str, object],
    spec: TemplateSpec,
    institution: str,
    document_type: str,
) -> None:
    _validate_template_request_shape(template_request)
    request_id = _required_contract_value(template_request, "TemplateRequest", "request_id")
    if _required_contract_value(semantic_contract, "Semantic Contract", "template_request_id") != request_id:
        raise ValueError("TemplateRequest.request_id must match Semantic Contract.template_request_id")
    for name, contract in (
        ("TemplateRequest", template_request),
        ("Semantic Contract", semantic_contract),
        ("Institution Design Contract", institution_design),
    ):
        if _required_contract_value(contract, name, "institution") != institution:
            raise ValueError(f"{name}.institution must match --institution")
    for name, contract in (("TemplateRequest", template_request), ("Semantic Contract", semantic_contract)):
        if _required_contract_value(contract, name, "document_type") != document_type:
            raise ValueError(f"{name}.document_type must match --document-type")
    if spec.semantic_contract_id != _required_contract_value(semantic_contract, "Semantic Contract", "contract_id"):
        raise ValueError("TemplateSpec.semantic_contract_id must match Semantic Contract.contract_id")
    if spec.institution_design_id != _required_contract_value(institution_design, "Institution Design Contract", "design_id"):
        raise ValueError("TemplateSpec.institution_design_id must match Institution Design Contract.design_id")
    if spec.institution_design_version != _required_contract_value(institution_design, "Institution Design Contract", "institution_design_version"):
        raise ValueError("TemplateSpec.institution_design_version must match Institution Design Contract.institution_design_version")


def _validate_template_request_shape(template_request: dict[str, object]) -> None:
    for key in ("purpose", "requested_items", "reference_scope", "constraints"):
        if key not in template_request:
            raise ValueError(f"TemplateRequest is missing required field: {key}")
    if not isinstance(template_request["purpose"], str) or not template_request["purpose"].strip():
        raise ValueError("TemplateRequest.purpose must be a non-empty string")
    if not isinstance(template_request["requested_items"], list) or not template_request["requested_items"]:
        raise ValueError("TemplateRequest.requested_items must be a non-empty list")
    if not isinstance(template_request["reference_scope"], dict):
        raise ValueError("TemplateRequest.reference_scope must be an object")
    if not isinstance(template_request["constraints"], list):
        raise ValueError("TemplateRequest.constraints must be a list")


if __name__ == "__main__":
    raise SystemExit(main())
