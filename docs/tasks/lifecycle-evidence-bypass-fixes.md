# Task: lifecycle evidence bypass fixes

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task preserves the current product workflow and authoring structure. It
may change only approval-time checks required to bind machine QA evidence,
human review evidence, and the candidate currently being promoted. It may add
a deterministic candidate digest only if existing runtime artifacts cannot
express that binding.

It must not change baseline evidence, protected submodules, layout/
materialization behavior, semantic required-content policy, or schemas.

## Goal

Reject an approval when QA evidence or human review evidence belongs to a
different candidate, or when the candidate has changed after QA.

## Completion criteria

1. QA evidence records a deterministic identity of the candidate it tested.
2. Approval recomputes that identity and rejects stale or transplanted QA
   evidence.
3. Human review evidence is bound to the same candidate identity and approval
   rejects mismatch.
4. Task-scoped tests reproduce every confirmed bypass and pass after the fix.

## Scope classification

### BLOCKER

- None initially.

### FOLLOW-UP

- Cross-artifact identity validation not already enforced by current runtime.

### OUT_OF_SCOPE

- Protected submodule changes under `skills/hwp-skill/` and
  `templates/institutions/`.
