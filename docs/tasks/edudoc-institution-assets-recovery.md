# Task: EDUDOC institution asset recovery

## Status

IN PROGRESS

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `PRESERVE`

This recovery task must not revise the TEMPLATE_CREATE or DOCUMENT_RENDER
system contract.

Its authority is limited to recovering the exact or best-evidenced
pre-incident contents of:

`templates/institutions/edudoc/`

and validating the recovered state.

## Incident

This task exists because of the 2026-08-25 Windows Junction / temporary
worktree cleanup data-loss incident.

Durable incident record:

`docs/data-loss-incident-2026-08-25.md`

## Goal

Recover the EDUDOC institution assets that existed before the 2026-08-25 data
loss without redesigning, inventing, or silently replacing missing production
data.

Recovery must be evidence-driven.

## Known required paths

Repository references establish that the pre-incident EDUDOC area contained
or was expected to contain at least:

- `_design/design.json`
- `_families/one_page_report/recipe.json`
- `주간업무보고서/`
- reference HWPX assets referenced by project documentation

This list is not yet considered a complete pre-incident inventory.

## Recovery principles

### Exact recovery before reconstruction

Prefer a byte-identical or clearly provenance-equivalent surviving copy.

Do not synthesize a replacement merely because it satisfies the current
schema or tests.

### Provenance required

Every restored file must record:

- original path;
- source artifact;
- source timestamp when available;
- why the source is believed to represent the lost file;
- whether the recovery is exact, derived, or uncertain.

### Uncertain recovery

If multiple surviving candidates differ, do not choose one solely because it
passes tests.

Compare the candidates against repository references, task history, generated
artifacts, and known pre-incident behavior.

If exact identity cannot be established, record the uncertainty.

### No redesign during recovery

This task must not:

- introduce new Institution Design values;
- alter family-layout policy;
- change document-family semantics;
- change hierarchy policy;
- change page-fit policy;
- create a new approved template design;
- use recovery as an opportunity to refactor unrelated code.

Any valid improvement discovered during recovery is a FOLLOW-UP unless it is
strictly required to restore the pre-incident state.

## Current recovery inventory

| Original path | Surviving evidence | Recovery status | Exactness |
| --- | --- | --- | --- |
| `_design/design.json` | `tests/fixtures/template-contracts/edudoc.institution_design.json` exists, but equivalence to the lost production Design has not yet been established | NOT RESTORED | UNKNOWN |
| `_families/one_page_report/recipe.json` | Multiple `recipe.json` / `family_recipe.json` artifacts exist under `sandbox/` | CANDIDATES FOUND | NOT YET VERIFIED |
| `주간업무보고서/` | Repository documentation proves an existing approved EDUDOC weekly-report package was referenced | NOT INVENTORIED | UNKNOWN |
| reference HWPX assets | Repository documentation refers to EDUDOC reference HWPX material | NOT INVENTORIED | UNKNOWN |

Update this table as evidence is verified.

## Recovery source priority

Use recovery sources in this order where applicable:

1. exact surviving Git object or committed source;
2. exact copied production/package artifact;
3. candidate or QA artifact known to have copied the production contract;
4. generated authoring or rendering artifact with documented provenance;
5. task-scoped fixture when equivalence to production is independently proven;
6. editor or local-history copy;
7. filesystem-level deleted-file recovery.

A lower-priority source must not overwrite a better-evidenced higher-priority
source.

## Required investigation

### Original inventory

Reconstruct the pre-incident directory and file inventory for:

`templates/institutions/edudoc/`

using repository references, surviving artifacts, Git objects, task
documentation, test fixtures, and local logs.

### Institution Design

Determine whether an exact pre-incident copy of:

`_design/design.json`

survives.

The test fixture must not automatically be promoted to production Design
without proving equivalence.

### One-page family recipe

Identify all surviving candidate copies of:

`_families/one_page_report/recipe.json`

Compare them and establish which one corresponds to the pre-incident live
contract.

### Approved weekly-report package

Reconstruct the expected contents of:

`주간업무보고서/`

Locate exact surviving approved-package artifacts before restoring anything
to the live registry.

### Reference HWPX

Identify the exact reference HWPX paths mentioned by project documentation
and determine whether surviving copies exist.

## Prohibitions

During this recovery task:

- do not create Junctions from temporary worktrees to live repository paths;
- do not run `git worktree remove --force` against a worktree containing
  unverified reparse points;
- do not run `git clean` against the affected repository or submodule;
- do not use `git reset --hard` as a recovery shortcut;
- do not force-update the institution submodule;
- do not overwrite a surviving uncertain artifact with a guessed replacement;
- do not modify unrelated runtime, schema, contract, or test behavior.

Temporary validation must comply with:

`docs/agent-policies/work-unit-execution.md`

## Validation

After restoration, validate each recovered layer independently.

At minimum:

1. the recovered Institution Design parses and satisfies its contract;
2. the one-page family recipe resolves successfully;
3. repository references to required EDUDOC paths resolve;
4. relevant task-scoped EDUDOC tests pass;
5. the approved weekly-report package, if recovered, can be located by the
   normal template-registry path;
6. recovery does not silently replace unresolved assets.

Passing tests alone does not prove exact recovery.

## Recovery log

Record each actual restoration before marking it complete.

| Path | Recovery source | Evidence | Validation | Result |
| --- | --- | --- | --- | --- |
| | | | | |

## Completion criteria

This task is DONE only when:

1. the pre-incident EDUDOC asset inventory has been reconstructed as far as
   surviving evidence permits;
2. every required recoverable asset has been restored to its original path;
3. every restored file has documented provenance;
4. exact versus reconstructed recovery is explicitly distinguished;
5. relevant contract and task-scoped validation passes;
6. the normal EDUDOC template lookup paths operate again;
7. any asset that cannot be recovered exactly remains explicitly documented
   as unresolved rather than silently replaced;
8. the incident document contains the final recovery outcome.