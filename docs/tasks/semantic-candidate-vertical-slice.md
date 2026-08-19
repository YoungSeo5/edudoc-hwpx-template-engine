# Task: semantic candidate vertical slice

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task implements only the self-authored `TEMPLATE_CREATE` vertical slice:
the four JSON inputs, semantic placement binding, deterministic HWPX authoring,
candidate QA invocation, and candidate-bundle persistence. It preserves the
parent workflow and does not revise product contracts or schemas.

## Allowed files

- `core/adapters/hwpx_template_authoring.py`
- `core/adapters/hwpx_authoring_resolve.py`
- `scripts/templates/author_hwpx_template.py`
- weekly-report contract/spec fixtures
- authoring task-scoped tests and one new task-scoped test

## Prohibited scope

- `docs/product-workflow-contract.md`, `docs/contracts/`, baseline evidence,
  renderer, source ingestion, alias map, approval, registration, and QA CLI;
- `templates/institutions/` and `skills/hwp-skill/`.

## Completion criteria

1. The authoring CLI validates all four input contracts and their identities.
2. Semantic Contract element binding, not section type or table column,
   determines self-authored separation roles and canonical placeholder IDs.
3. The candidate root contains the required copied contracts, source HWPX,
   rules, placeholder map, QA report, and existing QA artifacts with candidate
   status unchanged.
4. A new task-scoped end-to-end test covers the public authoring flow and
   semantic-to-location projection.

## Classification

### BLOCKER

- None initially.

### FOLLOW-UP

- Approval, renderer, source ingestion, and existing external-source QA remain
  outside this vertical slice.
