# Task: semantic-contract runtime integration

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task implements the already-approved `TEMPLATE_CREATE` and
`DOCUMENT_RENDER` hand-offs without revising their product semantics. It may
change only the runtime boundaries that enforce those contracts:

- semantic-contract / TemplateSpec / institution-design binding and resolved
  authoring serialization for the self-authored path;
- self-authored candidate storage, artifacts, machine-QA evidence, and human
  review evidence;
- approval-gate validation for new contract-complete packages;
- semantic required-content validation and alias-optional render preparation.

This task preserves the external-source extraction path, product workflow
documentation, and all baseline/evidence documents. It must not modify
`docs/hwpx-layout-baseline.md`, `templates/institutions/`, or
`skills/hwp-skill/`.

## Goal

Make the Semantic Template Contract the self-authored path's semantic source
of truth from resolution through candidate, approval, and render preparation,
so a newly approved package is demonstrably final-renderable with canonical
content.

## Completion criteria

1. Resolution rejects semantic/TemplateSpec binding conflicts and emits a
   deterministic resolved-authoring artifact with semantic identities and
   explicit supported visual values.
2. The self-authored CLI creates a canonical candidate bundle containing raw
   contracts, design provenance, resolved contract, source HWPX, locations,
   and persisted machine-QA evidence.
3. New-package approval requires complete candidate artifacts, QA pass,
   recorded human review, canonical field consistency, and render preparation.
4. Render preparation validates required canonical semantic fields and does
   not require `alias_map.json` when canonical fields and required metadata
   are otherwise available.
5. Task-scoped success and failure tests cover the requested integration;
   existing external-source behavior remains covered by regression tests.

## Classification

### BLOCKER

- None initially.

### FOLLOW-UP

- Masthead/assets, repeating sections, complex tables, and source-ingestion
  IR expansion remain outside this task.

### OUT_OF_SCOPE

- Baseline analysis or edits, existing approved-package migration, UI/API,
  and document-format ingestion expansion.
