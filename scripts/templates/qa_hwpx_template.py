#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_template_renderer import (  # noqa: E402
    HwpxTemplateRenderError,
    load_template_content,
    render_candidate_roundtrip,
)
from core.templates.hwpx_content_separator import (  # noqa: E402
    separate_hwpx_template_content,
)
from core.templates.hwpx_semantic_classifier import SemanticAmbiguityError  # noqa: E402
from core.templates.registry import TemplateRegistry  # noqa: E402
from core.templates.hwpx_template_registration import candidate_artifact_digest  # noqa: E402
from core.adapters.hwpx_semantic_contract import (  # noqa: E402
    SemanticContractError,
    persist_candidate_contract_artifacts,
)
from core.adapters.hancom_page_count import validate_native_page_count  # noqa: E402


class SnapshotMismatchError(ValueError):
    """Raised when the candidate's source.hwpx snapshot no longer matches --source."""


class NativePageValidationError(ValueError):
    """Raised when a required native Hancom page-count check does not pass."""

    def __init__(self, message: str, validation: dict | None = None) -> None:
        super().__init__(message)
        self.validation = validation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "원본 HWPX를 미승인 템플릿 후보로 분리하고 sample/test 왕복 출력을 검증합니다."
        )
    )
    parser.add_argument("--source", required=True, type=Path, help="사용자가 제공한 원본 HWPX")
    parser.add_argument("--output-dir", type=Path, help="테스트용 후보 출력 폴더")
    parser.add_argument("--candidate-id", help="생략하면 cand_<uuid> canonical candidate ID")
    parser.add_argument("--institution", required=True, help="기관명")
    parser.add_argument("--document-type", required=True, help="문서 유형")
    parser.add_argument(
        "--template-id",
        help="템플릿 식별자(생략하면 기관·문서유형·원본 내용으로 자동 생성)",
    )
    parser.add_argument("--rules", type=Path, help="추가 콘텐츠 분리 규칙")
    parser.add_argument("--contract-artifact-dir", type=Path, help="self-authored contract artifact staging directory")
    parser.add_argument("--required-native-pages", type=int)
    args = parser.parse_args(argv)
    if args.output_dir is None:
        candidate_id = args.candidate_id or f"cand_{uuid.uuid4().hex}"
        args.output_dir = ROOT / "sandbox" / "template-candidates" / candidate_id

    template_id = args.template_id
    template_id_source = "provided" if template_id is not None else "generated"
    try:
        if template_id is None:
            template_id = _generated_template_id(
                args.source,
                args.institution,
                args.document_type,
            )
        separation = separate_hwpx_template_content(
            args.source,
            args.output_dir,
            template_id=template_id,
            template_name=args.document_type,
            institution=args.institution,
            rules_path=args.rules,
        )
        candidate_data = json.loads(
            separation.extraction.template_json.read_text(encoding="utf-8")
        )
        if candidate_data.get("status") != "candidate":
            raise HwpxTemplateRenderError(
                "QA generation must leave template.json status as candidate"
            )
        contract_artifacts = (
            persist_candidate_contract_artifacts(args.contract_artifact_dir, args.output_dir)
            if args.contract_artifact_dir is not None
            else {}
        )

        # 이미 등록된 템플릿이 있으면, alias_map이 묶어 둔 field_id가 후보에서
        # 같은 내용을 가리키는지 먼저 확인한다. field_id는 순번이라 앞쪽 분류가
        # 하나만 달라져도 뒤 번호가 조용히 다른 텍스트로 밀린다.
        field_identity = TemplateRegistry(
            ROOT / "templates" / "institutions"
        ).verify_candidate_field_identity(
            args.institution,
            args.document_type,
            args.output_dir,
        )

        sample_content = load_template_content(separation.content_sample)
        sample_output = args.output_dir / "roundtrip.sample.hwpx"
        sample_render = render_candidate_roundtrip(
            args.output_dir,
            sample_content.fields,
            sample_output,
        )

        test_fields = {
            field_id: f"QA_{index:03d}_{field_id}"
            for index, field_id in enumerate(sample_content.fields, start=1)
        }
        test_content_path = args.output_dir / "content.test.json"
        test_content_path.write_text(
            json.dumps(
                {
                    "template_id": sample_content.template_id,
                    "source_file": args.source.name,
                    "fields": test_fields,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        test_output = args.output_dir / "roundtrip.test.hwpx"
        test_render = render_candidate_roundtrip(
            args.output_dir,
            test_fields,
            test_output,
        )
        native_page_validation = None
        if args.required_native_pages is not None:
            if args.required_native_pages <= 0:
                raise NativePageValidationError("--required-native-pages must be positive")
            sample_native = validate_native_page_count(sample_output, args.required_native_pages)
            test_native = validate_native_page_count(test_output, args.required_native_pages)
            native_page_validation = {
                "roundtrip.sample.hwpx": asdict(sample_native),
                "roundtrip.test.hwpx": asdict(test_native),
            }
            if not sample_native.passed or not test_native.passed:
                raise NativePageValidationError(
                    "required native page validation did not pass: "
                    f"sample={sample_native.reason or sample_native.observed_pages}, "
                    f"test={test_native.reason or test_native.observed_pages}",
                    native_page_validation,
                )

        source_snapshot = args.output_dir / "source.hwpx"
        source_snapshot_matches = _sha256(args.source) == _sha256(source_snapshot)
        if not source_snapshot_matches:
            raise SnapshotMismatchError(
                "candidate source.hwpx snapshot no longer matches --source; "
                "re-run separation against the current source"
            )
        report_path = args.output_dir / "qa.report.json"
        summary = {
            "ok": True,
            "source": str(args.source),
            "output_dir": str(args.output_dir),
            "institution": args.institution,
            "document_type": args.document_type,
            "template_id": template_id,
            "template_id_source": template_id_source,
            "status": candidate_data["status"],
            "source_snapshot_matches": source_snapshot_matches,
            "candidate_digest": candidate_artifact_digest(args.output_dir),
            "bound_field_identity": field_identity,
            "sample_render": sample_render.to_meta(),
            "test_render": test_render.to_meta(),
            "strict_validation": {
                "roundtrip.sample.hwpx": True,
                "roundtrip.test.hwpx": True,
            },
            "native_page_validation": native_page_validation,
            "artifacts": {
                "template": str(separation.extraction.template_json),
                "review": str(separation.review),
                "placeholder_map": str(separation.placeholder_map),
                "content_sample": str(separation.content_sample),
                "content_test": str(test_content_path),
                "sample_output": str(sample_output),
                "test_output": str(test_output),
                "qa_report": str(report_path),
                **contract_artifacts,
            },
            "error": None,
        }
        report_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except SemanticAmbiguityError as exc:
        failure = _base_failure_summary(args, template_id, template_id_source)
        failure["error_code"] = "semantic_ambiguity"
        failure["error"] = str(exc)
        failure["unresolved_count"] = len(getattr(exc, "unresolved", []) or [])
        failure["unresolved"] = getattr(exc, "unresolved", [])
        failure["resolution_skeleton"] = getattr(exc, "resolution_skeleton", [])
        _persist_and_print_failure(args.output_dir, failure)
        return 1
    except SnapshotMismatchError as exc:
        failure = _base_failure_summary(args, template_id, template_id_source)
        failure["error_code"] = "snapshot_mismatch"
        failure["error"] = str(exc)
        _persist_and_print_failure(args.output_dir, failure)
        return 1
    except NativePageValidationError as exc:
        failure = _base_failure_summary(args, template_id, template_id_source)
        failure["error_code"] = "native_page_validation_failed"
        failure["error"] = str(exc)
        failure["native_page_validation"] = exc.validation
        _persist_and_print_failure(args.output_dir, failure)
        return 1
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        HwpxTemplateRenderError,
        SemanticContractError,
        NativePageValidationError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "source": str(args.source),
                    "output_dir": str(args.output_dir),
                    "institution": args.institution,
                    "document_type": args.document_type,
                    "template_id": template_id,
                    "template_id_source": template_id_source,
                    "status": "candidate",
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _base_failure_summary(
    args: argparse.Namespace, template_id: str, template_id_source: str
) -> dict:
    return {
        "ok": False,
        "source": str(args.source),
        "output_dir": str(args.output_dir),
        "institution": args.institution,
        "document_type": args.document_type,
        "template_id": template_id,
        "template_id_source": template_id_source,
        "status": "candidate",
    }


def _persist_and_print_failure(output_dir: Path, failure: dict) -> None:
    text = json.dumps(failure, ensure_ascii=False, indent=2)
    if output_dir.is_dir():
        (output_dir / "qa.report.json").write_text(text + "\n", encoding="utf-8")
    print(text)




def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generated_template_id(
    source: Path,
    institution: str,
    document_type: str,
) -> str:
    identity = "\0".join(
        (
            institution.strip(),
            document_type.strip(),
            _sha256(source),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"tpl_{digest[:24]}"


if __name__ == "__main__":
    raise SystemExit(main())
