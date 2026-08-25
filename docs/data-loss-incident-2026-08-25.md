# 2026-08-25 Codex Windows Junction Data-Loss Incident

## Status

RECOVERY IN PROGRESS

## Related project controls

Permanent execution-safety policy:

[`docs/agent-policies/work-unit-execution.md`](agent-policies/work-unit-execution.md)

Active recovery task:

[`docs/tasks/edudoc-institution-assets-recovery.md`](tasks/edudoc-institution-assets-recovery.md)

## Summary

On 2026-08-25, files under the live institution-template path

`templates/institutions/`

were removed during Codex-driven temporary worktree cleanup.

Git-tracked submodule contents could subsequently be restored from Git, but
untracked local assets under

`templates/institutions/edudoc/`

were not restored by normal submodule checkout.

The incident was not caused by the hierarchy paragraph-spacing calibration
logic itself.

## Affected repository

`C:\Users\work\edudoc-hwpx-template-engine`

## Affected live path

`templates/institutions/`

The known unrecovered area is:

`templates/institutions/edudoc/`

## Confirmed command sequence

During an isolated page-fit validation, Codex created a temporary Git
worktree:

`sandbox/commit-audit-pagefit-20260825`

The temporary worktree's

`templates/institutions`

path was then replaced with a Windows Junction targeting the live repository
path:

`C:\Users\work\edudoc-hwpx-template-engine\templates\institutions`

The relevant operation was equivalent to:

```powershell
New-Item -ItemType Junction `
  -Path <temporary-worktree>\templates\institutions `
  -Target C:\Users\work\edudoc-hwpx-template-engine\templates\institutions

```

Codex later removed the temporary worktree with:

```powershell
git worktree remove --force sandbox\commit-audit-pagefit-20260825

```

A substantially identical Junction + forced worktree-removal sequence was
executed again during the hierarchy validation pass.

## Timeline

* **09:56**: A temporary page-fit validation worktree was prepared. The worktree-local `templates/institutions` path was connected to the live repository's `templates/institutions` directory using a Windows Junction.
* **09:57**: Codex executed `git worktree remove --force sandbox\commit-audit-pagefit-20260825`
* **10:09-10:10**: A second temporary validation worktree for hierarchy tests used the same Junction pattern and was subsequently removed.
* **After cleanup**: The live `templates/institutions` contents were observed missing. Tracked submodule contents were recoverable through Git. The untracked `edudoc/` assets were not recovered by submodule checkout.

## Failure-mode assessment

The confirmed command sequence is:

1. Create a Windows Junction from a disposable worktree into a live, non-disposable directory;
2. Remove the disposable worktree using `git worktree remove --force`.

The observed data loss is consistent with a known Codex Desktop on Windows
failure mode in which managed-worktree cleanup traverses a Junction and
removes files from the Junction target.

The command sequence is confirmed by local Codex logs.
The exact internal filesystem-cleanup implementation responsible for
following the Junction was not directly observed.

## Evidence

Primary local evidence:

* `C:\Users\ohyou\.codex\logs_2.sqlite`
* `C:\Users\ohyou\.codex\.sandbox\sandbox.2026-08-25.log`

The Codex logs contain the actual tool calls that:

* created the validation worktrees;
* created the Junction to the live `templates/institutions` path;
* executed `git worktree remove --force`;
* later observed the institution submodule / EDUDOC path as unavailable.

An upstream Codex Windows issue also documents the same class of
Junction-following worktree-cleanup data loss.

## Known impact

The exact pre-incident inventory is still being reconstructed.
Repository references establish that the deleted EDUDOC area contained or was
expected to contain at least:

* `templates/institutions/edudoc/_design/design.json`
* `templates/institutions/edudoc/_families/one_page_report/recipe.json`
* `templates/institutions/edudoc/주간업무보고서/`
* EDUDOC reference HWPX assets referenced by project documentation

Additional files may have existed and must not be inferred solely from this
known-path list.

## Recovery policy

Recovery must reconstruct the exact pre-incident EDUDOC assets wherever
possible.
Missing production assets must not be recreated from guesses or redesigned
merely to make tests pass.

For every restored file, record:

* original repository path;
* recovery source;
* evidence that the source corresponds to the lost file;
* whether recovery is exact or reconstructed;
* validation performed after restoration.

Possible recovery sources include:

* surviving Git objects;
* sandbox candidate artifacts;
* QA outputs;
* authoring outputs;
* approved-package copies;
* test fixtures;
* surviving HWPX outputs;
* editor/local-history copies;
* filesystem recovery if no exact surviving copy exists.

## Prevention

The permanent execution-safety rules resulting from this incident belong in:
`docs/agent-policies/work-unit-execution.md`

The active recovery work is tracked in:
`docs/tasks/edudoc-institution-assets-recovery.md`

## Incident closure criteria

This incident may be marked RECOVERED only when:

1. the pre-incident EDUDOC asset inventory has been reconstructed as far as available evidence permits;
2. every recoverable required asset has been restored;
3. every restored asset has documented provenance;
4. relevant contract and task-scoped validation passes;
5. unresolved losses, if any, are explicitly documented rather than silently replaced.