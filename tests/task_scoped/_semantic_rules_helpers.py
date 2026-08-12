from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from core.templates.hwpx_semantic_classifier import classify_document_semantics
from core.templates.hwpx_semantic_contract import SemanticRole
from core.templates.hwpx_separation_rules import SeparationRules

# 실제 기관 원본 HWPX는 --rules 없이 돌리면 same-node 표식 경계 노드가
# semantic classifier에서 AMBIGUOUS로 남는다(독립 콘텐츠 근거가 없으므로).
# 이 헬퍼는 사람이 검토 후 기존 CONTENT로 확정했을 --rules 파일을 생성해,
# 이 semantic 작업과 무관한 기존 회귀 테스트가 그 결과를 계속 검증하게 한다.
# field 의미 자체를 지어내지 않는다 — 원래 legacy 분류기가 이미 CONTENT로
# 판정했던 노드만 명시적으로 확정한다.


def write_content_rules_for_ambiguous_nodes(source: Path, output_path: Path) -> Path:
    entries: list[dict[str, object]] = []
    with zipfile.ZipFile(source) as package:
        names = sorted(
            name
            for name in package.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for name in names:
            section = name.rsplit("/", 1)[-1]
            root = ET.fromstring(package.read(name))
            decisions = classify_document_semantics(root, section, SeparationRules())
            for decision in decisions:
                if decision.role is not SemanticRole.AMBIGUOUS:
                    continue
                entries.append(
                    {
                        "role": "content",
                        "section": section,
                        "text_node_index": decision.location.text_node_index,
                    }
                )
    output_path.write_text(
        json.dumps({"rules": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
