#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_template_input import (  # noqa: E402
    RenderExecutionContext,
)
from core.adapters.hwpx_template_renderer import (  # noqa: E402
    HwpxTemplateRenderError,
    load_template_content,
    orchestrate_hwpx_render,
)
from core.templates.registry import TemplateRegistry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="승인된 기관 템플릿에 content.json을 채워 HWPX를 생성합니다."
    )
    parser.add_argument("--institution", required=True, help="기관명")
    parser.add_argument("--document-type", required=True, help="문서 유형")
    parser.add_argument("--content", required=True, type=Path, help="템플릿 content.json")
    parser.add_argument("--output", required=True, type=Path, help="출력 HWPX")
    # argparse required가 아닌 이유: 누락도 JSON 요약({"ok": false, ...})으로 보고한다.
    parser.add_argument(
        "--requester-name",
        help="문서 생성 요청자 이름. 최종 문서 생성에 반드시 필요하며 "
        "content.hpf 작성자·최종저장자로 기록된다",
    )
    args = parser.parse_args(argv)
    requested_at = datetime.now(timezone.utc)

    registry = TemplateRegistry(ROOT / "templates" / "institutions")
    template_id: str | None = None
    try:
        execution_context = (
            RenderExecutionContext(
                requester_name=args.requester_name,
                requested_at=requested_at,
            )
            if args.requester_name is not None
            else None
        )
        content = load_template_content(args.content)
        template_id = content.template_id
        candidate = registry.find(args.institution, args.document_type)
        if candidate is None:
            raise HwpxTemplateRenderError(
                "approved institution template not found: "
                f"{args.institution} / {args.document_type}"
            )
        if content.template_id != candidate.identity.template_id:
            raise HwpxTemplateRenderError(
                "template_id mismatch: "
                f"content={content.template_id!r}, "
                f"approved={candidate.identity.template_id!r}"
            )
        template_dir = registry.template_path(
            args.institution, args.document_type
        ).parent
        result = orchestrate_hwpx_render(
            template_dir,
            content.fields,
            args.output,
            execution_context=execution_context,
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        HwpxTemplateRenderError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "institution": args.institution,
                    "document_type": args.document_type,
                    "template_id": template_id,
                    "output": None,
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
                "template_id": content.template_id,
                "output": str(result.output),
                "filled_fields": result.filled_fields,
                "missing_fields": result.missing_fields,
                "leftover_placeholders": result.leftover_placeholders,
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
