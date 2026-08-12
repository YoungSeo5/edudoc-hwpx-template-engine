"""alias_map이 묶은 field_id가 재추출 후에도 같은 내용을 가리키는지 QA가 확인한다.

`field_id`는 "문서 순서로 N번째 content" 라는 순번이라, 앞쪽 분류가 하나만 달라져도
뒤 번호가 전부 밀린다. alias_map은 사람 이름을 그 순번에 묶으므로 이름이 살아있는 한
검증을 통과하면서 조용히 다른 텍스트를 채운다.

변경 전에는 이 재배치를 아무도 잡지 못했다. 이제 QA가 등록된 placeholder_map의
category + sample_value를 후보와 비교해 거부한다. sample_value는 placeholder_map에만
두고 alias_map에 복사하지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _semantic_rules_helpers import write_content_rules_for_ambiguous_nodes  # noqa: E402
from core.templates.registry import TemplateRegistry  # noqa: E402
from scripts.templates import qa_hwpx_template  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ONE_PAGE = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원페이지"
DIRECTOR_REPORT = ROOT / "templates" / "institutions" / "금융감독원" / "금감원 원장보고"


def _registry_with(tmp_path: Path, fields: list[dict], alias: dict | None) -> Path:
    registered = tmp_path / "institutions" / "기관" / "문서"
    registered.mkdir(parents=True)
    (registered / "placeholder_map.json").write_text(
        json.dumps({"template_id": "demo", "fields": fields}, ensure_ascii=False),
        encoding="utf-8",
    )
    if alias is not None:
        (registered / "alias_map.json").write_text(
            json.dumps(alias, ensure_ascii=False), encoding="utf-8"
        )
    return tmp_path / "institutions"


def _candidate_with(tmp_path: Path, fields: list[dict]) -> Path:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "placeholder_map.json").write_text(
        json.dumps({"template_id": "demo", "fields": fields}, ensure_ascii=False),
        encoding="utf-8",
    )
    return candidate


def _field(field_id: str, category: str, sample: str) -> dict:
    return {
        "field_id": field_id,
        "placeholder": f"{{{{{field_id}}}}}",
        "category": category,
        "sample_value": sample,
    }


def test_bound_field_pointing_at_other_text_is_rejected(tmp_path: Path) -> None:
    """번호는 남았지만 다른 문장을 가리키는 경우 — 조용히 잘못 채워지던 사례."""
    root = _registry_with(
        tmp_path,
        [_field("content_12", "content", "(맑은고딕 15pt)")],
        {"template_id": "demo", "fields": {"진행상황 핵심": "content_12"}},
    )
    candidate = _candidate_with(
        tmp_path, [_field("content_12", "content", "휴먼명조 15pt")]
    )

    with pytest.raises(ValueError) as error:
        TemplateRegistry(root).verify_candidate_field_identity("기관", "문서", candidate)

    assert "content_12" in str(error.value)
    assert "(맑은고딕 15pt)" in str(error.value)


def test_bound_field_drift_error_includes_semantic_role_evidence(tmp_path: Path) -> None:
    """Todo7: 드리프트 오류에 후보 field의 semantic_role 근거를 덧붙인다."""
    root = _registry_with(
        tmp_path,
        [_field("content_12", "content", "(맑은고딕 15pt)")],
        {"template_id": "demo", "fields": {"진행상황 핵심": "content_12"}},
    )
    drifted = _field("content_12", "content", "휴먼명조 15pt")
    drifted["semantic_role"] = "marker_content"
    candidate = _candidate_with(tmp_path, [drifted])

    with pytest.raises(ValueError) as error:
        TemplateRegistry(root).verify_candidate_field_identity("기관", "문서", candidate)

    assert "[semantic_role=marker_content]" in str(error.value)


def test_unbound_field_drift_is_reported_without_raising(tmp_path: Path) -> None:
    """Todo7: 묶이지 않은 field의 드리프트는 실패시키지 않고 검토 근거로만 남긴다."""
    root = _registry_with(
        tmp_path,
        [
            _field("content_01", "content", "묶인 본문"),
            _field("content_02", "content", "묶이지 않은 본문"),
        ],
        {"template_id": "demo", "fields": {"본문": "content_01"}},
    )
    candidate = _candidate_with(
        tmp_path,
        [
            _field("content_01", "content", "묶인 본문"),
            _field("content_02", "content", "다른 본문으로 바뀜"),
        ],
    )

    report = TemplateRegistry(root).verify_candidate_field_identity("기관", "문서", candidate)

    assert report["checked"] is True
    assert len(report["unbound_drift"]) == 1
    assert "content_02" in report["unbound_drift"][0]


def test_bound_field_missing_from_the_candidate_is_rejected(tmp_path: Path) -> None:
    root = _registry_with(
        tmp_path,
        [_field("document_title_01", "document_title", "〈관련 현황〉")],
        {"template_id": "demo", "fields": {"현황 표제": "document_title_01"}},
    )
    candidate = _candidate_with(tmp_path, [_field("content_01", "content", "다른 본문")])

    with pytest.raises(ValueError) as error:
        TemplateRegistry(root).verify_candidate_field_identity("기관", "문서", candidate)

    assert "없음" in str(error.value)


def test_unbound_fields_may_be_renumbered_freely(tmp_path: Path) -> None:
    """alias_map이 묶지 않은 field는 사람 입력이 흐르지 않으므로 재배치를 허용한다."""
    root = _registry_with(
        tmp_path,
        [
            _field("content_01", "content", "묶인 본문"),
            _field("content_02", "content", "안 묶인 본문"),
        ],
        {"template_id": "demo", "fields": {"본문": "content_01"}},
    )
    candidate = _candidate_with(
        tmp_path,
        [
            _field("content_01", "content", "묶인 본문"),
            _field("content_02", "content", "완전히 다른 본문"),
        ],
    )

    report = TemplateRegistry(root).verify_candidate_field_identity(
        "기관", "문서", candidate
    )

    assert report == {
        "checked": True,
        "compared_with": str((root / "기관" / "문서")),
        "bound_field_count": 1,
        "unbound_drift": [
            "content_02: ('content', '안 묶인 본문') -> ('content', '완전히 다른 본문')"
        ],
    }


def test_qa_rejects_a_reextraction_that_renumbers_bound_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """실제 사례: 금감원 원페이지를 지금 separator로 다시 뽑으면 순번이 재배치된다."""
    rules = write_content_rules_for_ambiguous_nodes(
        ONE_PAGE / "source.hwpx", tmp_path / "rules.json"
    )
    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(ONE_PAGE / "source.hwpx"),
            "--output-dir",
            str(tmp_path / "candidate"),
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원페이지",
            "--template-id",
            "fss_one_page",
            "--rules",
            str(rules),
        ]
    )

    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert summary["ok"] is False
    assert "alias_map.json이 묶은 field_id" in summary["error"]
    assert "document_title_01" in summary["error"]
    assert "content_12" in summary["error"]


def test_qa_checks_registered_identity_outside_repository_cwd(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside_cwd = tmp_path / "outside-repository"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)
    rules = write_content_rules_for_ambiguous_nodes(
        ONE_PAGE / "source.hwpx", tmp_path / "rules.json"
    )

    exit_code = qa_hwpx_template.main(
        [
            "--source",
            str(ONE_PAGE / "source.hwpx"),
            "--output-dir",
            str(tmp_path / "candidate"),
            "--institution",
            "금융감독원",
            "--document-type",
            "금감원 원페이지",
            "--template-id",
            "fss_one_page",
            "--rules",
            str(rules),
        ]
    )

    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert summary["ok"] is False
    assert "alias_map.json이 묶은 field_id" in summary["error"]


def test_qa_reports_when_there_is_nothing_to_compare_against(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rules = write_content_rules_for_ambiguous_nodes(
        DIRECTOR_REPORT / "source.hwpx", tmp_path / "rules.json"
    )
    qa_hwpx_template.main(
        [
            "--source",
            str(DIRECTOR_REPORT / "source.hwpx"),
            "--output-dir",
            str(tmp_path / "candidate"),
            "--institution",
            "금융감독원",
            "--document-type",
            "등록되지 않은 문서유형",
            "--template-id",
            "fss_unregistered_demo",
            "--rules",
            str(rules),
        ]
    )

    summary = json.loads(capsys.readouterr().out)

    assert summary["bound_field_identity"] == {
        "checked": False,
        "reason": "등록된 템플릿 없음",
    }
