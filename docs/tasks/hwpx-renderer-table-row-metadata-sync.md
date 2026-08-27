# Task: HWPX renderer table-row metadata sync bug fix

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

이 task는 `core/adapters/hwpx_template_renderer.py`의 table-row collection
materialization(`_materialize_collection_table_rows` 및 그 보조 함수)만 수정할
수 있다. 다른 렌더링 경로(hierarchy_paragraph collection, table_cell 위임,
metadata/alias 처리 등), TEMPLATE_CREATE/DOCUMENT_RENDER 계약, 승인 semantics,
기존 승인 템플릿, 두 protected submodule은 변경하지 않는다. 이 task는
`docs/tasks/reference-based-generation-quality-evaluation.md` 평가 중 발견된
결함을 사용자의 명시적 지시로 별도 처리하는 것이다.

## Root cause

`docs/hwpx-layout-baseline.md`가 아니라 이번 평가에서 직접 확보한 실측 증거:

- 실제 reference HWPX(예: 금감원 원장보고, 원페이지)의 모든 `<hp:tbl>`에서
  `rowCnt` 속성은 항상 실제 `<hp:tr>` 개수와 정확히 같고, 각 행의 모든
  `<hp:tc><hp:cellAddr rowAddr=".."/>`는 그 행의 0-indexed 위치와 정확히
  일치하며 행 사이에 공백/중복이 없다 — 예외 없이 관찰된 invariant.
- `_materialize_collection_table_rows()`(`core/adapters/
  hwpx_template_renderer.py`)는 collection 값 개수(N)에 맞춰 실제
  `<hp:tr>`을 정확히 늘리거나 줄이지만, 표 prototype에서 가져온 `rowCnt`
  속성과 각 복제 행이 그대로 물려받은 `rowAddr`은 갱신하지 않았다. 그 결과
  N이 prototype 원래 행 수(예: 2)와 다르면(0/1/N 어떤 방향이든) `rowCnt`가
  실제 행 수와 어긋나고, 복제된 모든 행이 동일한 `rowAddr`을 공유한다.
- `hwpx.validate_package()`(strict/zip validator)는 이 불일치를 검사하지
  않아 통과하지만, 실제 한/글(Hancom Automation, `HWPFrame.HwpObject`)은
  이런 파일을 열 때 "파일이 손상되었습니다"로 거부한다 — COM
  `Open()` 자체가 `False`를 반환하며 실측 재현됨.

## Completion criteria

1. `rowCnt`와 각 행의 `rowAddr`이 실제 `<hp:tr>` 구조와 항상 일치하도록
   `_materialize_collection_table_rows()`을 최소 범위로 수정한다. prototype의
   원래 행 수를 collection cardinality의 상한으로 취급하지 않는다(0/1/prototype과
   동일/prototype 초과 모두 지원).
2. 기존 collection materialization 회귀 테스트
   (`tests/task_scoped/test_self_authored_collection_runtime.py`)에 이
   구조 invariant 검증을 추가하고, prototype 행 수 대비 적음/동일/많음 세
   경우를 모두 parametrize한다. 수정 전 코드에서 새 assertion이 실패함을
   확인한 뒤 수정을 적용해 통과시킨다.
3. 이번 평가에서 실패했던 원본 3-item 시나리오
   (`sandbox/eval-reference-generation-quality/content.eval.json`)를 같은
   candidate로 다시 렌더링하고, 실제 Hancom Automation으로 open 성공·
   PageCount·저장 후 재오픈까지 확인한다. strict/package validation 통과만으로
   완료로 보고하지 않는다.
4. `tests/task_scoped/` 전체와 전체 `pytest tests/`를 실행해 무관한 회귀가
   없음을 확인한다.

## Out of scope

- `hp:sz`(표 전체 높이) 등 다른 잠재적 stale 필드에 대한 추측성 재계산.
  실측 결과 실제 reference들도 `hp:sz.height`가 행 높이 합과 정확히 일치하지
  않는 경우가 있어(반올림/테두리 차이로 추정, 원인 확정하지 않음) 이번
  task에서 하드 invariant로 취급하지 않는다. 수정 후 실제 Hancom open이
  성공하는지로 이 판단의 충분성을 검증한다.
- merged cell(rowSpan/colSpan > 1) 지원 — 현재 시스템에 복잡한 테이블
  materializer가 없다는 기존 계약을 그대로 따른다(신규 capability 아님).
- hierarchy_paragraph collection 경로 — 표가 아니므로 이 invariant와 무관하고
  이번 평가에서 결함이 관찰되지 않았다.

## Evidence

- `sandbox/eval-reference-generation-quality/evaluation-report.md` 6·8절 —
  최초 발견 경위와 구조 실측.
- 실물 reference 표 실측(`templates/institutions/금융감독원/{금감원 원장보고,
  금감원 원페이지}/source.hwpx`) — `rowCnt`/`rowAddr` invariant의 근거.
