from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.adapters.hwpx_package_metadata import (
    PACKAGE_META_NAMES,
    PackageMetadata,
    build_package_metadata,
)
from core.adapters.hwpx_template_input import ResolvedMetadata


ROOT = Path(__file__).resolve().parents[2]


def test_package_metadata_is_institution_neutral() -> None:
    requested_at = datetime(2026, 9, 18, tzinfo=UTC)

    result = build_package_metadata(
        ResolvedMetadata(
            title="주간업무보고서",
            subject="주간 업무",
            description="기관 보고서",
            report_date="2026-09-18",
            keywords="주간,업무",
        ),
        requester_name="작성자",
        requested_at=requested_at,
    )

    assert isinstance(result, PackageMetadata)
    assert result.creator == "작성자"
    assert result.requested_at == requested_at
    assert PACKAGE_META_NAMES == (
        "creator",
        "subject",
        "description",
        "lastsaveby",
        "date",
        "keyword",
        "CreatedDate",
        "ModifiedDate",
    )


def test_runtime_has_no_fss_named_adapter() -> None:
    adapters = ROOT / "core" / "adapters"

    assert not (adapters / "hwpx_fss_director_report.py").exists()
    for path in adapters.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "Fss" not in source
        assert "FSS" not in source
        assert "fss_" not in source


def test_skill_routes_edudoc_design_before_document_authoring() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "<registry>/provision/edudoc/_design/design.json" in skill
    assert "고정 문구·고정 라벨·입력 필드·계층 구조" in skill
    assert "초기 승인 템플릿이 없는 상태가 정상" in skill
