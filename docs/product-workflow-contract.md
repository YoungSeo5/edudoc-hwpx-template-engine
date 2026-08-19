# Product workflow contract

## Authority

This is the authoritative product E2E contract. It owns workflow hand-offs,
artifact ownership, lifecycle semantics, and the agent/code boundary. It does
not claim that a declared contract is already implemented.

The schemas and detailed pre-authoring rules are owned by
[Template authoring contracts](contracts/template-authoring-contracts.md).
HWPX routing/package rules remain in
[HWPX template rendering policy](agent-policies/hwpx-template-rendering.md).
Observed reference-layout evidence remains in
[HWPX layout baseline](hwpx-layout-baseline.md).

## Product invariants

1. Document types are contract data, never Python document-type branches.
   Observed A/B groups are analysis aids, not a runtime enum.
2. Semantic meaning is declared before authoring. `section.type` is layout
   vocabulary and cannot determine FIXED/CONTENT meaning.
3. `approved` means final-renderable from complete canonical semantic content.
   Candidate round-trip QA alone is insufficient.
4. Candidate and approved storage never overlap.
5. The generic renderer executes location/layout and canonical-content
   contracts; it never infers purpose, requiredness, or semantic role.
6. Baseline observations, institution policy, document layout, and runtime
   support are different facts.

## Source-of-truth artifacts

| Artifact | Authoritative contents | Created by | Consumer | Canonical location |
|---|---|---|---|---|
| `TemplateRequest` | stated purpose, requested items, fixed text, reference scope, constraints | person/request layer | agent | candidate then approved package |
| Semantic Template Contract | canonical fields, roles, requiredness, cardinality, types | agent | planner, mapping, validator | candidate then approved package |
| layout baseline | observed evidence | reference analysis | person/agent | `docs/hwpx-layout-baseline.md` |
| Institution Design Contract | institution defaults, masthead policy, asset refs | institution/product policy | authoring planner | `templates/institutions/<institution>/_design/design.json` |
| executable `TemplateSpec` | concrete ordered document layout and provenance references | authoring planner | HWPX author | candidate then approved package |
| candidate | review HWPX, contracts, QA evidence | code | QA/human | `sandbox/template-candidates/<candidate_id>/` |
| approved package | final-renderable template and copied contracts | approval process | registry/renderer | `templates/institutions/<institution>/<document_type>/` |
| canonical content | `template_id` and canonical `field_id -> value` | agent/direct caller | validator/renderer | per-render `content.json` |

Schemas:

- [TemplateRequest v1](contracts/template-request.schema.json)
- [Semantic Template Contract v1](contracts/semantic-template-contract.schema.json)
- [Institution Design Contract v1](contracts/institution-design-contract.schema.json)
- [Document Family Layout Recipe v1](contracts/document-family-layout.schema.json)

## Responsibility boundary

| Actor | Responsibility | Must not do |
|---|---|---|
| person/request layer | state request and approve/reject reviewed candidates | encode physical HWPX layout as a requirement substitute |
| agent | decide semantic elements, requiredness, structure, applicable design policy, and source-to-field mapping | invent source facts or defer semantic decisions to renderer code |
| deterministic code | validate contracts, materialize layout, project declared roles to locations, validate content, render/validate HWPX, enforce lifecycle | infer a role from section type, field name, or visual guess |
| human reviewer | decide visual fidelity and explicitly approve | treat machine QA as visual approval |

## TEMPLATE_CREATE

```text
user request
  -> TemplateRequest
  -> agent judgment
  -> Semantic Template Contract
  -> Institution Design Contract + executable TemplateSpec
  -> deterministic source.hwpx authoring
  -> candidate + machine QA
  -> human visual review
  -> approval gate
  -> approved package
```

| Stage | Input -> output | Status | Contract |
|---|---|---|---|
| request capture | user request -> TemplateRequest | not implemented | no HWPX coordinates/XML IDs in request |
| semantic decision | request -> semantic contract | not implemented | declares all fixed elements and canonical content fields |
| baseline evidence | references -> observations | partially implemented | baseline is evidence, not automatic defaults |
| institution design | evidence/policy -> design contract | not implemented | policy may cite evidence but is not evidence |
| layout planning | semantic + design -> TemplateSpec | partially implemented | supports section plans and runtime-loaded `one_page_report` component recipes |
| authoring | TemplateSpec -> source HWPX + role locations | partially implemented | component plans are lowered to generic authoring sections; other family/layout capabilities remain unimplemented |
| candidate QA | source + locations -> candidate package | implemented | structural/package validation; a declared native page requirement is enforced only when Hancom Automation and its local security module are available |
| visual review | candidate -> approval/rejection record | not implemented | review evidence is required before approval |
| approval | complete candidate + explicit approval -> approved package | partially implemented | current registration does not enforce full approval gate |

### TemplateRequest and semantic contract

The request is saved as `template_request.json` in the candidate root. The
entry layer creates an opaque `cand_<uuid>` candidate ID. On approval the
request and semantic contract are copied unchanged into the approved package.

The semantic contract is the only source for:

- `CONTENT` field ID, description, requiredness, cardinality, and type;
- `FIXED_LABEL` exact label text; and
- `FIXED_TEXT` exact immutable text.

