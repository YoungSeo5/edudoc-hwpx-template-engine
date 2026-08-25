# Task: one-page-report family configurable variants

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the self-authored `TEMPLATE_CREATE` layout-planning
and source-authoring path for the existing `one_page_report` family. It
preserves DOCUMENT_RENDER, approval/promotion semantics, approved templates,
external-source extraction, and `skills/hwp-skill/`.

## Purpose

Connect already-established one-page-report evidence to the existing generic
family recipe, TemplateSpec, resolver, and authoring path. Weekly report must
declare its supported variant selections as data and a different TemplateSpec
must use the same generic path without Python document- or field-ID branches.

## Confirmed reference evidence

- A4 portrait and left/right 20mm margins are family invariants.
- Top-level markers are literal HWPX text, not structural numbering. Marker
  hierarchy is a TemplateSpec-selected family variation; `■` is not a family
  default.
- Header-information composition varies. This task supports only existing
  `single_pair`, `wide_row`, and `paired_row` primitives through declared row
  groups; multi-column, merged, and nonuniform tables remain unsupported.
- Empty state is product policy: retain the section heading and render short
  body text, never a key/value table merely for alignment.
- Institution Design owns EDUDOC assets, colors, fonts, and masthead identity.

## Implementation scope

- TemplateSpec-selected top-level marker through existing text-style resolution.
- TemplateSpec-selected header-info row groups using existing 1-pair/2-pair
  table primitives.
- Single-text status rendered as a generic section, preserving line breaks and
  avoiding a fake structured table.
- Weekly and project TemplateSpecs using the same family/component path with
  different supported selections.
- Repair the independent native-page CLI test constructor to match the current
  `NativePageValidation` dataclass API.

## Explicit runtime-contract gaps

1. Depth-specific marker/list paragraph materialization.
2. Structured repeating status items.
3. General multi-column, merged-cell, or nonuniform table materialization.
4. Independent outer/inner table-border materialization.
5. Arbitrary TemplateSpec masthead composition override.
6. New vertical-density profile system.

## Completion criteria

1. The family has no fixed `■` top-level marker and does not force a universal
   `1 wide + 2 paired` metadata composition.
2. Weekly explicitly selects `□`, one wide metadata row, and two paired rows.
3. Project uses the same generic path with different supported selections.
4. No production Python branch inspects weekly document type or field IDs.
5. Empty state remains heading plus body; single-text status remains unparsed.
6. Focused tests and the full suite pass with zero failures.
7. A new unapproved v4 weekly candidate is generated with strict package and
   round-trip artifacts.

## Visual and native QA boundary

Candidate package/round-trip success is not visual approval. Native PageCount
passes only when actual Hancom Automation reports page count 1. Until the user
reviews a fresh Hancom rendering, visual QA remains pending; label wrapping,
literal `□` rendering, paragraph spacing, masthead balance, and one-page
density must not be claimed as visually passed.

## Completion record

Standalone historical `display="section"` state was superseded by the later
`one-page-report-visual-fidelity` implementation before a standalone commit.
Its surviving row-group, pair-count, marker, and keep-with-next behavior is
validated by that coherent implementation.

- Focused regression tests passed: 5 passed.
- Full suite passed: 295 passed.
- `sandbox/template-candidates/weekly-report-one-page-family-v4/` contains the
  unapproved source and round-trip artifacts. Native PageCount could not run
  in the Codex sandbox because its Hancom security module is unavailable.
- Visual QA remains pending human review in Hancom.

## Architecture defect remediation

- An explicit `row_groups` declaration now fails closed when its groups do not
  consume every metadata row exactly once; it no longer falls back to a
  generic `info_table`.
- The unselected `stacked` table layout capability was removed. Existing
  `label_value` metadata rendering and `pairs_per_row` remain unchanged.
- Focused regression tests passed: 8 passed. Full suite passed: 298 passed.
- The immutable replacement candidate is
  `sandbox/template-candidates/weekly-report-one-page-family-v5/` and remains
  unapproved. Native PageCount is unavailable in the Codex sandbox; visual QA
  remains pending human review in Hancom.
