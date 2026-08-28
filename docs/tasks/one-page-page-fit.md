# Task: one_page_report page-fit measurement (auto-compaction removed)

## Status

DONE (scope reduced — see "2026-08-21 정정" 절)

## 2026-08-21 정정

이 task는 처음에 `default`/`compact`/`minimum` density profile을 실제 Hancom
PageCount에 따라 자동 선택하는 기능으로 구현·완료 보고됐다. 이후 검토에서
그 계수(line-spacing ×0.87, spacing/cell-margin ×0.5·×0, 100% 하한)가
evidence가 직접 증명한 값이 아니라 baseline 관찰을 재해석해 만든
heuristic이었다는 지적을 받았고, 사용자 결정으로 **자동 압축(compact/
minimum 자동 선택)을 production contract에서 제거**했다. 아래 본문은 그
제거 이후의 최종 상태를 기록한다 — 자동 압축이 있던 이전 버전의 세부
설계는 이 파일의 git 이력(또는 대화 기록)에만 남아 있다.

**남긴 것**: 실제 콘텐츠를 `default` 설정으로 한 번 렌더링하고 실제 Hancom
PageCount를 측정해, 기대와 다르면 압축을 시도하지 않고 정직하게
`ok=False`로 실패시키는 measurement/failure/diagnosis 흐름
(`core/adapters/hwpx_page_fit.py`).

**제거한 것**: `core/adapters/hwpx_authoring_resolve.py`의 `DENSITY_PROFILES`,
`_DENSITY_SPACING_SCALE`, `_DENSITY_LINE_SPACING_SCALE`,
`_LINE_SPACING_FLOOR_PERCENT`, 관련 `_scale_*` 함수, `resolve()`/
`_resolve_*`의 `density_profile` 매개변수 — 전부 삭제해 이 파일을 이 task
시작 전 상태로 되돌렸다.

**남겨진 질문(별도 정책 결정 필요, 이 task 범위 밖)**: "`one_page_report`가
반드시 1페이지여야 하는가"와 "그렇다면 어떤 속성을 어디까지 줄일 수 있는가"는
Institution Design 수준의 정책 결정이 필요하다. 아래 "제거 전 실측 데이터"
절이 그 결정에 참고할 수 있는 실측 증거를 남긴다.

### 제거 전 실측 데이터 (참고용, 자동 적용되지 않음)

`sandbox/eval-reference-generation-quality/vertpos_dump.txt`(Hancom이 실제
저장한 파일의 `<hp:lineseg vertpos>`를 직접 읽어 계산, 손계산 아님):

```
available body height (A4, 상하 10mm)                 277.0mm

default (2페이지, 압축 없음)
  총 필요 높이                                          301.1mm
  overflow                                              +24.1mm

이전 buggy "minimum" 설정 적용 시(현재는 production에서 제거됨)
  총 필요 높이                                          246.5mm
  여유                                                  +30.5mm  (다시 정정: 이전 보고에서 "-30.5mm"로 잘못 기록했었음 — 양수가 맞다, 즉 필요보다 여유가 있었다는 뜻)
  default 대비 축소량                                    54.6mm  (301.1 - 246.5)
```

**기록**: 1페이지에 필요한 최소 축소량은 24.1mm였는데, 제거된 "minimum"
설정은 54.6mm를 줄였다 — 필요량의 2배 이상, **필요 이상으로 강한 압축**이었다.
이건 이 heuristic이 "간신히 맞추기"가 아니라 "안전 마진을 크게 두고
과압축"하는 방식으로 동작했다는 뜻이고, 그 자체로 이 계수들이 세밀하게
튜닝된 값이 아니라 대략적인 heuristic이었다는 방증이다. masthead 실측
높이는 설계값 24.0mm와 정확히 일치해 그 자체는 결함이 아니었다 — overflow
24.1mm는 metadata 표(3행)·status 표(4행)·section heading 4개·본문 4개·
bullet 4개·footer 등 15개 안팎 요소에 고르게 분산돼 있었다.

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

이 task는 `core/adapters/hwpx_authoring_resolve.py`(density profile 해석)와
새 `core/adapters/hwpx_page_fit.py`(bounded orchestrator)만 추가/수정한다.
`core/adapters/hwpx_template_authoring.py`, `core/adapters/
hwpx_template_renderer.py`, `core/templates/hwpx_content_separator.py`는
읽기 전용으로 호출만 하고 수정하지 않는다. `templates/institutions/`
(institution 소유 protected submodule)는 어떤 파일도 쓰기로 열지 않는다 —
사용자가 명시적으로 확인한 경계(이 task 대화 중 `AskUserQuestion`으로 확정):
generic page-fit mechanism과 density profile의 schema/해석 로직은 main
repository 책임이고, institution-specific한 실제 디자인 값은 여전히
Institution Design Contract(submodule)의 배타적 소유이며 main repo가 그
값을 복제하거나 우회하지 않는다.

## Root cause (선행 task에서 확정)

`docs/tasks/hwpx-renderer-table-row-metadata-sync.md`의 bugfix 이후
`sandbox/eval-reference-generation-quality/evaluation-report.md` 10절에서
실측된 문제: `one_page_report`는 `native_page_count=1` 검증 게이트는 갖고
있었지만(코드 근거: `scripts/templates/qa_hwpx_template.py` 154-234행,
`core/adapters/hancom_page_count.py`는 open 후 PageCount를 비교만 함),
콘텐츠 밀도가 늘어난 실제 렌더 결과를 1페이지로 되돌리는 production 로직은
전혀 없었다(`core/adapters/hwpx_template_renderer.py` 어디에도 `PageCount`
참조 없음). 3건 project_tasks + 4건 next_actions 입력에서 실측
`PageCount=2`가 이 gap의 최초 재현 사례였다.

