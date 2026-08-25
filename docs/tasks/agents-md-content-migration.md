# Task: root AGENTS.md content migration

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only:

- the information placement and duplication of the root `AGENTS.md`;
- the destination documents named in the migration plan below
  (`README.md`, `docs/agent-policies/task-scoped-testing.md`,
  `docs/agent-policies/hwpx-layout-context.md`,
  `docs/contracts/template-authoring-contracts.md`, and the new
  `docs/agent-policies/work-unit-execution.md`); and
- the minimum consistency fix in a destination when the migration exposes an
  actual factual inconsistency.

## Prohibitions

- Do not change `TEMPLATE_CREATE` / `DOCUMENT_RENDER` workflow meaning.
- Do not redesign the Product/Workflow Contract.
- Do not change Semantic Contract, Institution Design, or TemplateSpec
  responsibilities.
- Do not change runtime behavior, code, schemas, or tests.
- Do not add a new capability, option, or CLI.
- Do not weaken an existing test expectation.
- Do not perform unrelated documentation cleanup.
- Do not reset, revert, check out, or delete the user's unrelated working-tree
  changes.
- Do not overwrite or delete `docs/tasks/agents-governance-maintenance.md`.
- Do not commit or push.

## Goal

Keep in the root `AGENTS.md` only the project-level invariants and routing
rules every coding agent must always read. Move or merge operational detail,
historical regression notes, contract detail, and testing detail into the
document that already owns the subject.

The goal is not line-count reduction. All of the following must hold:

1. No rule removed from root is lost.
2. Every rule has one clear authoritative owner.
3. Multi-copy duplication of the same rule is reduced.
4. Stale operational documentation is removed from root.
5. Root tells an agent which detailed document to read.
6. Existing project/workflow semantics are preserved.

## Authoritative migration plan

This plan is the completed read-only audit's result and is authoritative. It is
not re-classified by this task.

| Root section | Verdict | Destination |
|---|---|---|
| `Project goal` | KEEP (condensed) | root; detail in `docs/product-workflow-contract.md` |
| `Absolute prohibitions` | KEEP | root |
| `Dependencies` | MERGE | `README.md` §1 |
| `Implementation scope` | KEEP | root |
| `Test and build requirements` | MERGE | `docs/agent-policies/task-scoped-testing.md` |
| `해결된 회귀` | MOVE | `docs/agent-policies/hwpx-layout-context.md` |
| `Commands` | MOVE | `README.md` 운영 매뉴얼 |
| `Documentation changes` | KEEP | root |
| `Work-unit execution contract` | SPLIT | root reading order; detail to `docs/agent-policies/work-unit-execution.md` |
| `response` | KEEP + move to top | root |
| `Contract interpretation` | MERGE | `docs/contracts/template-authoring-contracts.md` |
| `Concurrent work` | KEEP | root |
| `Relevant verification` | MERGE | `docs/agent-policies/task-scoped-testing.md` |

## Factual inconsistencies in scope

- `C-1`: the root `Commands` block is stale relative to `scripts/templates/`.
  It is removed, not expanded into a CLI catalog. `scripts/AGENTS.md` already
  owns the script catalog; `README.md` owns operational commands.
- `C-2`: `Project goal` recognizes a self-authored `TEMPLATE_CREATE` entry
  path that the operational documentation never showed. `README.md` is
  corrected to state both normal entry paths using the current
  `scripts/templates/author_hwpx_template.py` source of truth. No workflow or
  CLI is designed or changed.

## Completion criteria

1. Every row of the migration plan is applied.
2. Every moved/merged rule's meaning exists in its destination.
3. Root `AGENTS.md` has no dangling reference; every changed local link exists.
4. No detail moved to a destination is re-duplicated in root.
5. `docs/agent-policies/work-unit-execution.md` exists and is referenced from
   root.
6. `Project goal` still states `TEMPLATE_CREATE`, `DOCUMENT_RENDER`, both
   `TEMPLATE_CREATE` entry paths, and the not-a-format-converter boundary.
