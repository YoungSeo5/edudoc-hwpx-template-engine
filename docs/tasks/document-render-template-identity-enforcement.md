# Task: DOCUMENT_RENDER template identity enforcement

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task preserves the existing DOCUMENT_RENDER workflow and changes only its
public approved-render service boundary: every normal entry point must provide
the canonical approved `template_id` before final rendering starts.

## Scope

- Require `content_template_id` at `render_approved_document()`.
- Refuse a missing or mismatched identity before `orchestrate_hwpx_render()`.
- Preserve the direct-content CLI path and pass the selected source-content
  path's approved template identity into the same service boundary.
- Add regression coverage for missing, mismatched, matching, and source-content
  normal paths.

## Out of scope

- Native PageCount behavior.
- Authoring, candidate QA, registration, schemas, and protected submodules.
- New identity sources, compatibility paths, fallbacks, abstractions, or
  refactors.

## Completion criteria

1. Direct service calls without a template identity fail before rendering.
2. Direct service calls with a mismatched identity fail before rendering.
3. A matching identity keeps the existing final-render result.
4. Source-content rendering reaches the same service with the selected
   approved identity.
