# Task: AGENTS governance maintenance

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the root `AGENTS.md` sections required to resolve:

- the duplicated `Project goal` conflict; and
- the active task-contract path from `tasks/` to `docs/tasks/`.

## Prohibitions

- Do not modify any other `AGENTS.md` rule.
- Do not modify an existing task contract.
- Do not remove or move items identified as KEEP, MOVE CANDIDATE, or EXACT DUPLICATE.
- Do not change code or tests.

## Completion criteria

1. Root `AGENTS.md` has one `Project goal` section consistent with the current
   `TEMPLATE_CREATE` and `DOCUMENT_RENDER` E2E contract.
2. The root active task-contract path is `docs/tasks/`.
3. No other active task-contract-location reference is changed; any additional
   incorrect reference is reported only.
