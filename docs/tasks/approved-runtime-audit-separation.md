# Task: approved runtime / audit separation

## Status

COMPLETE

> **2026-08-27 정정**: 이 task가 선택한 audit 경로(`templates/audit/<template_id>/`,
> registry_root 밖 public superproject 내부)는 registry_root가 private
> submodule일 때 private institution artifact를 public repo로 유출하는 P0
> 결함으로 확인되어, 후속 commit(`fix: keep registration audit artifacts
> private`)에서 `<registry_root>/_audit/<template_id>/`(registry_root 내부)로
> 교체됐다. 이 문서의 나머지 서술은 그 시점의 설계 기록으로 남긴다.

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

이 task는 승인 등록 시 candidate artifact를
`templates/institutions/<institution>/<document_type>/`의 DOCUMENT_RENDER
runtime artifact와 `templates/audit/<template_id>/`의 승인 evidence로 분리하는
저장 경계만 수정한다.

## Scope

- candidate의 기존 QA, human approval, strict/renderability 검증을 먼저 수행한다.
- Task 1-A에서 확정한 runtime artifact만 approved 경로에 보존한다.
- 나머지 candidate evidence는 audit 경로에 원래 상대 경로로 보존한다.
- 등록 확인 성공 후에만 candidate를 제거한다.

## Out of scope

- `source.hwpx` 또는 `template/` 제거·통합
- renderer, placeholder map, semantic classification 구조 변경
- 기존 approved template migration
- hierarchy 또는 visual fidelity 변경

## Completion criteria

1. approved에는 runtime artifact만 존재한다.
2. audit에는 approved에서 제외된 evidence가 보존된다.
3. QA와 human approval 검증은 분리 전에 그대로 수행된다.
4. 등록된 approved template의 identity, strict render, native PageCount 계약이 유지된다.
5. focused 및 전체 pytest가 통과한다.
