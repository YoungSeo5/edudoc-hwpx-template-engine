# Work-Unit Execution Policy

Root `AGENTS.md` requires an explicit task contract for every scoped task and
defines the required reading order. This policy owns the detailed rules for
task-contract authority, scope limits, and issue classification.

## Applies to

Every scoped project task, including:

- investigation and analysis
- planning
- E2E or architecture changes
- contract and schema changes
- documentation changes
- implementation
- testing
- migration

## Task contract authority

The active task contract MUST declare its authority over the parent system
contract. A task must state one of these:

- `PRESERVE`: the parent E2E/system contract must not be changed.
- `REVISE`: the task may revise explicitly named portions of the parent
  E2E/system contract.

`REVISE` does not permit unrestricted redesign. The task contract must name
the exact workflow, sections, decisions, or boundaries it is allowed to
change.

## Issue classification

When work discovers a new issue, classify it as:

- `BLOCKER`: required to satisfy the current task's completion criteria.
- `FOLLOW-UP`: valid issue, but not required to complete the current task.
- `OUT_OF_SCOPE`: unrelated to the current task.

Do not automatically expand the current task because a new issue was found.

If a discovered issue proves that the active task contract itself is wrong or
incomplete, stop only the affected work, record the issue, revise the task
contract with human approval, and then continue.

An open issue in `docs/product-workflow-contract.md` is not automatically a
`BLOCKER` for every task.

## Temporary worktree and reparse-point safety

Temporary validation environments are disposable. Their external dependencies
and targets are not.

### Protected-path rule

A temporary worktree MUST NOT contain a Windows Junction, directory symbolic
link, or other reparse point whose target is a live or non-disposable path,
including:

- the primary repository working tree;
- another active Git worktree;
- a submodule working tree;
- `templates/institutions`;
- an approved-template registry;
- user-authored or untracked project data;
- any directory whose contents are not explicitly disposable.

The fact that a linked target is intended to be read-only does not make the
link safe for worktree cleanup.

### Worktree cleanup rule

Do not run:

`git worktree remove --force`

on a temporary worktree until it has been verified that the worktree contains
no reparse point whose target escapes the temporary worktree.

If such a link exists, cleanup MUST stop.

The external target and the link-removal semantics must be verified before
the temporary worktree may be removed.

### External-data rule

When isolated validation requires data from outside the temporary worktree,
prefer one of these approaches:

1. create a disposable copy or snapshot of the required data;
2. initialize the required dependency normally inside the validation
   environment when its Git contract permits it;
3. change the validation harness to read a verified external source without
   placing a traversable directory link inside the disposable worktree.

Do not solve missing validation data by linking the disposable worktree
directly to a protected live directory.

### Submodule data rule

A submodule path is not automatically disposable.

Tracked files may be recoverable from Git while local untracked files are not.

Before any cleanup operation that can affect a submodule working tree, treat
untracked and ignored contents as potentially user-owned data unless their
disposability has been explicitly established.

### Cleanup ownership

An agent may automatically remove only temporary resources that it created
and whose deletion boundary is proven to be contained within the disposable
resource itself.

A cleanup command must not be justified solely by statements such as
"this is only a temporary worktree" when that worktree contains links,
mounts, Junctions, shared directories, or other references to external data.

### Data-loss response

If an execution step may have deleted or overwritten non-disposable data:

1. stop destructive cleanup and mutation affecting the relevant paths;
2. preserve available logs and surviving artifacts;
3. determine the affected path and command sequence;
4. create or update a durable incident record;
5. recover from verified sources rather than guessing missing content.

Do not hide a data-loss event by recreating enough files merely to restore
test success.

### Incident reference

These rules were strengthened after the repository data-loss incident recorded
in:

[`docs/data-loss-incident-2026-08-25.md`](../data-loss-incident-2026-08-25.md)

The incident demonstrated that a disposable worktree is not a valid deletion
boundary when it contains a Junction or other reparse point targeting
non-disposable data.

## Completion

A task is DONE when its declared completion criteria are satisfied.
Remaining `FOLLOW-UP` items do not prevent the task from closing.
