# Document API

`core.document_api` is the internal Python connection boundary for approved
document templates. External Slack, MCP, HTTP, and storage integrations may call
this package; they do not belong inside it.

Agents changing this folder must also follow [AGENTS.md](AGENTS.md).

## Current API

- `list_approved_templates()` lists approved HWPX templates from the institution
  template registry.
- `get_template_contract()` returns the existing placeholder and alias contracts.
- `validate_template_content()` delegates to the existing HWPX input preparation.
- `render_approved_document()` delegates to the existing approved HWPX
  orchestration and strict validation path.

## Boundary

This package contains connection code only. It does not implement renderers,
approve candidates, rewrite template contracts, add fallback routes, or integrate
external services. HWPX rendering remains owned by `core.adapters`, and approved
template data remains under `templates/institutions`.

Add a format-specific module only when a second document format is actually
connected. See the repository
[architecture](../../docs/architecture.md) and
[HWPX template policy](../../docs/agent-policies/hwpx-template-rendering.md).
