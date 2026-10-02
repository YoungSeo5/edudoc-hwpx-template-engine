# Task: Self-authored 출장 결과보고서 template candidate

## Status

DONE — `HUMAN_REVIEW_REQUIRED`

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task adds only data for one new EDUDOC self-authored document type and
runs the existing `TEMPLATE_CREATE` self-authoring path. It changes no code,
schema, family recipe, Institution Design, existing template, task contract,
or protected submodule.

## Goal

Create an unapproved, reusable `edudoc` / `출장 결과보고서` HWPX template
candidate from the user's stated items through the existing
`scripts/templates/author_hwpx_template.py` pipeline.

## User request (2026-09-15)

- Institution: `edudoc`.
- Overview items: 출장자, 소속, 출장 기간, 출장지, 작성일, 보고 대상, 출장 목적,
  경비 합계.
- Body items: 주요 일정표(일자·방문처·주요 활동, 여러 행), 출장 결과(주요 내용),
  성과 및 시사점.
- New template only; do not modify existing files.

## Inputs (new)

- `templates/self-authored/edudoc/출장 결과보고서/template_request.json`
- `templates/self-authored/edudoc/출장 결과보고서/semantic_contract.json`
- `templates/self-authored/edudoc/출장 결과보고서/template_spec.json`
- existing, unchanged: `templates/institutions/edudoc/_design/design.json`,
  `templates/institutions/edudoc/_families/one_page_report/recipe.json`

## Decisions

- Layout uses the existing `one_page_report` components (masthead,
  title_block, header_info, status_table, section) as data only. No new
  primitive or document-type branch.
- Visual values come only from the EDUDOC Institution Design and family
  recipe; the TemplateSpec states only structure, bindings, column ratios,
  and the `□ ` heading marker already used by existing EDUDOC specs.
- All user-selected items are required; the schedule is `cardinality: many`.

## Completion criteria

1. Canonical inputs exist and the authoring CLI accepts them without
   `--allow-noncanonical-inputs-for-test`.
2. A candidate is produced under `sandbox/template-candidates/` with
   `template.json` status `candidate`, strict sample/test round-trip
   validation passing, and no leftover placeholder.
3. Registration is not invoked; nothing is approved.

## Output evidence

- Candidate: `sandbox/template-candidates/business-trip-result-report-v2/`,
  `template.json` status `candidate`, `template_id`
  `tpl_fa233fe01ff392c9196c3c51`. Authoring CLI exit 0 with canonical inputs;
  strict validation true for both round-trips; zero missing fields and
  leftover placeholders; native page count 1 for `source.hwpx` and both
  round-trips.
- Review renders: `sandbox/human-review/business-trip-result-report/`
  (`sparse.hwpx` 1 schedule row, `normal.hwpx` 3, `dense.hwpx` 6, their
  `content.*.json`, and `render_checks.json`). Each is strict-valid with
  matching schedule rows, all scalar values, no `{{` placeholder, and no
  sample-row leakage; outputs are distinct and re-render byte-identical.
  Native page count (absolute path) is 1 for all three.
- No registration was run; visual approval has not been given.

## Issue classification

### BLOCKER

- None initially.

### FOLLOW-UP

- Human visual review in Hancom (and native page count where the Hancom
  Automation security module is available) before any approval.
- The `status_table` component has no heading materialization, and an
  unknown `heading_text` key on it is silently ignored instead of failing
  fast. The schedule table therefore has no "주요 일정" heading; its header
  row (일자/방문처/주요 활동) identifies it. The first run
  (`sandbox/template-candidates/business-trip-result-report/`) carried that
  ineffective key and is superseded by `business-trip-result-report-v2`.
- Candidate QA round-trip (`roundtrip.test.hwpx`) does not apply `many`
  table-row collection values; the sample rows remain. The same holds for the
  existing weekly-report candidate, so it is a pre-existing QA limitation.
  Collection rendering was verified separately with `render_candidate_roundtrip`.
- `scripts/templates/check_native_page_count.py` fails with
  `native_page_open_failed` when `--input` is a relative path; the same file
  passes with an absolute path.

### OUT_OF_SCOPE

- None initially.
