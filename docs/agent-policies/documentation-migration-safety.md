# Documentation Migration Safety

## Purpose

This policy prevents content loss, broken references, orphaned documents, duplicate sources of truth, and unnecessary repository growth during documentation changes.

It applies whenever documentation is:

- created,
- moved,
- renamed,
- split,
- consolidated,
- shortened,
- archived,
- or deleted.

## Mandatory Migration Order

Documentation migration must follow this order:

1. Create the destination file.
2. Copy or move the required source content into the destination.
3. Verify that the destination contains the complete intended content.
4. Update references to point to the destination.
5. Verify that every changed local reference resolves to an existing file.
6. Only then remove or shorten the original content.

Use the following rule:

```text
Copy → Verify → Redirect → Delete
```

Do not delete source content before the destination has been created and verified.

## Safety Rules

1. Create and populate the destination file before deleting any source content.
2. Do not add a reference to a local file that does not exist.
3. Preserve all normative rules, architectural contracts, workflow requirements, safety constraints, ownership boundaries, and agent responsibilities.
4. Do not replace detailed rules with a pointer unless the destination file already contains those rules.
5. Record every documentation migration with:
   - source file,
   - source sections,
   - destination file,
   - content moved,
   - content intentionally removed,
   - reason for intentional removal.
6. Verify that every changed local documentation path exists.
7. Do not delete or shorten the source section until the destination content has been reviewed against the original.
8. Do not create a new documentation file unless its purpose, owner document, and reference path are clear.
9. Every new documentation file must be referenced by at least one appropriate owner or index document.
10. Do not create placeholder references for files that may be written later.
11. Do not create empty destination files, stub files, or TODO-only policy files as substitutes for completed migration.
12. Report documentation movement separately from wording reduction.

## Source-of-Truth Rules

Before creating a new document, determine whether an existing canonical document already owns the subject.

Do not create a second source of truth when the content belongs in an existing document.

When multiple documents describe the same rule:

1. choose one canonical source,
2. move the complete rule to that source,
3. replace duplicate content with a valid reference,
4. verify that the canonical file exists,
5. remove only confirmed duplication.

A short summary must not silently replace a normative rule.

## Incomplete Migration Conditions

A documentation migration is incomplete if any of the following is true:

- a referenced file is missing,
- source content has no verified destination,
- a new document is not referenced by an owner or index,
- normative rules were shortened without preservation,
- the destination contains only a placeholder or TODO,
- duplicate sources of truth remain,
- a document was deleted without recording its destination,
- local links or paths are broken,
- unrelated folders or documents were created,
- the final report does not identify moved and removed content separately.

If any incomplete condition is detected, stop and report it. Do not describe the migration as complete.

## Required Verification

After documentation changes, verify:

1. every newly added local path exists,
2. every changed local reference resolves,
3. every deleted normative section exists in its declared destination,
4. no unintended empty files were created,
5. no unintended directories were created,
6. no orphaned document was introduced,
7. no duplicate source of truth was introduced,
8. the working tree contains only intended documentation changes.

Where repository tooling exists, run the relevant documentation-link, path, policy, and diff checks.

Do not weaken, skip, or delete validation checks to make the migration appear successful.

## Required Completion Report

The final report must include:

```text
Source:
- <source file and sections>

Destination:
- <destination file and sections>

Moved:
- <content moved without semantic loss>

Removed:
- <content intentionally removed and reason>

References updated:
- <files whose references changed>

Verification:
- destination file exists
- changed local references resolve
- no orphaned documents
- no unintended files or directories
- no duplicate source of truth
```

Do not report the task as complete without this evidence.
