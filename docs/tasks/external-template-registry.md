# Task: external template registry

## Status

ACTIVE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise only the production storage boundaries of
`TEMPLATE_CREATE` and `DOCUMENT_RENDER`, the candidate/approved/audit
lifecycle paths, and user-specific registry configuration. It does not revise
template semantics, layout authoring, rendering, QA, or approval requirements.

## Goal

Keep the standalone skill package limited to code, `SKILL.md`, shared runtime,
and read-only `edudoc` design provision. Store mutable institution artifacts in
one user- or organization-selected external registry.

```text
<registry>/
├─ provision/
│  └─ <institution>/
│     ├─ _design/
│     └─ _families/
├─ self-authored/
├─ candidates/
├─ approved/
├─ _audit/
└─ _tmp/
```

`<registry>` is selected once through user-specific configuration. Loading the
skill never asks for it. Only a `TEMPLATE_CREATE` or `DOCUMENT_RENDER` request
with neither an explicit registry path nor saved configuration needs setup.
The sole user configuration file is `~/.edudoc-hwpx-template/config.json`; its
entire JSON content is `{"registry_root": "<absolute path>"}`. An explicit
`--registry-root` takes precedence over this saved value.

The registry root must be an absolute path outside the running package root,
`~/.agents/skills/hwpx-institution-template`,
`~/.claude/skills/hwpx-institution-template`, and this repository working tree.
Every descendant of these four protected locations is also rejected.

## Revised production paths

| Artifact | Canonical path |
|---|---|
| read-only institution provision | `<registry>/provision/<institution>/_design/` and `<registry>/provision/<institution>/_families/` |
| self-authoring inputs | `<registry>/self-authored/<institution>/<document_type>/` |
| candidate | `<registry>/candidates/<candidate_id>/` |
| Institution Design Contract | `<registry>/provision/<institution>/_design/design.json` |
| document family recipe | `<registry>/provision/<institution>/_families/<family>/` |
| active approved package | `<registry>/approved/<institution>/<document_type>/` |
| audit evidence | `<registry>/_audit/<template_id>/` |
| workflow temporary artifacts | `<registry>/_tmp/` |

A new registry is initialized only after the user explicitly requests it. The
initializer may copy the repository or standalone package's read-only
`templates/institutions/<institution>/_design/` and
`templates/institutions/<institution>/_families/` provision at the same
relative paths. Connecting an existing registry must not overwrite it.
`approved/` contains only explicitly approved, final-renderable document
packages; it never contains design provision or family recipes.

## Provision source and runtime lookup

The repository and standalone package both retain
`templates/institutions/<institution>/_design/` and
`templates/institutions/<institution>/_families/` at the same relative paths
as read-only initialization sources. Runtime Institution Design and document
family recipe lookup uses only
`<registry>/provision/<institution>/`; it does not read the package provision
after registry initialization or connection.
Connecting an existing registry also requires
`<registry>/provision/edudoc/_design/design.json` as a file and
`<registry>/provision/edudoc/_families/` as a directory. Missing provision
causes a failure listing the missing paths; connecting never copies or repairs
provision and never creates or modifies registry files.

## Temporary artifacts

`<registry>/_tmp/` is the only production-workflow temporary boundary for QA,
page-fit, and registration artifacts. A workflow CLI may create it when needed
and cleans its own temporary artifacts when the workflow ends. It is neither
approval evidence nor a document output boundary.

Production workflows do not fall back to OS temporary storage or the package's
internal `sandbox/`. Repository development and pytest continue to use
`sandbox/`; because a test registry itself is created below `sandbox/`, that
test registry's `<registry>/_tmp/` is also below `sandbox/`.

Exception: one atomic-replace staging file for DOCUMENT_RENDER's final output
is created in the same directory as the output so it inherits the output
directory ACL and because `os.replace()` cannot cross drives between the
registry and output. Failure cleanup follows
`docs/tasks/document-render-output-acl-inheritance.md`.

## Existing approved packages

The three templates under `templates/institutions/금융감독원/` — `금감원 원장보고`,
`금감원 원장보고 가상자산`, and `금감원 원페이지` — are remnants of a past
pipeline. Do not migrate them into registry `approved/` or `_audit/`, and do
not include them in standalone or installed packages. Leave the source
submodule unchanged; do not modify or delete it.

## Approval boundary

```text
candidate
  -> machine QA
  -> human visual review
  -> explicit approval for the matching candidate ID and digest
  -> approved registration
  -> audit preservation
```

Google Drive and email may deliver a review artifact or notification. Neither
an uploaded file nor a sent message is approval evidence. Approval remains a
human decision tied to the candidate ID and digest.

## Scope

- Add user-specific registry configuration and a deterministic setup path.
- Route all production candidate, approved-template, and audit reads/writes
  through the configured registry.
- Route production Institution Design and document family recipe lookup through
  `<registry>/provision/<institution>/`; after registry initialization or
  connection, do not read package provision.
- Route production QA, page-fit, and registration temporary artifacts through
  `<registry>/_tmp/`.
- Align the active template-routing policy and pipeline diagram with these
  storage boundaries.
- Update the standalone skill instructions and package so they do not retain
  mutable template artifacts.
- Preserve existing unapproved drafts only through an explicit, non-approving
  migration step after a registry path is selected.

## Prohibitions

- Do not create a repo-scoped `.agents/skills` skill.
- Do not modify `skills/hwp-skill/` or `templates/institutions/`.
- Do not auto-configure a registry, initialize a registry, migrate artifacts,
  approve a candidate, or send Drive/email content without the corresponding
  explicit user request. This does not permit migration of the three Financial
  Supervisory Service legacy templates named in Existing approved packages.
- Do not implement Google Drive API or email delivery in this task.
- Do not change the completed `repo-skill-packaging-mvp` task contract.

## Completion criteria

1. No production mutable artifact is created under the installed skill folder.
2. A missing registry configuration fails with an actionable setup requirement;
   it never falls back to package-relative mutable paths.
3. Candidate, active approved package, and audit paths remain separate.
4. Registration still requires machine QA, visual-review evidence, matching
   candidate digest, and explicit approval.
5. The standalone package contains only the runtime and read-only provision
   needed to initialize a registry when explicitly requested.
6. Production workflow temporary artifacts are not created outside
   `<registry>/_tmp/`, including in OS temporary storage or the package's
   internal `sandbox/`, except for the one same-directory atomic-replace
   staging file for DOCUMENT_RENDER final output, whose failure cleanup follows
   `docs/tasks/document-render-output-acl-inheritance.md`.
7. After a registry is initialized or connected, runtime Institution Design and
   document family recipe lookup does not read package provision
   (`templates/institutions/...`).

## Issue classification

- `BLOCKER`: a production workflow writes mutable artifacts inside the skill
  package, resolves an approved template outside the configured registry, or
  weakens the approval boundary.
- `BLOCKER`: a production temporary artifact is written outside
  `<registry>/_tmp/`, except for the one same-directory atomic-replace staging
  file for DOCUMENT_RENDER final output, whose failure cleanup follows
  `docs/tasks/document-render-output-acl-inheritance.md`.
- `BLOCKER`: runtime design or family lookup reads package provision instead of
  registry provision.
- `FOLLOW-UP`: Google Drive API, email notification, approver-role management,
  registry revision history, and concurrent shared-drive coordination.
- `OUT_OF_SCOPE`: renderer redesign, new document-family materializers, and
  changes to private template data.
