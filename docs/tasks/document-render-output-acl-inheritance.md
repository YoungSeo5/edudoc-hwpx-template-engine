# Task: DOCUMENT_RENDER output ACL inheritance

## Status

COMPLETE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task preserves DOCUMENT_RENDER content projection, HWPX package structure,
validation, approved-template selection, and caller-owned output paths. It may
change only final artifact persistence in `hwpx_template_renderer.py` so a
successfully validated output inherits its destination directory's filesystem
permissions.

## Scope

- Build and validate the complete HWPX before publishing it at the final path.
- Publish with a same-directory atomic replacement without carrying a private
  temporary directory's ACL onto the final file.
- Remove temporary artifacts on staging or package-validation failure and
  preserve an existing final output until a replacement has passed renderer
  validation.
- Add focused regression coverage for permission inheritance, atomic publish,
  and failure cleanup.

## Out of scope

- HWPX content, layout, metadata, renderer semantics, or template changes.
- ACL mutation with platform commands or post-write permission repair.
- Candidate QA, approval, registration, and protected submodules.

## Completion criteria

1. A final render inherits the output directory ACL on Windows.
2. Rendering and validation complete before the final path is replaced.
3. A staging or package-validation failure leaves no temporary sibling and
   preserves any existing final file.
4. Focused, affected regression, and production CLI validation pass without
   modifying approved templates or their source HWPX.

## Completion record

- The renderer builds and validates a same-directory sibling HWPX, then uses
  `os.replace()` only after success. The sibling inherits the output directory
  ACL; private rewrite directories never become the final file.
- The Windows ACL and failure-cleanup regressions passed, followed by 46 directly
  affected renderer/API regressions and the deep one-page candidate E2E.
- A production `fss_one_page` render passed strict package validation with
  `AreAccessRulesProtected=False`, nine inherited ACEs, no temporary artifact,
  and no approved-template hash change.
- The full suite completed with 395 passed, 5 skipped, and 3 unrelated failures:
  two require unavailable native Hancom page validation, and one fixture omits
  the now-required family recipe `page` object.
