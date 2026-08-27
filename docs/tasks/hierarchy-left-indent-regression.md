# Task: hierarchy left-indent regression

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

## Scope

Restore only the resolved `indent_left_mm` materialization for self-authored
business-status hierarchy paragraphs that also carry a native intent. Preserve
the established `□ → ◦ → *` marker progression, template-owned literal marker
spacing, native intents, paragraph spacing, native PageCount behavior, and
all protected template packages.

## Completion criteria

1. A new business-status E2E regression proves source and round-trip HWPX
   jointly preserve the heading/child marker progression, no duplicate prefix,
   resolved non-zero left indent, and native intents.
2. The authoring path materializes the existing resolved left indent together
   with each hierarchy item's existing native intent.
3. A fresh sandbox candidate has the same marker and geometry values in source
   and `roundtrip.sample.hwpx`.

## Issue classification

- `BLOCKER`: native-intent authoring explicitly overwrites the resolved left
  indent with zero.
- `OUT_OF_SCOPE`: paragraph spacing and native PageCount/security-module QA.
