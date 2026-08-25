# Task: hierarchy paragraph spacing reference verification

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only
`templates/institutions/edudoc/_design/design.json`'의
`defaults.styles.one_page_body.spacing_after_pt`, and only when an
authoritative stored reference HWPX directly establishes a different hierarchy
paragraph `margin.next` value.

## Scope

Identify the stored reference or baseline artifact that was actually used for
the edudoc one-page Institution Design. Compare its section-heading and
hierarchy paragraphs' `paraPrIDRef`, margin `prev`/`next`, and `lineSpacing`
with the current business-status candidate. Do not infer a value from visual
appearance or from a non-authoritative family sample.

## Completion criteria

1. Establish whether an authoritative reference exists for this exact design
   decision.
2. If it has `margin.next=600`, preserve code and Institution Design.
3. If it has a different explicit value, add a failing resolve regression,
   revise only the named design value, and verify a fresh source and roundtrip
   candidate retain marker, indentation, and native intent values.
4. If no authoritative reference exists, report that fact without modifying
   code or Institution Design.

## Issue classification

- `BLOCKER`: an authoritative reference proves a different hierarchy
  paragraph-spacing value.
- `OUT_OF_SCOPE`: line spacing, markers, indentation, literal spacing, native
  PageCount, renderer behavior, and protected template packages.
