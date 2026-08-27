# Task: Self-authored business-status one-page report E2E

## Status

DONE — `HUMAN_REVIEW_REQUIRED`

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the self-authored `TEMPLATE_CREATE` sub-path as
needed to create and validate one unapproved EDUDOC reusable candidate for
`사업 추진현황 1페이지 보고서`. It may add the task-specific semantic contract,
TemplateRequest, executable TemplateSpec, candidate artifacts under
`sandbox/template-candidates/`, human-review bundle under `sandbox/`, and
task-scoped regression tests required to prove this candidate's 0/1/N runtime
behavior.

It may make the smallest code change only when an existing self-authored
authoring, candidate-QA, or final-render boundary prevents the declared E2E
completion criteria. It must preserve the current Product/Workflow Contract's
approval semantics, DOCUMENT_RENDER boundary, external-source extraction path,
existing approved templates, and both protected submodules.

## Goal

From user requirements and existing analyzed-HWPX structural evidence, create
a new reusable HWPX candidate without an exact source HWPX.
Render three materially different canonical-content fixtures through the
candidate, preserve reviewable outputs, and leave the candidate unapproved.

## Completion criteria

1. Record the selected internal HWPX observations and provenance, separate
   common/document-type-specific patterns from EDUDOC execution decisions,
   and do not copy a reference's concrete visual values into runtime rules.
2. Materialize a valid self-authored candidate with explicit TemplateRequest,
   semantic contract, Institution Design provenance, TemplateSpec, candidate
   QA evidence, and candidate status.
3. Render sparse, normal, and dense fixtures through the same candidate in
   one process; prove 0/1/N cardinality, no prototype/value state leakage,
   no unresolved placeholders, strict package validity, A4 portrait, and one
   native page when the local native provider is available.
4. Preserve a human-review bundle containing the candidate, all inputs and
   final HWPX outputs, equivalent QA evidence, and real native previews plus
   a comparison artifact when available. If not available, record
   `HUMAN_REVIEW_REQUIRED` and the direct HWPX paths instead.
5. Do not invoke registration or claim approval.

## Out of scope

- Generic document families, rendering primitives, or capabilities not needed
  by this candidate.
- Any change to `DOCUMENT_RENDER`, approval/promotion semantics, exact-source
  extraction, existing task contracts, existing approved templates, or either
  protected submodule.
- Automatic approval, commit, push, or external state changes.

## Evidence hierarchy

1. `docs/hwpx-layout-baseline.md` and its named source samples are the primary
   layout/structure evidence. Existing one-page family tests and recipe data
   are the executable evidence for supported projection patterns.
2. The EDUDOC Institution Design Contract owns actual typography, color,
   masthead, table, and page-policy decisions.
3. This task's TemplateSpec selects supported components for this new document
   type; it does not reproduce any one baseline sample.
4. External official documents may be used only if internal evidence does not
   establish the document type's semantic structure. They cannot supply
   runtime layout/style values.

## Selected evidence and decisions

### Internal HWPX evidence

| Source and provenance | Observation | Decision for this candidate |
|---|---|---|
| `docs/hwpx-layout-baseline.md`, group A: 광주 한장보고서, 금감원 원장보고 2건, 금감원 원페이지, 한국농어촌공사 한페이지 | A4 portrait and 20 mm left/right margins are `COMMON` (5/5). | Select the existing one-page recipe with its A4 portrait and 20 mm left/right TemplateSpec projection. |
| Same group A baseline | Full-width tables (about 168–173 mm), 0.12 mm inner borders, and 1.8/0.5 mm cell margins are `REPEATED`. | Use the existing `one_page_status_table` and metadata table roles; no source table is copied. |
| Same group A baseline | `□ → ㅇ/◦ → -` hierarchy is `COMMON`; staged indentation is observed. | Use the existing two-level `bullet_list` projection for optional next actions. |
| Existing `templates/institutions/edudoc/_families/one_page_report/recipe.json` and its task-scoped tests | Masthead, metadata, title, status table, section, callout, and bullet-list components are runtime-loaded and already materialized without document-type branches. | Select those components as data only for this new document type. |

### Evidence deliberately not adopted

- A particular baseline sample's exact fonts, colors, title banner, date-line
  alignment, page number, footer contact line, image behavior, or source text.
  These are variable, document-type-specific, or institution-specific facts.
- Any exact source HWPX: no exact target source exists, and no source extraction
  route was used.
- External web-search results: they were collected before the evidence
  hierarchy was clarified, but no semantic field or layout decision depends on
  them because the user request plus internal evidence already established the
  report structure.

### Contract ownership

- The Semantic Contract owns the fixed title/labels and canonical content,
  including optional `project_tasks` and `next_actions` collections.
- EDUDOC Institution Design owns the required masthead, logo assets, fonts,
  colors, borders, and table style roles.
- This candidate's TemplateSpec selects the supported `one_page_report`
  components, metadata grouping, four-column status projection, and two-level
  action projection. It does not introduce a new primitive or Python
  document-type branch.

## Output evidence

- Candidate: `sandbox/template-candidates/business-status-one-page-e2e/`
  with `template.json` status `candidate` and `source.hwpx`.
- Human-review bundle: `sandbox/human-review/business-status-one-page-e2e/`.
- Sparse, normal, and dense outputs all have strict package validation success,
  zero unresolved placeholders, zero missing fields, and A4 portrait package
  dimensions (`59528 × 84186`, `landscape=WIDELY`).
- The Hancom Automation COM object is present but its local security module is
  missing. Native page-count validation and real native previews therefore
  cannot run in this environment; no mock preview was made.

## Issue classification

### BLOCKER

- None initially.

### FOLLOW-UP

- Before approval, open the three final HWPX files in a Hancom environment
  with a registered Automation security module and complete native page and
  human visual review.

### OUT_OF_SCOPE

- None initially.
