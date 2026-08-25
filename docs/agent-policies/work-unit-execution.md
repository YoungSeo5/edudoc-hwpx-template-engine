# Work-Unit Execution Policy

Root `AGENTS.md` requires an explicit task contract for every scoped task and
defines the required reading order. This policy owns the detailed rules for
task-contract authority, scope limits, and issue classification.

## Applies to

Every scoped project task, including:

- investigation and analysis
- planning
- E2E or architecture changes
- contract and schema changes
- documentation changes
- implementation
- testing
- migration

## Task contract authority

The active task contract MUST declare its authority over the parent system
contract. A task must state one of these:

- `PRESERVE`: the parent E2E/system contract must not be changed.
- `REVISE`: the task may revise explicitly named portions of the parent
  E2E/system contract.

`REVISE` does not permit unrestricted redesign. The task contract must name
the exact workflow, sections, decisions, or boundaries it is allowed to
change.

## Issue classification

When work discovers a new issue, classify it as:

- `BLOCKER`: required to satisfy the current task's completion criteria.
- `FOLLOW-UP`: valid issue, but not required to complete the current task.
- `OUT_OF_SCOPE`: unrelated to the current task.

Do not automatically expand the current task because a new issue was found.

If a discovered issue proves that the active task contract itself is wrong or
incomplete, stop only the affected work, record the issue, revise the task
contract with human approval, and then continue.

An open issue in `docs/product-workflow-contract.md` is not automatically a
`BLOCKER` for every task.

## Completion

A task is DONE when its declared completion criteria are satisfied.
Remaining `FOLLOW-UP` items do not prevent the task from closing.
