"""masthead-structural-ownership task: end-to-end proof that masthead column
count/order/role now comes from the Institution Design Contract's
``masthead.slots``, not from a Python literal.

Before this task, ``core/adapters/hwpx_template_authoring.py`` decided which
column held which role via a module constant (``_MASTHEAD_TITLE_COLUMN = 1``)
and literal column indices (``0``/``2``) — no Institution Design Contract
field expressed that decision. This file proves two things directly against
the real generated HWPX XML (not just against the intermediate
``ResolvedAuthoringContract``, which ``test_hwpx_authoring_resolve.py``
already covers):

1. The unchanged edudoc `slots` order (``["logo_left", "title",
   "logo_right"]``, migrated into
   ``tests/fixtures/template-contracts/edudoc.institution_design.json`` by
   this same task) still materializes the exact same 1-row/3-column
   `logo-title-logo` masthead as before — a pure regression check.
2. Declaring a *different* `slots` order in a design contract actually moves
   the title/logo cells to different columns in the generated document —
   the only way this could happen is if authoring reads the declared order
   at materialize time instead of assuming a fixed position.

It also asserts the removed ``_MASTHEAD_TITLE_COLUMN`` constant is gone from
the module, so a future change cannot quietly reintroduce it as a hidden
fallback.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters import hwpx_template_authoring  # noqa: E402
from core.adapters.hwpx_authoring_resolve import HwpxAuthoringResolveError, resolve  # noqa: E402
from core.adapters.hwpx_template_authoring import (  # noqa: E402
    generate_source_hwpx,
    load_template_spec,
)

FIXTURE = ROOT / "tests" / "fixtures" / "template-spec" / "weekly_report.template_spec.json"
BASE_INSTITUTION_DESIGN_FIXTURE = (
    ROOT / "tests" / "fixtures" / "template-contracts" / "edudoc.institution_design.json"
)

_NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}


_UNSET = object()


def _write_design_with_slots(
    tmp_path: Path,
    slots: list[str] | None,
    *,
    row_count: object = _UNSET,
) -> Path:
    """Copy the real edudoc test fixture, replacing (or removing) masthead
    structural fields (``slots``, ``row_count``).

    ``slots=None`` removes the key entirely. ``row_count`` left at the
    default (``_UNSET``) keeps the fixture's own declared value (``1``);
    pass ``None`` to remove the key, or any other value to override it.

    Asset ``path`` values are made absolute (pointing at the original
    fixture's own ``assets/`` directory) since this copy is written under
    *tmp_path*, not next to the fixture's assets.
    """
    data = json.loads(BASE_INSTITUTION_DESIGN_FIXTURE.read_text(encoding="utf-8"))
    if slots is None:
        del data["masthead"]["slots"]
    else:
        data["masthead"]["slots"] = slots
    if row_count is None:
        del data["masthead"]["row_count"]
    elif row_count is not _UNSET:
        data["masthead"]["row_count"] = row_count
    for asset in data["assets"]:
        asset["path"] = str((BASE_INSTITUTION_DESIGN_FIXTURE.parent / asset["path"]).resolve())
    path = tmp_path / "design.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _masthead_table(section_root: ET.Element) -> ET.Element:
    tables = section_root.findall(f".//{{{_NS['hp']}}}tbl")
    return tables[0]  # masthead는 항상 generate_source_hwpx()가 만드는 첫 번째 표다.


def _cell_widths_and_texts(masthead: ET.Element) -> tuple[list[int], list[str]]:
    cells = masthead.findall(f".//{{{_NS['hp']}}}tc")
    widths = [int(cell.find(f"{{{_NS['hp']}}}cellSz").get("width")) for cell in cells]
    texts = ["".join(t.text or "" for t in cell.iter(f"{{{_NS['hp']}}}t")) for cell in cells]
    return widths, texts


def _pics_per_cell(masthead: ET.Element) -> list[int]:
    cells = masthead.findall(f".//{{{_NS['hp']}}}tc")
    return [len(cell.findall(f".//{{{_NS['hp']}}}pic")) for cell in cells]


def test_masthead_title_column_constant_no_longer_exists() -> None:
    assert not hasattr(hwpx_template_authoring, "_MASTHEAD_TITLE_COLUMN"), (
        "masthead column ownership must come from resolved.masthead.slots, "
        "not a module-level Python constant"
    )


def test_unchanged_slots_order_still_produces_logo_title_logo_regression(tmp_path: Path) -> None:
    design_path = _write_design_with_slots(tmp_path, ["logo_left", "title", "logo_right"])
    spec = load_template_spec(FIXTURE)
    resolved = resolve(design_path, spec)
    assert resolved.masthead is not None
    assert resolved.masthead.row_count == 1
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")

    with zipfile.ZipFile(source_hwpx) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
    masthead = _masthead_table(section_root)

    assert masthead.get("rowCnt") == "1"
    assert masthead.get("colCnt") == "3"
    widths, texts = _cell_widths_and_texts(masthead)
    assert texts == ["", "주간업무보고서", ""]
    pics = _pics_per_cell(masthead)
    assert pics == [1, 0, 1]
    # 왼쪽/오른쪽 로고 칸(34mm)이 가운데 문서명 칸(102mm)과 같은 폭이 아니다.
    assert widths[0] == widths[2]
    assert widths[1] != widths[0]


def test_reordered_slots_actually_move_title_and_logo_columns(tmp_path: Path) -> None:
    # title을 맨 앞으로, 로고 둘을 뒤로 미룬 순서 — 이런 배치는 baseline/실제
    # 기관 evidence로 뒷받침되지 않으므로 실제 institution design으로
    # 채택하지 않는다(이 task의 범위 밖). 여기서는 오직 "authoring이 선언된
    # 순서를 실제로 읽어 materialize하는가"만 증명하기 위한 최소 반례다.
    design_path = _write_design_with_slots(tmp_path, ["title", "logo_left", "logo_right"])
    spec = load_template_spec(FIXTURE)
    resolved = resolve(design_path, spec)
    assert resolved.masthead is not None
    assert resolved.masthead.slots == ("title", "logo_left", "logo_right")
    source_hwpx = generate_source_hwpx(resolved, tmp_path / "source.hwpx")

    with zipfile.ZipFile(source_hwpx) as package:
        section_root = ET.fromstring(package.read("Contents/section0.xml"))
    masthead = _masthead_table(section_root)

    widths, texts = _cell_widths_and_texts(masthead)
    # 문서명이 이제 0번 칸(왼쪽 로고칸이 아니라)에 있다 — 기존 고정 위치
    # (_MASTHEAD_TITLE_COLUMN=1) 가정이 사라졌다는 직접 증거.
    assert texts == ["주간업무보고서", "", ""]
    pics = _pics_per_cell(masthead)
    assert pics == [0, 1, 1]
    # 폭도 role을 따라 함께 옮겨간다 — title_slot_width_mm(102mm)이 이제
    # 0번 칸 폭이다.
    assert widths[0] != widths[1]
    assert widths[1] == widths[2]


def test_masthead_requires_slots_declaration_end_to_end(tmp_path: Path) -> None:
    design_path = _write_design_with_slots(tmp_path, None)
    spec = load_template_spec(FIXTURE)

    with pytest.raises(HwpxAuthoringResolveError, match="slots"):
        resolve(design_path, spec)


def test_masthead_requires_row_count_declaration_end_to_end(tmp_path: Path) -> None:
    design_path = _write_design_with_slots(
        tmp_path, ["logo_left", "title", "logo_right"], row_count=None
    )
    spec = load_template_spec(FIXTURE)

    with pytest.raises(HwpxAuthoringResolveError, match="row_count"):
        resolve(design_path, spec)
