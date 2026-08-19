# Task: product contract foundation

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task is authorized by the user request of 2026-08-18. It MAY revise the
whole `TEMPLATE_CREATE` and `DOCUMENT_RENDER` product contract only to define:

- the persistent artifacts and hand-offs before existing runtime paths;
- the self-authored-template semantic source of truth;
- institution design-contract ownership and provenance;
- candidate and approved lifecycle invariants; and
- source-ingestion output and canonical-content boundaries.

It MUST NOT change runtime behavior, HWPX rendering, parsers, CLI surfaces,
the protected `skills/hwp-skill/` submodule, or template data under
`templates/institutions/`.

## Goal

Make the product contracts decision-complete enough that the next runtime task
can implement the declared gaps without re-deciding ownership, state, artifact
locations, or semantic boundaries.

## Inputs

- `docs/product-workflow-contract.md`
- `docs/hwpx-generation-rules.md`
- `docs/hwpx-layout-baseline.md`
- `docs/template_spec_redesign_analysis.md`
- current runtime code and current template-data layout

## Outputs

- reconciled product workflow documentation;
- JSON Schemas for TemplateRequest, Semantic Template Contract, and
  Institution Design Contract;
- contract examples for the existing weekly-report authoring fixture; and
- a file/function-level runtime implementation gap list.

## Completion criteria

1. The authoritative artifact, lifecycle, and responsibility for every E2E
   hand-off is documented without treating unimplemented runtime behavior as
   implemented.
2. `TemplateRequest`, `Semantic Template Contract`, `Institution Design
   Contract`, executable `TemplateSpec`, and canonical content have one
   distinct responsibility each.
3. `approved` is defined as final-renderable from canonical content, while the
   current implementation gap is explicitly named rather than hidden.
4. Candidate and approved storage locations cannot overlap by contract.
5. Every new schema has an owner document, is referenced by the product
   workflow, and has a parseable example.

## Discovered issues

### BLOCKER

- The former `template-create-authoring-v2` task cannot authorize the required
  product-wide changes. This task supersedes it only for this contract work.

### FOLLOW-UP

- Runtime changes required to enforce these contracts are intentionally left
  to the next implementation task.

## Verification

- All three JSON Schema files parsed successfully, and the TemplateRequest,
  Semantic Template Contract, and Institution Design Contract examples satisfy
  their declared required shape.
- All local Markdown links under `docs/` resolve.
- No runtime code, parser, CLI, protected submodule, or institution template
  data was changed by this task.
