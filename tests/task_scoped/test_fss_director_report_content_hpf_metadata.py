from __future__ import annotations

import json
import re
import sys
import zipfile
from collections.abc import MutableMapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.adapters.hwpx_template_renderer import (
    HwpxTemplateRenderError,
    JsonValue,
    RenderExecutionContext,
    orchestrate_hwpx_render,
)
from core.adapters.hwpx_template_input import prepare_hwpx_template_input
from scripts.templates.render_hwpx_template import main as render_cli

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = (
    ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"
)
CONTENT_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "template-content"
    / "fss_director_report.input.json"
)
REQUESTED_AT = datetime(2026, 8, 3, 5, 49, 12, tzinfo=timezone.utc)
META_NAMES = (
    "creator",
    "subject",
    "description",
    "lastsaveby",
    "CreatedDate",
    "ModifiedDate",
    "date",
    "keyword",
)


def _content() -> MutableMapping[str, JsonValue]:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def _hpf(package: Path) -> str:
    with zipfile.ZipFile(package) as archive:
        return archive.read("Contents/content.hpf").decode("utf-8")


def _title(xml: str) -> str:
    match = re.search(r"<opf:title[^>]*>(.*?)</opf:title>", xml, re.DOTALL)
    assert match is not None
    return match.group(1)


def _meta(xml: str, name: str) -> str:
    match = re.search(
        rf'<opf:meta\b[^>]*\bname="{re.escape(name)}"[^>]*'
        r'(?:/>|>(.*?)</opf:meta>)',
        xml,
        re.DOTALL,
    )
    assert match is not None
    return match.group(1) or ""


def _mask_target_metadata(xml: str) -> str:
    masked, title_count = re.subn(
        r"(<opf:title\b[^>]*?)(?:\s*/>|>.*?</opf:title>)",
        r"\1>TARGET</opf:title>",
        xml,
        flags=re.DOTALL,
    )
    assert title_count == 1
    for name in META_NAMES:
        pattern = re.compile(
            rf'(<opf:meta\b(?=[^>]*\bname="{re.escape(name)}")[^>]*?)'
            r'(?:\s*/>|>.*?</opf:meta>)',
            re.DOTALL,
        )
        masked, count = pattern.subn(r"\1>TARGET</opf:meta>", masked)
        assert count == 1, name
    return masked


def _broken_base(tmp_path: Path, *, target: str, duplicate: bool) -> Path:
    source_path = TEMPLATE_DIR / "source.hwpx"
    output_path = tmp_path / f"broken-{target}-{duplicate}.hwpx"
    with zipfile.ZipFile(source_path) as source, zipfile.ZipFile(
        output_path, "w"
    ) as destination:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/content.hpf":
                xml = payload.decode("utf-8")
                pattern = (
                    re.compile(
                        r"<opf:title(?:\s*/>|>.*?</opf:title>)",
                        re.DOTALL,
                    )
                    if target == "title"
                    else re.compile(
                        rf'<opf:meta\b[^>]*\bname="{re.escape(target)}"[^>]*'
                        r'(?:/>|>.*?</opf:meta>)',
                        re.DOTALL,
                    )
                )
                match = pattern.search(xml)
                assert match is not None
                replacement = match.group(0) * 2 if duplicate else ""
                payload = pattern.sub(replacement, xml, count=1).encode("utf-8")
            destination.writestr(info, payload)
    return output_path


def test_fss_content_hpf_uses_source_content_and_execution_context(
    tmp_path: Path,
) -> None:
    content = _content()
    output = tmp_path / "metadata.hwpx"
    context = RenderExecutionContext(
        requester_name="오영서",
        requested_at=REQUESTED_AT,
    )

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=context,
    )

    xml = _hpf(output)
    assert _title(xml) == content["제목"]
    assert _meta(xml, "creator") == "오영서"
    assert _meta(xml, "subject") == "추진 배경, 주요 내용"
    assert _meta(xml, "description") == content["결론"]
    assert _meta(xml, "lastsaveby") == "오영서"
    assert _meta(xml, "date") == content["보고일"]
    assert _meta(xml, "keyword") == (
        "언론보도, 디지털금융국, 추진 배경, 주요 내용"
    )
    assert _meta(xml, "CreatedDate") == "2026-08-03T05:49:12Z"
    assert _meta(xml, "ModifiedDate") == "2026-08-03T05:49:12Z"
    assert _mask_target_metadata(xml) == _mask_target_metadata(
        _hpf(TEMPLATE_DIR / "source.hwpx")
    )


@pytest.mark.parametrize("target", ["title", "creator"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_fss_content_hpf_rejects_missing_or_duplicate_metadata(
    tmp_path: Path,
    target: str,
    duplicate: bool,
) -> None:
    context = RenderExecutionContext("오영서", REQUESTED_AT)
    broken = _broken_base(tmp_path, target=target, duplicate=duplicate)

    with pytest.raises(HwpxTemplateRenderError, match=target):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            _content(),
            tmp_path / "invalid.hwpx",
            execution_context=context,
            base_hwpx=broken,
            validate=False,
        )


def test_fss_content_hpf_clears_description_when_conclusion_is_missing(
    tmp_path: Path,
) -> None:
    content = _content()
    del content["결론"]
    output = tmp_path / "without-conclusion.hwpx"

    orchestrate_hwpx_render(
        TEMPLATE_DIR,
        content,
        output,
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
        validate=False,
    )

    assert _meta(_hpf(output), "description") == ""


def test_prepared_fss_metadata_keeps_missing_optional_conclusion_empty() -> None:
    content = _content()
    content.pop("결론")

    prepared = prepare_hwpx_template_input(
        TEMPLATE_DIR,
        content,
        execution_context=RenderExecutionContext("오영서", REQUESTED_AT),
    )

    assert prepared.package_metadata.description == ""


def test_render_cli_passes_requester_name_to_fss_metadata(tmp_path: Path) -> None:
    content_path = tmp_path / "content.json"
    content_path.write_text(
        json.dumps(
            {"template_id": "fss_director_report", "fields": _content()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "cli.hwpx"

    exit_code = render_cli(
        [
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원장보고",
            "--content",
            str(content_path),
            "--output",
            str(output),
            "--requester-name",
            "오영서",
        ]
    )

    assert exit_code == 0
    assert _meta(_hpf(output), "creator") == "오영서"
    assert _meta(_hpf(output), "lastsaveby") == "오영서"


def test_render_cli_rejects_fss_request_without_requester_name(
    tmp_path: Path,
) -> None:
    content_path = tmp_path / "content.json"
    content_path.write_text(
        json.dumps(
            {"template_id": "fss_director_report", "fields": _content()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "missing-requester.hwpx"

    exit_code = render_cli(
        [
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원장보고",
            "--content",
            str(content_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert not output.exists()


def test_execution_context_rejects_blank_requester_name() -> None:
    with pytest.raises(HwpxTemplateRenderError, match="requester_name"):
        RenderExecutionContext("  ", REQUESTED_AT)


def test_fss_render_requires_execution_context(tmp_path: Path) -> None:
    with pytest.raises(HwpxTemplateRenderError, match="execution_context"):
        orchestrate_hwpx_render(
            TEMPLATE_DIR,
            _content(),
            tmp_path / "missing-context.hwpx",
            validate=False,
        )