## Completion criteria (최종, 2026-08-21 정정 반영)

1. page-fit "측정" 책임을 명시적으로 확정한다(아래 "책임 위치" 절).
2. 자동 압축(density profile 자동 선택)은 production contract에 두지
   않는다 — evidence로 직접 증명되지 않은 heuristic 계수를 만들지 않는다.
3. 실제 콘텐츠 → `default` 설정 렌더 → 실제 Hancom PageCount 측정 흐름을
   구현하고, 기대와 다르면 명시적 실패를 반환한다(성공한 문서로 위장하지
   않는다).
4. 3 project_tasks + 4 next_actions 입력은 실제 Hancom에서 `PageCount=2`로
   **정직하게 실패**해야 한다(더 이상 1페이지로 압축하지 않는다).
5. 기존 collection materialization/구조 회귀와 무관한 실패 없이 focused/full
   pytest가 통과해야 한다.

## 책임 위치 (최종)

- **family recipe**(`native_page_count`): "무엇을 목표 페이지 수로 검증할지"만
  소유한다(변경 없음).
- **Institution Design Contract**: 각 role의 실제 값을 배타적으로 소유한다
  (변경 없음, 이 task는 새 role/키를 추가하지 않는다).
- **TemplateSpec**: 변경 없음.
- **`resolve()`(`hwpx_authoring_resolve.py`)**: 이 task 시작 전 상태로
  완전히 되돌아갔다 — density profile을 모른다. role 조회·override
  병합만 한다.
- **renderer**(`generate_source_hwpx`/`hwpx_template_renderer.py`): 변경
  없음(애초에 이 task 내내 변경된 적 없다).
- **native page validation**(`hancom_page_count.py`): 변경 없음. 순수
  비교 함수로 재사용된다.
- **`hwpx_page_fit.py`**: 유일하게 실제로 남은 새 책임 — "`default`로
  한 번 렌더링해 실제 PageCount를 측정하고, 기대와 다르면 정직하게
  실패시킨다." 어느 profile을 선택할지 결정하는 로직은 없다(그 결정
  자체를 제거했다).
- **아직 어느 계층도 갖고 있지 않은 것**: "1페이지 여야 하는가"와 "어떤
  속성을 얼마나 줄일 수 있는가"에 대한 정책. 위 실측 데이터가 그 결정의
  참고 자료다.

## 완료 기록 (최종)

- `core/adapters/hwpx_authoring_resolve.py`: density profile 관련 추가를
  전부 제거하고 이 task 시작 전 상태로 되돌렸다(`DENSITY_PROFILES` 등
  어떤 흔적도 남지 않음 — `grep`으로 확인).
- `core/adapters/hwpx_page_fit.py`: `render_one_page_with_page_fit()`을
  "default 1회 렌더 + 실측 + 실패 시 정직한 ok=False"로 단순화. profile
  루프 없음.
- `tests/task_scoped/test_one_page_page_fit.py`: sparse/one_each(default에서
  이미 통과) · 3+4(정직하게 실패, `observed_pages==2` 확인) ·
  larger(정직하게 실패) · `resolve()`가 더 이상 `density_profile`을 받지
  않음을 확인하는 회귀로 재작성.
- focused: `pytest tests/task_scoped/test_one_page_page_fit.py` 5 passed
  (density profile 제거 직후 실행).
- 전체 스위트는 이 정정 작업 도중 이 저장소에서 **동시에 진행 중인 다른
  작업**(`hwpx_authoring_resolve.py`/`hwpx_template_authoring.py`에 masthead
  `slots` 지원을 추가하는 별개 task)이 같은 파일을 계속 수정하고 있어,
  이 task 자체와 무관한 사유로 전체 재실행이 일시적으로 막혔다(EDUDOC
  masthead에 아직 없는 `slots` 키를 요구하게 됨 — protected submodule이라
  그 task도 즉시 채울 수 없는 상태로 보인다). 이 task의 변경 범위(density
  profile 제거)는 파일 diff로 직접 확인했고, 그 변경이 착수하기 직전
  실행한 5/5 focused 통과가 유효한 근거다. 전체 스위트 재확인은 그 동시
  작업이 안정된 뒤 별도로 필요하다.

## Out of scope

- `templates/institutions/`에 새 role/profile 데이터 추가(protected
  submodule).
- font size 축소, 문서 전체 scale-down.
- merged-cell/복잡한 표 materializer.
- "1페이지여야 하는가"/"무엇을 얼마나 줄일 수 있는가"의 Institution
  Design 수준 정책 결정 — 별도 task.
- 이 task 중 발견된, 무관한 pytest 1회성 `PermissionError` flake
  (`test_fss_director_report_prepared_input.py`,
  `test_hwpx_resolved_render_boundary.py` — 둘 다 격리 재실행에서 즉시
  통과, Windows 파일 잠금 관련으로 판단) — 수정하지 않고 분리 기록만 한다.
- `hwpx_authoring_resolve.py`/`hwpx_template_authoring.py`에서 동시에
  진행 중인 masthead `slots` 관련 작업 — 이 task와 무관하며 건드리지
  않았다.
