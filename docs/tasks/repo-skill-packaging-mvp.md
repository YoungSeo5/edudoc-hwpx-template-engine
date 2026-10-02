# Task: standalone skill packaging MVP

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This task packages the existing repository workflow as a standalone Codex
skill directory. It must not revise `TEMPLATE_CREATE`, `DOCUMENT_RENDER`,
lifecycle, storage, approval, rendering, or validation semantics.

## Scope

- Keep the canonical repository entrypoint at root `SKILL.md` and correct its
  workflow routing and stale candidate path.
- Assemble a separate `C:/Users/work/hwpx-institution-template/` sibling directory with the
  corrected `SKILL.md`, minimal `agents/openai.yaml`, required runtime files,
  required policy/contracts, runtime dependencies, and an empty sandbox
  boundary.
- Route both `TEMPLATE_CREATE` entry paths and `DOCUMENT_RENDER` without
  duplicating their canonical policy text.
- Verify the standalone copy's skill structure, local links, imports, workflow
  CLIs, routing instructions, and applicable end-to-end behavior.
- Package only the `edudoc` Institution Design Contract and its logo assets as
  the initial institution provision. Do not package any approved document
  template until its candidate has completed human visual review and explicit
  approval.
- Rename the shared package-metadata and preview helpers so the standalone
  runtime does not carry FSS-specific identifiers for institution-neutral
  behavior.

## Prohibitions

- Do not change schemas, source templates, submodules, or registry data in
  place. Runtime changes are limited to institution-neutral renaming of shared
  metadata/preview helpers and the corresponding regression test.
- Do not add a package builder, installer, plugin, or repo-scoped skill.
- Do not modify `skills/hwp-skill`; treat it only as a copied runtime
  dependency.
- Do not auto-install dependencies or initialize submodules.
- Do not approve or register a candidate without a separate explicit human
  approval after visual review.
- Do not delete or modify unrelated working-tree changes.
- Do not commit or push.

## Completion criteria

1. `C:/Users/work/hwpx-institution-template/SKILL.md` is the standalone package
   entrypoint and passes skill validation.
2. The skill description selects institutional HWPX authoring, extraction, and
   approved-template rendering, and excludes generic conversion.
3. `TEMPLATE_CREATE` includes self-authoring and exact-source extraction, then
   the shared QA, human review, and explicit approval boundary.
4. `DOCUMENT_RENDER` requires an approved template and refuses unresolved
   required content or renderer fallback.
5. Candidate output stays under `sandbox/template-candidates/`; the package
   includes only `sandbox/.gitkeep`, not generated artifacts.
6. The package contains only the runtime, policies/contracts, dependencies,
   and template provision selected by this task.
7. Skill validation, link checks, CLI import smoke tests, focused tests, and
   runnable package scenarios pass or an external human-approval blocker is
   reported exactly.
8. The standalone and installed packages contain no Financial Supervisory
   Service registry data or FSS-specific runtime identifiers.
9. Before the first `edudoc` candidate is explicitly approved, approved
   template discovery returns an empty list; this is the required lifecycle
   state, not a packaging failure.

## Issue classification

- `BLOCKER`: broken package references/imports, missing workflow route, missing
  required runtime dependency, the confirmed relative-path native Hancom open
  failure, or a validation failure caused by this task.
- `FOLLOW-UP`: plugin distribution or unsupported runtime product capabilities
  already identified by the parent contract.
- `OUT_OF_SCOPE`: renderer behavior, new document types, private template
  contents, and unrelated dirty-tree changes.

## Packaging record

Source:
- root `SKILL.md`, selected tracked runtime files, canonical operational docs,
  initialized `skills/hwp-skill`, and the `edudoc` Institution Design Contract
  with its logo assets

Destination:
- `C:/Users/work/hwpx-institution-template/`

Copied:
- only files required for the standalone skill's declared workflows; the
  initial registry contains `templates/institutions/edudoc/_design/` and no
  approved document package

Excluded:
- `.git/`, `.venv/`, caches, logs, test code, unrelated test fixtures, task
  history, generated sandbox contents, unrelated templates, and
  development-only files; four contract example JSON files referenced by the
  packaged authoring contract are retained as documentation examples

Verification:
- root and package `SKILL.md` match
- every packaged local reference resolves
- no generated sandbox artifact is included
- no source submodule or template registry file is modified; their contents are
  copied into the local internal-use package without Git metadata
- no repo-scoped `.agents/skills` entry is created

## Previous packaging result superseded

The earlier package copied the entire initialized private registry snapshot,
which exposed two obsolete Financial Supervisory Service templates as the only
approved templates. That result does not satisfy this corrected contract and
must not be treated as verification evidence.

Current verification results are recorded only after the clean standalone and
installed packages have been rebuilt and tested.

## Corrected verification results

- `templates/institutions/` contains only `edudoc/_design/` with the two logo
  assets; approved template discovery returns `[]`.
- No FSS-named adapter, runtime identifier, or Financial Supervisory Service
  registry data remains in the standalone or installed runtime/template scope.
- Shared package metadata and preview handling use institution-neutral names;
  the behavior-preserving affected regression set reports `35 passed`.
- New regression file:
  `tests/task_scoped/test_institution_neutral_package_metadata.py`.
  Before implementation it failed at collection because
  `core.adapters.hwpx_package_metadata` did not exist; after implementation all
  three tests pass.
- Root, standalone, and installed `SKILL.md` files have matching SHA-256 hashes.
- `quick_validate.py` passes for both standalone and installed copies when run
  with UTF-8 mode.
- All five workflow CLIs exit 0 for `--help` in the installed environment.
- Installed `TEMPLATE_CREATE` authoring produced an `edudoc` candidate with two
  embedded logo assets, `status: candidate`, both strict roundtrips passing,
  and no missing fields or leftover placeholders. The smoke-test input and
  candidate were removed afterward; no approval or registration was performed.
- Full source suite: `399 passed, 5 skipped, 3 failed`. Two failures require the
  unavailable local Hancom security module for native page validation. The
  remaining pre-existing one-page recipe fixture omits its required `page`
  object. None exercises the institution-neutral rename or package selection.
- Installed cleanup leaves only `sandbox/.gitkeep` and
  `templates/self-authored/.gitkeep`; no generated candidate is packaged.
