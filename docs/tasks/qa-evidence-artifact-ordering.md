# Task: QA evidence artifact ordering

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task preserves the lifecycle, digest format, approval checks, and
authoring model. It may change only the ordering that makes final candidate
artifacts available before QA records `candidate_digest`.

## Goal

Ensure QA evidence describes the final candidate artifact set without any
post-QA candidate-digest rewrite.

## Completion criteria

1. No authoring path rewrites `qa.report.json.candidate_digest` after QA.
2. Final candidate snapshots used by digest exist before QA runs.
3. A task-scoped regression fails against the old post-QA rewrite and passes
   with the corrected ordering.

## Scope classification

### BLOCKER

- None initially.

### OUT_OF_SCOPE

- Protected submodules, approval-gate redesign, schema changes, and layout
  changes.
