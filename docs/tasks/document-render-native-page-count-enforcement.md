# Task: DOCUMENT_RENDER native PageCount enforcement

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the implemented DOCUMENT_RENDER postcondition for an
approved package that explicitly carries a package-local native PageCount
contract. It does not revise TEMPLATE_CREATE semantics, approval status,
Institution Design, family recipe values, or the renderer kernel.

## Scope

- Preserve an optional self-authored `family_recipe.json` from contract staging
  into the candidate so registration's approved-runtime allowlist preserves the
  package-local relative reference from `template_spec.json`.
- Make `core.document_api.render_approved_document()` the approved-document
  render funnel for the direct-content CLI and source-content API.
- Resolve an explicit expected page count only from package-local
  `template_spec.json` and its referenced `family_recipe.json`; never from the
  protected institution family source, QA report, or a guessed default.
- After strict final rendering succeeds, require native validation when and
  only when that explicit package-local contract exists.
- Reuse `HwpxTemplateRenderError` and `validate_native_page_count()` for final
  failure propagation.

## Out of scope

- `core/adapters/hwpx_template_renderer.py` render functions and the shared
  `_render_filled_package()` kernel.
- Candidate QA behavior and `hwpx_page_fit.py` production integration.
- Auto fitting, density profiles, typography, spacing, padding, or protected
  `templates/institutions/` changes.
- New page-count metadata fields or a default/migrated page-count value for
  existing approved packages.

## Completion criteria

1. A staged `family_recipe.json`, when present, reaches the candidate and then
   the approved package through the approved-runtime allowlist.
2. The final-render CLI calls the public document API rather than directly
   selecting a package and invoking the renderer.
3. A package-local expected page count causes final render success only when
   `validate_native_page_count()` passes; mismatch and unavailable validation
   fail without a `RenderResult`.
4. A package with no explicit page-count contract preserves existing final
   render behavior and does not call native validation.
5. New focused tests cover artifact persistence, API/CLI enforcement success
   and failure, unavailable native validation, legacy compatibility, and the
   unaffected candidate render boundary.
