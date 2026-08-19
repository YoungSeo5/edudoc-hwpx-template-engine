# Task: one-page-report family authoring

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the self-authored `TEMPLATE_CREATE` layout-planning
and source-authoring sub-path. It may introduce the executable
`one_page_report` family contract, reusable HWPX layout components, and the
corresponding `TemplateSpec`/resolver/materializer contract.

It may revise these parent-contract statements only as required to describe
the implemented self-authoring layout capability:

- `TEMPLATE_CREATE` layout-planning and authoring status/capability text;
- the TemplateSpec capability statement in “Baseline, design policy,
  TemplateSpec, and masthead”.

It must preserve DOCUMENT_RENDER, approval/promotion semantics, existing
approved templates, source-based external-HWPX extraction, and
`skills/hwp-skill/`.

## Goal

Implement an executable `one_page_report` document-family recipe backed by
reusable HWPX layout components. Use it to create a compact weekly report and
a structurally different second one-page report without adding document- or
field-specific branches to Python authoring code.

## Required evidence

- Analyze only one-page-report/original-report reference HWPX files from
  `C:\Users\ohyou\OneDrive\바탕 화면\샘플파일 등`; exclude press releases.
- Keep EDUDOC identity values in the Institution Design Contract; derive only
  reusable layout structure/proportions from the reference analysis.
- Add machine tests for recipe loading, component order, both TemplateSpecs,
  XML materialization, and no document-specific Python branch.
- Generate unapproved candidates at
  `sandbox/template-candidates/weekly-report-one-page-family/` and
  `sandbox/template-candidates/one-page-report-reuse-proof/`.

## Completion criteria

1. `one_page_report` is a runtime-loaded recipe, not documentation only.
2. Components support the declared generic component types and do not inspect
   weekly-report field names or document types.
3. Weekly report declares five metadata fields and six body sections through
   the family/component TemplateSpec.
4. A distinct second report uses the same institution design, recipe, and
   component code through data-only contracts.
5. Both candidates pass strict package/round-trip validation and remain
   unapproved.
6. Focused, directly affected, and full test suites pass.

## Out of scope

- Press-release family support.
- Any automatic approval or modification of existing approved templates.
- New document ingestion or final-rendering workflows.
