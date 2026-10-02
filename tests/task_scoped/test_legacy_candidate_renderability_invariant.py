"""approved artifact renderability invariant: legacy(source-extracted) 경로.

`semantic_contract.json`이 없는 legacy 후보는 지금까지 등록(승인) 시점에
자신의 content.sample.json으로 실제 렌더가 되는지 전혀 확인하지 않았다.
self-authored/contract-complete 경로는 `_validate_contract_complete_candidate`가
이미 확인한다. 이 테스트는 legacy 경로에도 같은 수준의 확인이 생겼는지,
그리고 그 확인에 semantic_contract.json을 새로 요구하지 않는지 증명한다.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from core.adapters.hwpx_template_renderer import snapshot_source_hwpx
from core.templates import hwpx_template_registration as registration_module
from core.templates.hwpx_layout_context import LAYOUT_CONTRACT, DocumentLayout
from core.templates.hwpx_template_registration import (
    TemplateRegistrationError,
    register_hwpx_template_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
BROTHER_HWPX = (
    ROOT / "references" / "document-types" / "public-plan"
    / "브라더 공공기관 보고서 양식.hwpx"
)


def _legacy_candidate(
    tmp_path: Path,
    *,
    sample_fields: dict[str, str],
    template_id: str = "legacy_renderable_demo",
) -> Path:
    """semantic_contract.json 없이, 실제로 렌더 가능한 최소 legacy 후보를 만든다."""
    candidate = tmp_path / "institutions" / "candidates" / "candidate"
    candidate.mkdir(parents=True)

    section0 = zipfile.ZipFile(BROTHER_HWPX).read("Contents/section0.xml").decode("utf-8")
    target = next(t for t in re.findall(r"<hp:t>([^<]+)</hp:t>", section0) if t.strip())
    template_xml = section0.replace(f"<hp:t>{target}</hp:t>", "<hp:t>{{demo_field}}</hp:t>", 1)

    (candidate / "raw").mkdir()
    (candidate / "raw" / "section0.xml").write_text(section0, encoding="utf-8")
    (candidate / "template").mkdir()
    (candidate / "template" / "section0.template.xml").write_text(template_xml, encoding="utf-8")

    header_xml = zipfile.ZipFile(BROTHER_HWPX).read("Contents/header.xml")
    paragraphs = [
        node
        for node in ElementTree.fromstring(template_xml).iter()
        if node.tag.rsplit("}", 1)[-1] == "p"
    ]
    field = {
        "field_id": "demo_field",
        "placeholder": "{{demo_field}}",
        "section": "section0.xml",
        "table": None,
        "row": None,
        "col": None,
        "paragraph_index": next(
            index
            for index, paragraph in enumerate(paragraphs)
            if "{{demo_field}}" in "".join(paragraph.itertext())
        ),
    }
    layout = DocumentLayout.read(template_xml, header_xml)
    field["layout_context"] = layout.context_for(field)
    (candidate / "placeholder_map.json").write_text(
        json.dumps(
            {
                "template_id": template_id,
                "layout_contract": LAYOUT_CONTRACT,
                "section_paragraph_counts": {"section0.xml": len(paragraphs)},
                "paragraph_style_margins": layout.margins_of_referenced_styles([field]),
                "fields": [field],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (candidate / "content.sample.json").write_text(
        json.dumps({"template_id": template_id, "fields": sample_fields}, ensure_ascii=False),
        encoding="utf-8",
    )
    (candidate / "template.review.md").write_text("# review\n", encoding="utf-8")
    (candidate / "template.json").write_text(
        json.dumps(
            {
                "identity": {
                    "institution": "브라더",
                    "document_type": "legacy_renderable_demo",
                    "extends": None,
                    "template_id": template_id,
                    "template_name": "legacy_renderable_demo",
                },
                "reference_format": "hwpx",
                "reference_path": "reference.hwpx",
                "status": "candidate",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    snapshot_source_hwpx(BROTHER_HWPX, candidate)
    return candidate


def test_registration_accepts_legacy_candidate_whose_sample_content_renders_cleanly(
    tmp_path: Path,
) -> None:
    candidate = _legacy_candidate(tmp_path, sample_fields={"demo_field": "정상 값"})
    registry_root = tmp_path / "institutions"

    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    assert result.template_id == "legacy_renderable_demo"


def test_renderability_check_uses_registry_tmp_not_os_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production registration checks use the registry _tmp/ boundary."""
    candidate = _legacy_candidate(tmp_path, sample_fields={"demo_field": "정상 값"})
    registry_root = tmp_path / "institutions"

    real_temporary_directory = registration_module.tempfile.TemporaryDirectory
    seen_dirs: list[Path | None] = []

    class _RecordingTemporaryDirectory(real_temporary_directory):
        def __init__(self, *args, **kwargs):
            seen_dirs.append(kwargs.get("dir"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        registration_module.tempfile, "TemporaryDirectory", _RecordingTemporaryDirectory
    )

    register_hwpx_template_candidate(candidate, registry_root=registry_root, approve=True)

    assert seen_dirs == [registry_root / "_tmp"]
    assert not any((registry_root / "_tmp").iterdir())


def test_registration_rejects_legacy_candidate_that_cannot_render_its_own_sample_content(
    tmp_path: Path,
) -> None:
    # content.sample.json이 placeholder_map의 demo_field가 아닌 다른 필드를
    # 선언한다 -> demo_field는 채워지지 않고 {{demo_field}}가 그대로 남는다.
    candidate = _legacy_candidate(
        tmp_path, sample_fields={"other_field": "정상 값"}
    )
    registry_root = tmp_path / "institutions"

    with pytest.raises(
        TemplateRegistrationError,
        match="unresolved placeholders",
    ):
        register_hwpx_template_candidate(
            candidate,
            registry_root=registry_root,
            approve=True,
        )

    assert candidate.is_dir()
    assert not (registry_root / "approved").exists()


def test_legacy_candidate_with_no_declared_fields_skips_renderability_check(
    tmp_path: Path,
) -> None:
    """필드가 아직 없는 최소 후보(단위 테스트 스텁류)는 확인할 렌더 대상이
    없으므로 새 검사가 등록을 막지 않는다."""
    candidate = _legacy_candidate(tmp_path, sample_fields={})
    registry_root = tmp_path / "institutions"

    # demo_field placeholder가 채워지지 않아 render_candidate_roundtrip을
    # 실제로 호출했다면 실패했을 것이다. fields가 비어 있으므로 건너뛴다.
    result = register_hwpx_template_candidate(
        candidate,
        registry_root=registry_root,
        approve=True,
    )

    assert result.template_id == "legacy_renderable_demo"
