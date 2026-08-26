# Task: hierarchy projection reference alignment

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the self-authored `one_page_report` hierarchy
prototype selections and their source/candidate-roundtrip projection. It preserves
paragraph spacing, DOCUMENT_RENDER, native PageCount handling, approval and
registration, and protected template packages.

## Evidence

The common observed hierarchy is `□ → ㅇ/◦ → -`
(`docs/hwpx-layout-baseline.md`, lines 189–212). The approved FSS reference
contains both `hp:case` and `hp:default` branches under `hp:switch`. Hancom
native layout uses the `hp:case` margin values: `-2240`, `-2990`, and `-4410`
for the `□`, `◦`, and `*` prototypes. Each `hp:default` value is exactly twice
the corresponding `hp:case` value (`-4480`, `-5980`, `-8820`), which caused
the earlier evidence and self-authored projections to record the wrong branch.
A section heading already owns the `□` level, while the self-authored
TemplateSpecs select the `◦` and `*` reference prototypes for their first and
second children. Their native intents therefore use the same `hp:case` source:
`-2990` and `-4410`.

## Completion criteria

1. A newly added regression fails before the fix and checks the whole heading
   plus child-prototype progression, rather than child prototypes in isolation.
2. The first and second hierarchy children select the existing `◦` and `*`
   reference prototypes without marker repetition.
3. Source and candidate round-trip HWPX preserve the same marker and native
   indentation prototype values.
4. A fresh sandbox candidate is created without approval or registration.

## Issue classification

- `BLOCKER`: hierarchy children start at the same `□` prototype already owned
  by the section heading.
- `BLOCKER`: the prior generic body left-indent projection does not match the
  native reference hierarchy prototypes.
- `BLOCKER`: candidate hierarchy metadata records a source layout prefix as a
  renderer-added marker prefix, duplicating its leading spaces on round-trip.
- `OUT_OF_SCOPE`: paragraph spacing and native PageCount availability.