These three roles are the complete role vocabulary. `many` cardinality
expresses a future repeat need; it does not claim `repeat_section` runtime
support. Authoring must project roles declared by this artifact rather than
calculate them from `title`, `info_table`, or `body_section`.

### Baseline, design policy, TemplateSpec, and masthead

The baseline records observed reference facts. The Institution Design Contract
records product policy/defaults for new self-authored documents. It is stored
at `templates/institutions/<institution>/_design/design.json`; reusable logo
assets are stored once under `_design/assets/` and referenced by asset ID,
never base64-copied into a TemplateSpec.

Product policy is fixed: self-authored institution documents default to a
required masthead. A document-specific override is permitted only when the
referenced design contract permits it. `resolve()`
(`core/adapters/hwpx_authoring_resolve.py`) now materializes a required
masthead — a bordered logo-left/document-name/logo-right table with the logo
assets embedded as real `hp:pic` image objects (BinData + manifest, not text
glyphs) — when the Institution Design Contract's `masthead.default` is
`"required"` and states every logo/dimension/style property; it raises rather
than falling back to a plain title paragraph if any is missing.

TemplateSpec is the only document-specific executable layout plan. It carries
semantic-contract and institution-design ID/version references, but does not
duplicate semantic meaning or institution defaults. It supports ordered
`title`, `info_table`, and `body_section` sections, plus a runtime-loaded
`one_page_report` family recipe whose generic components lower to those same
authoring primitives. It rejects `repeat_section` and has no complex-table
(merged cell) materializer; `info_table` column widths follow the Institution
Design Contract's `label_width_ratio` rather than a fixed 1:1 split.

### Candidate and approval lifecycle

```text
candidate -- machine QA --> reviewed candidate
reviewed candidate -- visual approval + gate --> approved
```

Candidates exist only under `sandbox/template-candidates/<candidate_id>/` and
are never registry-visible. An approved package is stored only at
`templates/institutions/<institution>/<document_type>/`; the active revision's
immutable identity is `(institution, document_type, template_id)`.

The approval gate requires source HWPX, rendered sections and
placeholder/location mapping, machine-QA evidence, request/semantic/spec
contracts, design provenance, required-field/final-render metadata, recorded
human visual approval, and explicit `--approve`.

Current `qa_hwpx_template.py` allows arbitrary `--output-dir` and current
registration does not require all of these artifacts. A current `approved`
status is registry-approved only, not yet product-approved by this contract.
Enforcement is a defined implementation gap.

## DOCUMENT_RENDER

```text
approved template identity
  -> source/direct content
  -> format-specific ingestion
  -> normalized extracted information
  -> agent semantic mapping
  -> canonical content
  -> required validation against semantic contract
  -> generic renderer
  -> structural/layout validation
  -> caller-owned final HWPX output path
```

| Stage | Input -> output | Status | Contract |
|---|---|---|---|
| select | identity -> active approved package | partially implemented | current registry uses institution/document type exact match |
| ingest | source -> normalized extracted information | partially implemented | current formats: `.md`, `.markdown`, `.txt`, `.hwpx` |
| map | normalized information -> canonical content | partially implemented | current code fills only deterministic categories |
| validate | canonical content + semantic contract -> accepted/rejected | not implemented | requiredness comes from semantic contract |
| render | approved package + accepted content -> final HWPX | implemented core | generic location/layout executor |
| structural QA | final HWPX -> validation result | implemented | not a visual-quality claim |
| deliver | final path -> caller | local write implemented | output is caller `--output`; delivery integrations are out of scope |

### Ingestion, canonical content, aliases, and requiredness

Every format adapter emits normalized extracted information plus source evidence.
An agent maps that information to the approved semantic contract's canonical
field IDs. An adapter must not assign a semantic field simply because it parsed
text. The current HWPX adapter flattens to Markdown and loses table topology;
that is a known implementation gap. PDF, DOCX, HWP, XLSX, and image adapters
are not implemented.

Canonical content is the existing renderer-facing shape:

```json
{ "template_id": "approved-template-id", "fields": { "canonical_field_id": "value" } }
```

The semantic contract owns canonical identity and requiredness. `alias_map.json`
is optional input normalization for alternate names, choices, text rules,
repeat expansion, and package metadata. It is not canonical field identity and
is not inherently required for rendering. Current
`prepare_hwpx_template_input()` incorrectly requires alias-map metadata for all
final renders; the next runtime task must separate canonical render metadata
from optional aliases.

Required validation prevents final output with missing or unresolved required
content. `확인 필요` is unresolved. Optional content may be absent; an empty
value is allowed only where the semantic type permits it. Current direct
`content.json` rendering does not enforce this contract yet.

## Runtime implementation gaps fixed by this contract

1. Validate/persist request, semantic contract, design provenance, and visual
   approval evidence.
2. Change `generate_source_hwpx()` and rule construction to consume declared
   semantic elements instead of assigning roles from section types.
3. Load/validate `_design/design.json` and TemplateSpec provenance before
   implementing any unimplemented design materializer.
4. Enforce candidate root and approval-gate artifacts in candidate QA and
   registration.
5. Validate canonical required content before rendering and make aliases
   optional for renderability.
6. Replace Markdown-only HWPX flattening with normalized structural extraction,
   then connect agent mapping.

Existing generic rendering remains intact: it already executes placeholder
locations and recorded layout without document-type-specific Python branches.