7. The user's unrelated working-tree changes are preserved.
8. `docs/agent-policies/documentation-migration-safety.md` verification is
   performed and reported.

## Migration record

Per `docs/agent-policies/documentation-migration-safety.md` §Required
Completion Report.

```text
Source:
- AGENTS.md: Dependencies, Test and build requirements, 해결된 회귀, Commands,
  Work-unit execution contract, Contract interpretation, Relevant verification,
  response, Project goal

Destination:
- README.md: 1. 실행 환경 준비 (submodule 표), 3-2. 요구사항과 계약으로 직접 작성,
  7. 저장소 검증 (CI 명령)
- docs/agent-policies/task-scoped-testing.md: 실행 순서 규칙, ## Relevant verification
- docs/agent-policies/hwpx-layout-context.md: 5장 표 셀 leading fwSpace 절
- docs/contracts/template-authoring-contracts.md: ## Interpretation rules
- docs/agent-policies/work-unit-execution.md: 신규 파일 전체

Moved:
- submodule 부재 시의 결과 두 건 -> README 표의 `없을 때` 열
- 테스트 실행 순서(초점 -> 직접 영향 -> 전체) -> testing policy
- HWPX 조건부 검증 목록 7건 -> testing policy `## Relevant verification`
- text_node_index 단위 복원으로 해소된 회귀 사실 -> layout-context 5장
- 계약 간 추론 금지, resolved 값 밖 visual value 금지, invalid declaration
  fail-fast, FIXED/CONTENT·canonical path·cardinality·requiredness 재해석 금지
  -> template-authoring-contracts `## Interpretation rules`
- PRESERVE/REVISE, BLOCKER/FOLLOW-UP/OUT_OF_SCOPE, task 적용 범위 목록,
  DONE 기준 -> work-unit-execution.md

Removed:
- root의 PowerShell/Bash 설치·렌더·QA·등록 명령 블록: README 운영 매뉴얼이 이미
  동일 명령을 더 완전하게 소유한다 (root 쪽이 stale했다).
- "신규 테스트 최소 하나" 규칙: task-scoped-testing.md 5-6행과 동일.
- "실행한 검증 명령과 결과를 실패·경고까지 보고" 규칙: 같은 문서 17-23행과 동일.
- "관련 테스트 실패 시 검증됨/사용 가능/완료 금지": 같은 문서 14행과 동일.
- "회귀 시 기대값을 바꾸지 말고 렌더러를 고친다": 같은 문서 9·12행과 동일.
- "baseline은 관찰 evidence": template-authoring-contracts.md `### Institution
  Design Contract`와 product-workflow-contract.md invariant 6에 이미 존재.

References updated:
- AGENTS.md (README, scripts/AGENTS.md, work-unit-execution.md 포인터 추가)

Verification:
- destination file exists: 검증됨 (링크 25건 전부 해석됨)
- changed local references resolve: 검증됨
- no orphaned documents: work-unit-execution.md는 root AGENTS.md가 참조
- no unintended files or directories: 신규 파일 2개 외 없음
- no duplicate source of truth: root에서 이동한 상세 규칙의 root 잔존 없음
```

## Follow-up (not in this task's scope)

- `scripts/templates/render_hwpx_template_from_source.py`는 `scripts/AGENTS.md`가
  이미 소유하지만 README 운영 매뉴얼에는 없다. DOCUMENT_RENDER의 source 입력
  경로를 README에 문서화할지는 별도 판단이 필요하다.
- `scripts/templates/check_native_page_count.py`는 `docs/hancom-native-page-validation.md`가
  소유하는 진단 도구이며 `scripts/AGENTS.md` 표에는 없다.
- README `6. Python API`는 "공개 API는 다음 네 함수입니다"라고 하지만
  `core/document_api/__init__.py`의 `__all__`은 `render_document_from_source`를
  포함해 다섯 함수를 공개한다. 이 절은 이번 migration의 destination이 아니므로
  수정하지 않았다.
