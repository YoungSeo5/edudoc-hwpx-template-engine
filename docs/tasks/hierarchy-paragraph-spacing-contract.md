# Task: hierarchy paragraph spacing contract

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

## Scope

Trace only self-authored business-status hierarchy paragraph spacing from
TemplateSpec through resolve and source/candidate round-trip HWPX. Change
runtime code only if a declared spacing value differs from its materialized
`margin.prev` or `margin.next` value. Preserve hierarchy markers, literal
spacing, left margin, native intent, line spacing, and native PageCount
behavior.

## Completion criteria

1. Identify the canonical owner of hierarchy `spacing_before_pt` and
   `spacing_after_pt`, or report that it is not declared.
2. Compare the declared resolved values with source and round-trip margins.
3. Do not change code when the current materialized values match the contract.

## Issue classification

- `BLOCKER`: only a mismatch between declared hierarchy paragraph spacing and
  source/round-trip HWPX margins.
- `OUT_OF_SCOPE`: line spacing, marker/indent geometry, and native PageCount.
