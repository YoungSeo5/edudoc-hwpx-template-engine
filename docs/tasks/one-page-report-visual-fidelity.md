# Task: one-page-report visual fidelity

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the existing self-authored `TEMPLATE_CREATE`
layout-planning and source-authoring path for `one_page_report`. It preserves
DOCUMENT_RENDER, approval semantics, approved templates, source extraction,
and `skills/hwp-skill/`.

## Purpose

Add data-declared structured paragraph hierarchy and simple repeated status
table materialization. The runtime must materialize TemplateSpec-selected
geometry without inspecting field IDs, marker glyphs, or content strings.

## Evidence inventory

Existing documents record marker sequences, literal-marker representation,
alignment, page margins, font hierarchy, and some line-spacing/indent
observations. They do not yet provide a structured per-depth XML provenance
table for left/first-line indent, tab position, and paragraph spacing. This
task supplements only those missing geometry facts from the stored reference
HWPX sources.

## Completion criteria

1. Each structured item materializes as an independent HWPX paragraph.
2. TemplateSpec selects marker and supported per-depth paragraph geometry.
3. Structured status data materializes without parsing display text.
4. Weekly and project fixtures prove generic reuse with different selections.
5. Focused and full tests pass; v6 remains an unapproved candidate.

## QA boundary

Native PageCount requires Hancom Automation with a usable security module.
Visual QA remains pending human review in Hancom.

## Completion record

- Structured `simple_table`, hierarchy paragraphs, and collection 0/1/N
  materialization are covered by focused regressions and the full pytest suite.
- `one-page-report-family-variants` was absorbed into this coherent
  implementation before it received a standalone commit; its surviving
  row-group, pair-count, marker, and keep-with-next behavior is covered here.
- A fresh unapproved candidate was regenerated after EDUDOC asset recovery.
  Native page validation remains unavailable because the local Hancom security
  module is missing; this is the stated QA boundary and is not approval.
