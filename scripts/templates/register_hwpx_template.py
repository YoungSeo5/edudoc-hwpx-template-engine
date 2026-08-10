#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.templates.hwpx_template_registration import (  # noqa: E402
    TemplateRegistrationError,
    register_hwpx_template_candidate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "사용자가 승인한 HWPX 템플릿 후보를 정식 경로에 등록하고 "
            "TemplateRegistry로 확인합니다."
        )
    )
    parser.add_argument("--candidate", required=True, type=Path, help="후보 폴더")
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=ROOT / "templates" / "institutions",
        help="정식 템플릿 루트",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="후보를 승인해 등록한다는 사용자의 명시적 의사",
    )
    args = parser.parse_args(argv)

    try:
        result = register_hwpx_template_candidate(
            args.candidate,
            registry_root=args.registry_root,
            approve=args.approve,
        )
    except (OSError, json.JSONDecodeError, TemplateRegistrationError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "candidate": str(args.candidate),
                    "registered": None,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "candidate": str(args.candidate),
                "registered": {
                    "institution": result.institution,
                    "document_type": result.document_type,
                    "template_id": result.template_id,
                    "path": str(result.destination),
                },
                "error": None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
