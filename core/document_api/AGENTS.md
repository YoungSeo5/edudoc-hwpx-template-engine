# core/document_api/AGENTS.md

Read [README.md](README.md), the repository root `AGENTS.md`, and these policies
before changing executable behavior:

- `docs/agent-policies/minimal-abstraction.md`
- `docs/agent-policies/task-scoped-testing.md`

## Responsibility

Keep this package a thin connection boundary over existing approved-template
runtime functions.

## Required

- Resolve templates through `TemplateRegistry`; expose approved templates only.
- Delegate input preparation to `prepare_hwpx_template_input()`.
- Delegate final generation to `orchestrate_hwpx_render()`.
- Preserve template identity, execution context, source overwrite protection,
  prepared metadata, and strict HWPX validation.
- Add and run a new task-scoped test for every behavior change.

## Prohibited

- Do not copy or reimplement renderer, metadata, validation, or template logic.
- Do not expose candidate QA or approval operations.
- Do not add fallback routes or silently select another format.
- Do not add Slack, Drive, HTTP, MCP, authentication, or queue code here.
- Do not pre-create DOCX, PPTX, PDF, or other format modules.
