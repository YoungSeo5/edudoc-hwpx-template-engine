# Task: hierarchy paragraph spacing calibration candidates

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

## Scope

Generate three unapproved self-authored business-status candidates in
`sandbox/template-candidates/`. Each candidate uses a sandbox copy of the
current edudoc Institution Design and changes only
`one_page_body.spacing_after_pt`: 8, 10, or 12. Preserve all repository code,
tests, schemas, protected packages, and the actual Institution Design.

## Completion criteria

1. Each candidate has a generated `roundtrip.sample.hwpx`.
2. Each roundtrip has the selected hierarchy `margin.next` value.
3. Marker progression, child left margins, native intents, literal marker
   spacing, and line spacing are unchanged from the current design.
4. Native PageCount unavailability does not fail this calibration-only task.

## Issue classification

- `BLOCKER`: a candidate cannot be generated through the normal self-authored
  workflow.
- `OUT_OF_SCOPE`: choosing a final spacing value, changing the actual Design,
  code, tests, schema, approved packages, native PageCount, and any layout
  other than hierarchy paragraph spacing.
