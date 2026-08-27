"""잘못된 hierarchy level과 잘못된 cardinality는 fallback 없이 fail-fast해야 한다.

이미 구현에 존재하는 두 검증(HwpxTemplateAuthoringError, SemanticContractError)의
회귀 커버리지가 없어서 추가한다. 어느 쪽도 다른 값으로 조용히 대체하거나
기본값으로 넘어가지 않고, 명시적으로 실패해야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.adapters.hwpx_semantic_contract import (
    SemanticContractError,
    load_semantic_contract,
)
from core.adapters.hwpx_template_authoring import (
    HwpxTemplateAuthoringError,
    _parse_hierarchy_items,
)


def _hierarchy_item(levels: list[dict[str, object]], item_level: int = 1) -> dict[str, object]:
    return {
        "hierarchy": levels,
        "items": [{"level": item_level, "text": "본문"}],
    }


def test_duplicate_hierarchy_level_fails_fast_without_fallback() -> None:
    item = _hierarchy_item(
        [
            {
                "level": 1,
                "marker": "-",
                "native_intent_hwpunit": 0,
                "line_spacing_percent": 130,
            },
            {
                "level": 1,
                "marker": "•",
                "native_intent_hwpunit": 1000,
                "line_spacing_percent": 130,
            },
        ]
    )

    with pytest.raises(HwpxTemplateAuthoringError, match="must be unique and positive"):
        _parse_hierarchy_items(0, item)


def test_non_positive_hierarchy_level_fails_fast_without_fallback() -> None:
    item = _hierarchy_item(
        [
            {
                "level": 0,
                "marker": "-",
                "native_intent_hwpunit": 0,
                "line_spacing_percent": 130,
            },
        ],
        item_level=0,
    )

    with pytest.raises(HwpxTemplateAuthoringError, match="must be unique and positive"):
        _parse_hierarchy_items(0, item)


def _semantic_contract(cardinality: object) -> dict[str, object]:
    return {
        "semantic_contract_version": "v1",
        "contract_id": "invalid_cardinality_test",
        "template_request_id": "invalid_cardinality_test_request",
        "institution": "demo",
        "document_type": "demo",
        "elements": [
            {
                "element_id": "e1",
                "role": "CONTENT",
                "field_id": "f1",
                "required": True,
                "cardinality": cardinality,
                "content_type": "text",
            }
        ],
    }


def test_invalid_cardinality_value_fails_fast_without_fallback(tmp_path: Path) -> None:
    contract_path = tmp_path / "semantic_contract.json"
    contract_path.write_text(
        json.dumps(_semantic_contract("several"), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(SemanticContractError, match="invalid CONTENT semantic element"):
        load_semantic_contract(contract_path)


def test_missing_cardinality_fails_fast_without_fallback(tmp_path: Path) -> None:
    contract_path = tmp_path / "semantic_contract.json"
    contract_path.write_text(
        json.dumps(_semantic_contract(None), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(SemanticContractError, match="invalid CONTENT semantic element"):
        load_semantic_contract(contract_path)
