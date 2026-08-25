# Task: Masthead structural ownership fix

## Status

DONE — masthead `slots` **and** `row_count` declarations added to
Institution Design Contract schema, `resolve()`, and `generate_source_hwpx()`;
`_MASTHEAD_TITLE_COLUMN` and the literal `rows=1`/`cols=3` removed;
`templates/institutions/edudoc/_design/design.json` and
`tests/fixtures/template-contracts/edudoc.institution_design.json` migrated
losslessly (`slots: ["logo_left","title","logo_right"]`, `row_count: 1`, same
effective structure as before). Full `pytest tests/` regression green (344
passed, 1 pre-existing unrelated skip).

**Revision note**: the first pass of this task moved slot order/role to
`masthead.slots` but left `row_count` as a bare Python literal (`rows=1` in
`_add_table()`), reasoning it was a pure capability boundary like
`TemplateSpec._SECTION_TYPES`. On review this was judged incomplete against
the task's own stated scope ("row/column structure" — both, not just
column). `row_count` was then also moved into the contract as a required,
schema-`const`-bounded declaration (still only `1` is accepted; no
multi-row capability was added) — see the amended Goal/Completion criteria
below.

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only how the masthead's **structure** (row count, slot
count, slot left-to-right order, slot role) is declared and consumed:
`docs/contracts/institution-design-contract.schema.json`'s `masthead` shape,
`core/adapters/hwpx_authoring_resolve.py`'s masthead parsing/resolution, and
`core/adapters/hwpx_template_authoring.py`'s masthead materialization. It may
migrate the one existing masthead-declaring design contract
(`templates/institutions/edudoc/_design/design.json`, explicitly approved by
the user for this lossless migration only) and matching test fixtures. It must
not: invent a new masthead visual design, promote any `SINGLE_OBSERVATION`
sub-structure (checkbox status row, banner substructure, multi-row metadata
block) to a component, add institution/family/document-type Python branching,
change scalar/style ownership (width/height/font/color/logo size — these stay
exactly where they already are), touch the exact-source-extraction path, or
change any other protected-submodule file.

## Background / root cause

Prior investigation (`sandbox` conversation, not a separate artifact) found:
the masthead's already-adopted structure — 1 row, 3 columns, `logo-left /
title / logo-right` — is not declared anywhere in the Institution Design
Contract. Only the *width* of each of the three slots is contract-declared
(`logo_left_slot_width_mm`/`title_slot_width_mm`/`logo_right_slot_width_mm`).
Which column is which role is decided by Python: a module constant
`_MASTHEAD_TITLE_COLUMN = 1` in `core/adapters/hwpx_template_authoring.py`,
plus literal column indices `0`/`2` passed to `_materialize_masthead_logo()`
calls, plus a literal `cols=3` and `rows=1` in the `_add_table()` call for the
masthead table. This is not a reference-evidence gap (baseline evidence is not the
issue here) — it is an implementation gap: a structural decision that belongs
to the Institution Design Contract layer is instead owned by authoring code.

## Goal

Move slot **order** and slot **role** (which column is `logo_left`/`title`/
`logo_right`) into the Institution Design Contract as an explicit `slots`
declaration. `resolve()`/`generate_source_hwpx()` must read that declaration
and materialize accordingly instead of assuming a fixed position. Existing
scalar ownership (widths, height, font, color, logo dimensions) is untouched.

Row count is also moved into the contract as an explicit `row_count`
declaration — required whenever a masthead is active, schema-bounded to the
single value (`1`) this authoring version can materialize. That bound itself
(exactly one supported value, and the closed set of supported roles
`logo_left`/`title`/`logo_right`, exactly one each) remains a fixed capability
boundary of this authoring version, analogous to `TemplateSpec`'s fixed
`_SECTION_TYPES` tuple — this task does not add multi-row masthead support.
The difference is that the boundary is now enforced by resolve() validating
an explicit declared value, not by a Python literal silently used regardless
of what (if anything) the contract said.

## Completion criteria

1. `docs/contracts/institution-design-contract.schema.json`'s `masthead`
   shape gains a `slots` array (ordered, each entry one of `logo_left`/
   `title`/`logo_right`, all three required exactly once) and a `row_count`
   field (`const: 1`) — bounded, not an arbitrary grid/DSL.
2. `core/adapters/hwpx_authoring_resolve.py` requires and validates both
   `slots` and `row_count` whenever `masthead.default == "required"`; a
   missing or invalid value for either fails resolve fast — no silent
   recreation of the old fixed 1-row/3-column structure.
3. `core/adapters/hwpx_template_authoring.py` materializes row count, column
   count, order, and per-column role strictly from `resolved.masthead.
   row_count`/`resolved.masthead.slots`; the `_MASTHEAD_TITLE_COLUMN` module
   constant and the literal `rows=1`/`cols=3`/indices `0`/`2` are all
   removed. `build_separation_rules()` derives the title's FIXED column
   from `slots` instead of the removed constant.
4. `templates/institutions/edudoc/_design/design.json` and
   `tests/fixtures/template-contracts/edudoc.institution_design.json` are
   migrated to declare `"slots": ["logo_left", "title", "logo_right"]` and
   `"row_count": 1` — the exact structure already in effect. No other value
   in either file changes.
5. New focused tests prove: (a) missing/invalid `slots` or `row_count` each
   fail resolve fast with no fallback; (b) reordering `slots` in a
   test-only design contract actually changes which column holds the
   title/logo in the generated HWPX (proof that authoring no longer
   hard-codes position); (c) the existing edudoc masthead (unchanged
   `slots`/`row_count`) still generates the exact same 1-row/3-column/
   `logo-title-logo` structure as before this change.
6. Full `pytest tests/` regression passes with no unrelated changes.

## Out of scope

- Any new masthead sub-structure (checkbox row, banner, multi-row metadata) —
  recorded as deferred (`SINGLE_OBSERVATION`), not implemented here.
- Any change to which institutions/candidates exist, their approval status,
  or any other design value (color/font/size/logo asset/width/height).
- A general-purpose grid/layout DSL for masthead or any other component.
- Non-edudoc institutions, other families, or other protected-submodule data.

## Evidence

- `core/adapters/hwpx_template_authoring.py` (`_MASTHEAD_TITLE_COLUMN`,
  `_materialize_masthead()`, `_materialize_masthead_logo()`,
  `_materialize_masthead_title()`, `build_separation_rules()`).
- `core/adapters/hwpx_authoring_resolve.py` (`_MASTHEAD_REQUIRED_WHEN_ACTIVE`,
  `_parse_institution_masthead()`, `_resolve_masthead()`).
- `docs/contracts/institution-design-contract.schema.json` (`masthead`
  shape — currently declares only widths/height/border/logo dimensions, not
  slot order/role).
- `templates/institutions/edudoc/_design/design.json` and
  `tests/fixtures/template-contracts/edudoc.institution_design.json` (the
  only two masthead-`required` design contracts in this repository).
