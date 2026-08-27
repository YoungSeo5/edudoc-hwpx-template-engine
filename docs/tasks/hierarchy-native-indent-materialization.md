# Task: hierarchy native-indent materialization

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

## Scope

Correct only the self-authored `TEMPLATE_CREATE` authoring path where a
resolved hierarchy paragraph has both the Institution Design Contract's
`indent_left_mm` and the TemplateSpec-selected `native_intent_hwpunit`.
The HWPX paragraph format must materialize both resolved values. This task
does not change TemplateSpec values, layout policy, candidate QA,
DOCUMENT_RENDER, approval/registration, templates, or submodules.

## Evidence

The business-status one-page TemplateSpec selects hierarchy intents `-2990`
and `-4410`. Its resolved `body_style.indent_left_mm` is `5.0`, but the
authoring branch that applies a native intent writes HWPX `margin.left=0`.
The source and rendered HWPX retain that same value, so this is a source
authoring materialization defect rather than a rendering defect.

## Completion criteria

1. A newly added focused regression test fails before the fix and proves that
   a hierarchy paragraph with native intent retains the resolved left indent.
2. The minimal authoring change preserves the existing resolved left indent
   while retaining the TemplateSpec-selected native intent.
3. Focused regressions pass.
4. A fresh self-authored sandbox candidate confirms the two hierarchy
   paragraphs have materialized non-zero left margins and their existing
   level-specific intent values.

## Issue classification

- `BLOCKER`: the native-intent branch loses the resolved body left indent.
- `FOLLOW-UP`: paragraph spacing is excluded unless the same code path proves
  it is also lost.
