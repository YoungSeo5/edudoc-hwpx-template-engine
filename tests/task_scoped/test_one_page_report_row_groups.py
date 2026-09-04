from __future__ import annotations

from pathlib import Path

import pytest

from core.adapters.hwpx_layout_components import (
    HwpxLayoutComponentError,
    expand_family_components,
)


ROOT = Path(__file__).resolve().parents[2]
RECIPE = ROOT / "templates" / "institutions" / "edudoc" / "_families" / "one_page_report" / "recipe.json"


def test_row_groups_materialize_each_declared_group() -> None:
    sections, _, _ = expand_family_components(
        "one_page_report",
        RECIPE,
        [
            {"type": "masthead"},
            {"type": "title_block", "text": "보고서"},
            {
                "type": "header_info",
                "row_groups": [
                    {"row_count": 1, "pairs_per_row": 1},
                    {"row_count": 4, "pairs_per_row": 2},
                ],
                "rows": [
                    {"label": "A", "field_id": "a", "sample_value": "a"},
                    {"label": "B", "field_id": "b", "sample_value": "b"},
                    {"label": "C", "field_id": "c", "sample_value": "c"},
                    {"label": "D", "field_id": "d", "sample_value": "d"},
                    {"label": "E", "field_id": "e", "sample_value": "e"},
                ],
            },
        ],
    )

    assert [len(section["rows"]) for section in sections[1:]] == [1, 4]
    assert [section["pairs_per_row"] for section in sections[1:]] == [1, 2]


@pytest.mark.parametrize("row_counts", [(4,), (6,)])
def test_row_groups_rejects_incomplete_or_excessive_consumption(row_counts: tuple[int, ...]) -> None:
    with pytest.raises(HwpxLayoutComponentError, match="must consume every metadata row exactly once"):
        expand_family_components(
            "one_page_report",
            RECIPE,
            [
                {"type": "masthead"},
                {"type": "title_block", "text": "보고서"},
                {
                    "type": "header_info",
                    "row_groups": [{"row_count": row_count, "pairs_per_row": 1} for row_count in row_counts],
                    "rows": [
                        {"label": "A", "field_id": "a", "sample_value": "a"},
                        {"label": "B", "field_id": "b", "sample_value": "b"},
                        {"label": "C", "field_id": "c", "sample_value": "c"},
                        {"label": "D", "field_id": "d", "sample_value": "d"},
                        {"label": "E", "field_id": "e", "sample_value": "e"},
                    ],
                },
            ],
        )
