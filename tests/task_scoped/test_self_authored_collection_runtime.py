from __future__ import annotations

import json
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hwpx_template_renderer import render_candidate_roundtrip  # noqa: E402
from scripts.templates import author_hwpx_template  # noqa: E402

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_NS = {"hp": _HP}
_REQUEST = ROOT / "tests/fixtures/template-contracts/weekly-report-v2.template_request.json"
_SEMANTIC = ROOT / "tests/fixtures/template-contracts/weekly-report-v2.semantic_contract.json"
_DESIGN = ROOT / "templates/institutions/edudoc/_design/design.json"
_SPEC = ROOT / "tests/fixtures/template-spec/weekly_report_one_page.template_spec.json"


@pytest.fixture(scope="module")
def self_authored_candidate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    candidate_id = f"collection_runtime_{uuid.uuid4().hex}"
    candidate = tmp_path_factory.mktemp("template-candidates") / candidate_id
    exit_code = author_hwpx_template.main(
        [
            "--template-request", str(_REQUEST),
            "--semantic-contract", str(_SEMANTIC),
            "--institution-design", str(_DESIGN),
            "--template-spec", str(_SPEC),
            "--institution", "edudoc",
            "--document-type", "주간업무보고서",
            "--output-dir", str(candidate),
            "--candidate-id", candidate_id,
            "--template-id", f"tpl_{uuid.uuid4().hex}",
        ]
    )
    assert exit_code in (0, 1)
    assert (candidate / "placeholder_map.json").is_file()
    collections = json.loads(
        (candidate / "placeholder_map.json").read_text(encoding="utf-8")
    )["collections"]
    by_path = {entry["canonical_path"]: entry for entry in collections}
    assert by_path["major_tasks"]["kind"] == "table_row"
    assert by_path["major_tasks"]["prototype_location"]["table"] == 3
    assert by_path["next_week_plan"]["kind"] == "hierarchy_paragraph"
    assert {
        entry["prototype_level"]
        for entry in by_path["next_week_plan"]["prototype_paragraphs"]
    } == {1, 2}
    return candidate


def _section_root(output: Path) -> ET.Element:
    with zipfile.ZipFile(output) as package:
        return ET.fromstring(package.read("Contents/section0.xml"))


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{{{_HP}}}t"))


def _major_task_table(root: ET.Element) -> ET.Element:
    for table in root.findall(".//hp:tbl", _NS):
        rows = table.findall("./hp:tr", _NS)
        if rows and _paragraph_text(rows[0]) == "업무명상태일정":
            return table
    raise AssertionError("major_tasks table was not found")


def _major_task_rows(root: ET.Element) -> list[ET.Element]:
    return _major_task_table(root).findall("./hp:tr", _NS)


@pytest.mark.parametrize(
    ("major_tasks", "next_week_plan"),
    [
        # fewer than the prototype's 2 sample rows
        ([], []),
        ([{"task_name": "단일 업무", "status": "진행", "due_date": "8/22"}], [{"level": 1, "text": "단일 계획"}]),
        # exactly the prototype's original 2 sample rows
        (
            [
                {"task_name": "업무 X", "status": "완료", "due_date": "8/18"},
                {"task_name": "업무 Y", "status": "진행", "due_date": "8/19"},
            ],
            [
                {"level": 1, "text": "동일 계획"},
                {"level": 2, "text": "동일 계획 세부"},
            ],
        ),
        # more than the prototype's 2 sample rows
        (
            [
                {"task_name": "업무 A", "status": "완료", "due_date": "8/20"},
                {"task_name": "업무 B", "status": "진행", "due_date": "8/21"},
                {"task_name": "업무 C", "status": "예정", "due_date": "8/22"},
            ],
            [
                {"level": 1, "text": "상위 계획"},
                {"level": 2, "text": "하위 계획 A"},
                {"level": 2, "text": "하위 계획 B"},
            ],
        ),
    ],
)
def test_self_authored_collections_materialize_for_zero_one_and_many_items(
    self_authored_candidate: Path,
    tmp_path: Path,
    major_tasks: list[dict[str, str]],
    next_week_plan: list[dict[str, str | int]],
) -> None:
    output = tmp_path / "final.hwpx"

    result = render_candidate_roundtrip(
        self_authored_candidate,
        {"major_tasks": major_tasks, "next_week_plan": next_week_plan},
        output,
    )

    root = _section_root(output)
    table = _major_task_table(root)
    rows = table.findall("./hp:tr", _NS)
    assert len(rows) == len(major_tasks) + 1
    assert [_paragraph_text(row) for row in rows[1:]] == [
        f"{item['task_name']}{item['status']}{item['due_date']}" for item in major_tasks
    ]
    # Structural invariant (verified against every real reference HWPX table in
    # this repository, docs/tasks/hwpx-renderer-table-row-metadata-sync.md):
    # hp:tbl@rowCnt must equal the table's actual hp:tr count, and every cell
    # in a given row must share one hp:cellAddr@rowAddr equal to that row's
    # 0-indexed position, with no gaps or repeats across rows. A table that
    # violates this passes strict/zip validation but Hancom refuses to open
    # it as a damaged file.
    assert table.get("rowCnt") == str(len(rows))
    row_addrs = [
        {cell_addr.get("rowAddr") for cell_addr in row.findall(".//hp:cellAddr", _NS)}
        for row in rows
    ]
    assert row_addrs == [{str(index)} for index in range(len(rows))]
    top_level_text = [
        _paragraph_text(paragraph)
        for paragraph in root.findall("./hp:p", _NS)
    ]
    assert [text for text in top_level_text if "계획" in text] == [
        f"{'□ ' if item['level'] == 1 else '◦ '}{item['text']}"
        for item in next_week_plan
    ]
    assert not any(
        token in "".join(root.itertext())
        for token in ("major_tasks", "next_week_plan")
    )
    assert not any(
        token.startswith(("major_tasks", "next_week_plan"))
        for token in result.leftover_placeholders
    )
