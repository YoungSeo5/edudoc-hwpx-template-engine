# Template authoring contracts

This document owns the three pre-runtime contracts in the product workflow.
The workflow and lifecycle themselves remain owned by
[`docs/product-workflow-contract.md`](../product-workflow-contract.md).

## Contract chain

```text
TemplateRequest
  -> Semantic Template Contract
  -> Institution Design Contract + executable TemplateSpec
  -> source.hwpx + location contracts
```

The arrows are one-way. No runtime code may infer the preceding contract from
the following artifact.

| Artifact | Authoritative responsibility | Canonical location | Current runtime status |
|---|---|---|---|
| TemplateRequest | Preserve the user's stated purpose, items, fixed text, reference scope, and constraints | `sandbox/template-candidates/<candidate_id>/template_request.json` until approval; copied into approved package | Not implemented |
| Semantic Template Contract | Agent decision: canonical content fields, fixed elements, requiredness, cardinality, and content type | `sandbox/template-candidates/<candidate_id>/semantic_contract.json` until approval; copied into approved package | Not implemented |
| Institution Design Contract | Institution policy/defaults for self-authored documents, distinct from observations | `templates/institutions/<institution>/_design/design.json` | Not implemented |
| executable TemplateSpec | Concrete ordered layout and provenance references, consumed by authoring | candidate `template_spec.json`; copied into approved package | Current parser supports only its `sections[]`, `page`, and `styles` subset |
| canonical content | Per-job `template_id` plus canonical `field_id -> value` map | caller-owned `content.json` / prepared in memory | Existing renderer input; requiredness is not yet enforced from semantic contract |

The candidate root is always under `sandbox/template-candidates/`; candidate
artifacts must not be created in `templates/institutions/`. The approved root
is always `templates/institutions/<institution>/<document_type>/`. The latter
has exactly one active approved template per institution/document-type path;
its `template_id` remains the canonical immutable revision identity.

`templates/institutions/` is a protected data submodule. This repository
defines that layout but does not create or edit its institution data.

## Schemas

- [TemplateRequest v1](template-request.schema.json)
- [Semantic Template Contract v1](semantic-template-contract.schema.json)
- [Institution Design Contract v1](institution-design-contract.schema.json)

The JSON Schemas define artifact validity only. They do not claim that every
concept is currently renderable.

### TemplateRequest

`TemplateRequest` is an immutable user-input record. It intentionally has no
semantic field IDs, requiredness inferred by an agent, HWPX positions, XML
identifiers, or layout coordinates.

### Semantic Template Contract

The semantic contract is the source of truth for semantic meaning.

- A `CONTENT` element has a canonical `field_id`, requiredness, cardinality,
  and content type.
- `FIXED_LABEL` and `FIXED_TEXT` elements carry their exact fixed text.
- `section.type` is never a semantic source of truth. It can only select a
  layout materialization method after the semantic decision is made.
- `cardinality: many` declares a repeat requirement. It does **not** claim
  that `repeat_section` is implemented.

The agent creates this artifact from the request and evidence. Deterministic
code validates it, projects its declared roles into location rules, and rejects
unknown/missing data; it must not decide roles from field names or section
types.

### Institution Design Contract

The baseline is evidence: it records what was observed in reference documents.
The institution design contract is product policy: it states which defaults a
new self-authored document should use. A policy may cite baseline evidence but
is not itself an observation.

The canonical design path is:

```text
templates/institutions/<institution>/_design/
  design.json
  assets/<asset files>
```

No base64 asset is copied into TemplateSpec. `design.json` refers to an asset
by `asset_id`; the asset's `path` is relative to `_design/`. Masthead policy is
institution-wide (`required` or `none`) and a document-specific TemplateSpec
may override it only when `document_override_allowed` is true. Current runtime
does not materialize mastheads or assets, so a design using them is not yet
authorable.

### Executable TemplateSpec

TemplateSpec has exactly one responsibility: an executable document-specific
layout plan. It is produced after semantic and institution-policy decisions,
and is consumed by `load_template_spec()` / `generate_source_hwpx()`.

Its next runtime revision must retain these provenance references alongside the
existing layout data:

```json
{
  "semantic_contract_id": "...",
  "institution_design_id": "...",
  "institution_design_version": "v1"
}
```

Those references do not duplicate field meaning or institution defaults. The
current parser does not validate or persist them, so they are a defined runtime
gap, not a supported behavior.

## Canonical content and aliases

Canonical content is the existing renderer-facing `content.json` shape:

```json
{
  "template_id": "...",
  "fields": { "canonical_field_id": "value" }
}
```

Its allowed canonical field IDs come exclusively from the approved Semantic
Template Contract. A source-ingestion adapter first emits normalized extracted
information with source evidence; an agent maps that information to canonical
content. The source adapter does not assign semantic field IDs merely because
it recognizes text.

`alias_map.json` is optional input normalization for alternate human/source
names, choices, text rules, repeat expansion, and package metadata. It is not
the canonical field-identity source and is not intrinsically required for a
template to render. The current `prepare_hwpx_template_input()` requires an
alias-map metadata contract for final rendering; that is a runtime mismatch
with this product contract and must be changed in the next implementation task.

Required validation is performed against the Semantic Template Contract before
rendering. It rejects a missing or unresolved required `CONTENT` value; an
optional value may be absent, and an explicitly empty value is valid only when
the relevant content type permits it. `확인 필요` is unresolved, never a final
value for a required field.

## Examples

- [weekly report TemplateRequest](../../tests/fixtures/template-contracts/weekly-report.template_request.json)
- [weekly report Semantic Template Contract](../../tests/fixtures/template-contracts/weekly-report.semantic_contract.json)
- [edudoc Institution Design Contract](../../tests/fixtures/template-contracts/edudoc.institution_design.json)
- [existing executable TemplateSpec](../../tests/fixtures/template-spec/weekly_report.template_spec.json)

The examples demonstrate only currently materializable `title`, `info_table`,
and `body_section` layout. They do not declare masthead or repeat support.
