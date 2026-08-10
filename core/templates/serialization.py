"""Read and write template candidate and approved-template artifacts."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .models import TemplateCandidate
from .quality.false_positive import (
    FalsePositiveRule,
    learned_rules_from_diagnostics,
)
from .quality.gate import GateResult
from .quality.review import render_review
from .quality.success_rules import SuccessRules

# 이 모듈은 품질 파이프라인의 메모리 객체를 디스크 산출물로 바꾼다.
# candidate/검토 자료는 항상 기록하지만, approved template.json은
# 성공 게이트와 명시적 approve가 동시에 충족될 때만 기록한다.

def write_pipeline_artifacts(
    candidate: TemplateCandidate,
    gate: GateResult,
    output_dir: Path | str,
    *,
    approve: bool = False,
    success_rules: SuccessRules | None = None,
    false_positive_rules: list[FalsePositiveRule] | None = None,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # 흐름 1: 자동 분석 결과와 사람이 읽을 검토·근거 자료를 먼저 남긴다.
    paths["candidate"] = output_dir / "template.candidate.json"
    _write_json(paths["candidate"], candidate.to_dict())

    paths["review"] = output_dir / "template.review.md"
    paths["review"].write_text(render_review(candidate, gate), encoding="utf-8")

    paths["evidence"] = output_dir / "evidence.md"
    paths["evidence"].write_text(
        "# Template Evidence\n\n"
        + "\n".join(f"- {item}" for item in candidate.evidence)
        + "\n",
        encoding="utf-8",
    )

    # 흐름 2: 이번 판정에 사용한 성공 규칙과 새로 학습한 오탐 규칙도
    # 함께 저장해 다음 실행이 같은 검토 맥락을 재사용할 수 있게 한다.
    rules = success_rules or SuccessRules()
    paths["success_rules"] = output_dir / "success-rules.json"
    _write_json(paths["success_rules"], rules.to_dict())

    learned = learned_rules_from_diagnostics(candidate)
    merged_rules = _merge_false_positive_rules(
        [*(false_positive_rules or []), *learned]
    )
    paths["false_positive_rules"] = output_dir / "false-positive-rules.json"
    _write_json(
        paths["false_positive_rules"],
        {"rules": [rule.to_dict() for rule in merged_rules]},
    )

    # 흐름 3: 게이트 통과 시 validated 스냅샷을 기록한다. approve=True는
    # 사람의 명시적 승인 의사로 취급되며, 그때만 status를 approved로 바꾼
    # template.json을 추가한다.
    if gate.passed:
        paths["validated"] = output_dir / "template.validated.json"
        _write_json(paths["validated"], candidate.to_dict())
        if approve:
            approved = deepcopy(candidate.to_dict())
            approved["status"] = "approved"
            paths["template"] = output_dir / "template.json"
            _write_json(paths["template"], approved)
    elif approve:
        raise ValueError("A rejected template candidate cannot be approved.")
    return paths


# TemplateRegistry가 template.json을 다시 TemplateCandidate로 읽을 때 쓰는
# 역직렬화 경계다.
def load_candidate(path: Path | str) -> TemplateCandidate:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TemplateCandidate.from_dict(data)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _merge_false_positive_rules(
    rules: list[FalsePositiveRule],
) -> list[FalsePositiveRule]:
    result: list[FalsePositiveRule] = []
    seen: set[tuple] = set()
    for rule in rules:
        key = (
            rule.target,
            rule.pattern,
            rule.institution,
            rule.document_type,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result
