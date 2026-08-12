#!/usr/bin/env python3
"""Render an approved HWPX template from a source content file (.md/.txt/.hwpx).

Deterministic fields (date/title/department/contact) are extracted from the
source and mapped onto the template's ``placeholder_map.json``. Judgment
fields (body paragraphs, conclusions, ...) cannot be filled from source text
alone; if any field is left unresolved this refuses to render rather than
shipping a document with visible ``확인 필요`` placeholders.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_template_input import RenderExecutionContext  # noqa: E402
from core.adapters.hwpx_template_renderer import HwpxTemplateRenderError  # noqa: E402
from core.document_api import (  # noqa: E402
    HwpxUnresolvedFieldsError,
    render_document_from_source,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="승인된 기관 템플릿에 source 파일(.md/.txt/.hwpx)을 매핑해 HWPX를 생성합니다."
    )
    parser.add_argument("--institution", required=True, help="기관명")
    parser.add_argument("--document-type", required=True, help="문서 유형")
    parser.add_argument("--source", required=True, type=Path, help="source 파일 (.md/.txt/.hwpx)")
    parser.add_argument("--output", required=True, type=Path, help="출력 HWPX")
    parser.add_argument(
        "--requester-name",
        required=True,
        help="문서 생성 요청자 이름. content.hpf 작성자·최종저장자로 기록된다",
    )
    args = parser.parse_args(argv)
    requested_at = datetime.now(timezone.utc)

    execution_context = RenderExecutionContext(
        requester_name=args.requester_name,
        requested_at=requested_at,
    )
    try:
        result = render_document_from_source(
            args.institution,
            args.document_type,
            args.source,
            args.output,
            execution_context,
        )
    except HwpxUnresolvedFieldsError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "institution": args.institution,
                    "document_type": args.document_type,
                    "output": None,
                    "unresolved_fields": exc.unresolved_fields,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except (OSError, ValueError, json.JSONDecodeError, HwpxTemplateRenderError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "institution": args.institution,
                    "document_type": args.document_type,
                    "output": None,
                    "unresolved_fields": [],
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
                "institution": args.institution,
                "document_type": args.document_type,
                "output": str(result.output),
                "filled_fields": result.filled_fields,
                "missing_fields": result.missing_fields,
                "leftover_placeholders": result.leftover_placeholders,
                "unresolved_fields": [],
                "title_updated": result.title_updated,
                "error": None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
