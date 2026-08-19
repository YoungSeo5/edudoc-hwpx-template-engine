# Task: Institution Design Contract v1 (visual-policy resolution layer)

## Status

IMPLEMENTED (2026-08-18). Open decisions 1–6 were resolved by explicit human
instruction at implementation time (not re-derived by this document):
override allow-list is `size_pt`/`align` for text roles and `width_mm` for
table roles (Open decision 1); section↔role compatibility is enforced by
namespace separation (`defaults.styles` vs `defaults.table`), not a kind-tag
table (Open decision 2); the per-role property list implemented is exactly
Evidence's font_family/size_pt/color/bold/align plus the already-supported
optional line_spacing_percent/spacing_before_pt/spacing_after_pt/
indent_left_mm (Open decision 3); table cell typography is materialized by
setting `char_pr_id_ref` on each cell paragraph after `set_cell_text()`,
confirmed against the installed `hwpx` library (Open decision 4); `resolve()`
lives in `core/adapters/hwpx_authoring_resolve.py` (Open decision 5);
`institution_design_id`/`institution_design_version` provenance fields were
not added to `TemplateSpec` in this step (Open decision 6, deferred). See
`core/adapters/hwpx_authoring_resolve.py`, `core/adapters/hwpx_template_authoring.py`,
and `tests/task_scoped/test_hwpx_authoring_resolve.py` for the actual
implementation and its test coverage.

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task MAY revise only:

- the `defaults.styles` / `defaults.table` sub-shape of
  `docs/contracts/institution-design-contract.schema.json` (currently
  `{"type": "object"}` with no internal shape — this task defines that shape);
- the `TemplateSpec.styles` schema and `TemplateSpec` dataclass in
  `core/adapters/hwpx_template_authoring.py` (style-role references +
  document-specific overrides, replacing today's flat `{size_pt, align}` /
  `{width_mm, border_width_mm}` maps);
- the internal contract of a new `resolve()` step that turns an Institution
  Design Contract + TemplateSpec into a Resolved Authoring Contract;
- the internal contract of `generate_source_hwpx()`'s inputs (it consumes a
  Resolved Authoring Contract instead of raw `TemplateSpec.styles`).

This task MUST NOT revise:

- `docs/product-workflow-contract.md` itself. That document already declares
  the canonical Institution Design Contract location
  (`templates/institutions/<institution>/_design/design.json`) and its
  `required`/`document_override_allowed` masthead policy shape as of the
  `product-contract-foundation` task (DONE, 2026-08-18). This task adopts that
  decision; it does not re-decide it.
- `docs/contracts/institution-design-contract.schema.json`'s top-level
  required fields (`institution_design_version`, `institution`, `design_id`,
  `evidence_reference`, `defaults`, `masthead`) — only the internal shape of
  `defaults.styles`/`defaults.table` is in scope.
- `docs/contracts/template-authoring-contracts.md`'s contract-chain ownership
  statements.
- `docs/hwpx-layout-baseline.md` (evidence document — read-only input).
- the section-based authoring structure completed by
  `template-create-authoring-v2` (`sections[]` of `title`/`info_table`/
  `body_section`, in order). That task's completion is not reopened; this
  task adds a visual-policy resolution layer in front of the existing
  materializer dispatch, it does not redo structure materialization.
- `skills/hwp-skill/`, `templates/institutions/` template *data*, the
  renderer, separator, semantic classifier, or QA/approval scripts.
- any actual institution values (font family, brand color, masthead content).
  Those are private-submodule data decisions, not this task's output.

## Goal

Design (not implement) the missing visual-policy layer between the observed
`docs/hwpx-layout-baseline.md` and `generate_source_hwpx()`, so that every
visual property `generate_source_hwpx()` needs (font family, size, color,
bold, alignment, line spacing, paragraph spacing, indentation, table border,
cell padding, table label/value typography) is explicit, institution-decided,
and validated before authoring — never filled in by `hwpx` library skeleton
defaults or ad hoc Python constants.

## Problem statement

`TemplateSpec.styles` (as implemented by `template-create-authoring-v2`)
expresses only `{size_pt, align}` for text roles and `{width_mm,
border_width_mm}` for table roles. `generate_source_hwpx()` calls
`doc.styles.ensure_run(size=style.size_pt)` — no `color`, `font`, or `bold`
argument is ever passed. The `hwpx` library's `ensure_run()` /
`ensure_run_style()` treats every unpassed property as "don't care," which
lets it silently match and reuse an unrelated existing `charPr` (or clone the
skeleton's default `charPr` when creating a new one). Font family and text
color for every self-authored document are therefore decided by library
skeleton state, not by any institution policy — and no data contract exists
today for an institution to state that policy. `info_table` cell typography
has the same gap: `TemplateSpec.table_styles` has no label/value typography
fields, and `_materialize_info_table()` calls `set_cell_text(...,
preserve_format=True)` with no character-style argument at all.

Separately, `docs/product-workflow-contract.md` and
`docs/contracts/template-authoring-contracts.md` (written today by the
`product-contract-foundation` task) already declare that an "Institution
Design Contract" *should* exist at
`templates/institutions/<institution>/_design/design.json`, with a schema at
`docs/contracts/institution-design-contract.schema.json`. That schema and its
one example fixture (`tests/fixtures/template-contracts/edudoc.institution_design.json`)
exist, but `defaults.styles`/`defaults.table` are declared with no internal
shape (`{"type": "object"}`, accepts anything), no runtime code loads or
resolves `design.json`, and no `_design/` directory exists anywhere under the
`templates/institutions/` submodule. The contract is named but empty on both
the schema-detail and the resolve-into-authoring sides.

## Evidence / discovered failure

All of the following was confirmed by reading the actual current code, not
assumed:

1. `core/adapters/hwpx_template_authoring.py:453` —
   `_materialize_paragraph()` calls
   `doc.styles.ensure_run(size=style.size_pt)` only. No `color`, `font`,
   `bold`, `italic`, or `underline` argument is ever passed for any text
   role (`title`, `section_title`, `body`).
2. `.venv/Lib/site-packages/hwpx/oxml/document_parts.py:163-187`
   (`_run_style_predicate`) — `color`/`highlight`/`font_ref` are only
   compared `if spec.color is not None` / `if spec.font_ref is not None`.
   When `color=None`/`font=None` (today's call site), those checks are
   skipped entirely. The predicate matches on `(bold, italic, underline)`
   flags and `height` only. Any existing `charPr` with the right flags and
   height matches regardless of its `textColor`/`fontRef` — including a
   skeleton `charPr` with an unrelated color.
3. `.venv/Lib/site-packages/hwpx/oxml/header_part.py:230-281`
   (`ensure_char_property`) — when no existing `charPr` satisfies the
   predicate, a new one is created by `deepcopy`-ing `base_char_pr_id` if
   given, **or otherwise the first `<hh:charPr>` element found in the
   header** (`char_props.find(f"{_HH}charPr")`, i.e. effectively `id=0`ʼs
   element), then applying only the requested modifications on top. Since
   `generate_source_hwpx()` never passes `base_char_pr_id`, every newly
   created `charPr` for every role inherits **all unspecified properties**
   (color, font) from whichever `charPr` happens to be first in the
   skeleton document's header — this is the literal mechanism of the
   observed `#2E74B5` blue title/heading bug, confirmed at the library
   source level, not just observed as an output artifact.
4. `_materialize_info_table()` (`hwpx_template_authoring.py:466-479`) calls
   `table.set_cell_text(row_index, col, text)` with no character-style
   argument. `hwpx/oxml/table.py:711` (`set_cell_text`) defaults
   `preserve_format=True`, so cell text is written into whichever `charPr`
   the newly created table's cell paragraph already carries — again library
   state, not contract data. `TemplateSpec.table_styles` (`TableStyle`
   dataclass) has exactly two fields, `width_mm` and `border_width_mm`; no
   label/value typography field exists even at the schema level to carry a
   decision if one existed.
5. `templates/institutions/` (submodule) currently contains only
   `금융감독원/*` and `edudoc/주간업무보고서/` document-type folders (verified
   by directory listing) — no `_design/` directory exists for any
   institution.
6. Repository-wide search for `institution_design` / `design.json` / `_design`
   finds exactly four hits, all documentation/schema/fixture
   (`docs/contracts/template-authoring-contracts.md`,
   `docs/contracts/institution-design-contract.schema.json`,
   `docs/product-workflow-contract.md`,
   `tests/fixtures/template-contracts/edudoc.institution_design.json`). No
   `core/` or `scripts/` file references any of these names. Nothing loads,
   validates, or resolves an Institution Design Contract at runtime today.
7. `docs/hwpx-layout-baseline.md` already follows the "baseline = evidence"
   principle this task's brief asks for: it explicitly declines to pick a
   font family or brand color (`"확인 필요(어떤 색을 쓸지는 기관이 정할
   사항)"`, `"실제 색값 ... 그대로 가져오지 않는다"`) and records only the
   *pattern* (heading is a bold large headline weight; body is one of
   serif/gothic; accent color is a dark banner + light table pattern). No
   change to this document is needed or proposed by this task.

## Scope

- Define the internal shape of `defaults.styles` / `defaults.table` in
  `docs/contracts/institution-design-contract.schema.json` as a set of named
  **typography roles** and **table defaults**, each carrying every property
  `generate_source_hwpx()` needs (font family, size, color, bold, alignment,
  line spacing, paragraph spacing, indentation; table border, cell margin,
  label/value role references).
- Define the restructured `TemplateSpec.styles` shape: a section references a
  style **role** (an institution-defined name) plus an optional
  document-specific **override** object carrying only the properties this
  document wants to change.
- Define `resolve()` semantics: how an Institution Design Contract and a
  TemplateSpec combine into a **Resolved Authoring Contract** — priority
  order, per-property merge behavior, role-existence validation,
  section-type/role compatibility, and required-property completeness
  checking.
- Define failure semantics: what `resolve()` must reject, and that rejection
  happens before `generate_source_hwpx()` is ever invoked.
- Redefine `generate_source_hwpx()`'s responsibility contract: it consumes a
  fully resolved, no-null structure and passes every contract-owned property
  explicitly to `hwpx` library calls (so the `ensure_run_style` predicate gap
  in Evidence item 2 cannot silently reuse an unrelated `charPr`).
- Identify the storage split between schema (public repo) and actual
  institution values (private submodule), reconciled against the existing
  `product-contract-foundation` decision.
- List files likely to change in the next implementation task, and the
  purpose of each change.
- Specify what a task-scoped test for this layer must assert.
- Produce this task-contract document.

## Out of scope

- Any code change. `hwpx_template_authoring.py`,
  `weekly_report.template_spec.json`, the renderer, the separator, the
  semantic classifier, QA/approval scripts, and `skills/hwp-skill/` are not
  touched.
- Choosing actual institution values: font family, brand color, masthead
  content, logo assets. These remain `확인 필요` / unresolved until a human
  decides them for a real institution, in the private
  `templates/institutions/` submodule.
- Masthead materialization, bullet hierarchy, image slots, footer
  contact-line — same out-of-scope boundary `template-create-authoring-v2`
  already declared; this task's `defaults`/`resolve` design accounts for a
  future masthead policy shape (the schema already reserves a `masthead`
  object) but does not implement masthead rendering.
- Repeat/variable-cardinality sections — unchanged, still out of scope
  repository-wide.
- Any change to `docs/product-workflow-contract.md` or
  `docs/contracts/institution-design-contract.schema.json`'s top-level
  required-field list.
- Creating `templates/institutions/<institution>/_design/design.json` with
  real data — that file's *existence with real values* is private-submodule
  data work, not this (public-repo) task's output. This task defines the
  schema shape that file must satisfy.

## Current architecture

```text
docs/hwpx-layout-baseline.md (evidence, intentionally incomplete on
  font family / color)
        |
        | (no code path — read by humans only)
        v
tests/fixtures/template-spec/weekly_report.template_spec.json
  TemplateSpec.styles = { role_name: {size_pt, align} | {width_mm, border_width_mm} }
  (flat, document-instance-local; no institution layer; no font/color/bold
  field exists in the schema at all)
        |
        v
core/adapters/hwpx_template_authoring.py: generate_source_hwpx()
  doc.styles.ensure_run(size=style.size_pt)   <- color/font/bold never passed
  table.set_cell_text(..., preserve_format=True)  <- no cell typography arg
        |
        v
hwpx library (.venv/Lib/site-packages/hwpx):
  ensure_run_style() predicate ignores unset color/font -> matches/reuses
  unrelated existing charPr, or clones the header's first charPr (~id=0)
  for unspecified properties when creating a new one
        |
        v
candidate source.hwpx: title/heading color and font are whatever the
  HwpxDocument.new() skeleton happened to carry (#2E74B5 observed)
```

`docs/contracts/institution-design-contract.schema.json` and
`templates/institutions/<institution>/_design/design.json` are **named** in
`docs/product-workflow-contract.md` / `docs/contracts/template-authoring-contracts.md`
but are dead ends: the schema's `defaults.styles`/`defaults.table` accept any
object shape, no `_design/` directory exists in the submodule, and no
`core/`/`scripts/` code reads either. There is currently no code path from
"institution policy" to `generate_source_hwpx()` at all — the gap the task
brief describes is exactly this: `TemplateSpec` is the only layer that
actually feeds the generator, and it was never designed to carry institution
defaults or a role/override split.

## Target architecture

```text
reference HWPX
        |
        v
docs/hwpx-layout-baseline.md            (observed evidence — unchanged, read-only)
        |
        v  (human decision, cites evidence, is not evidence)
templates/institutions/<institution>/_design/design.json
  validated against docs/contracts/institution-design-contract.schema.json
  defaults.styles.<role>   = { font_family, size_pt, color, bold, align,
                                line_spacing_percent, spacing_before_pt,
                                spacing_after_pt, indent_left_mm? }
  defaults.table.<role>    = { border_width_mm, border_color, cell_margin_mm,
                                label_style_role, value_style_role }
  masthead                 = { default: required|none, document_override_allowed }
        |
        v
tests/fixtures/template-spec/weekly_report.template_spec.json
  (or its real successor)
  institution_design_id / institution_design_version   (provenance, already
    named as a required next-revision field in
    docs/contracts/template-authoring-contracts.md)
  sections[].style = "<institution role name>"
  sections[].style_override = { <optional per-document property overrides> }
        |
        v
resolve(institution_design, template_spec)
  -> Resolved Authoring Contract
     every section's style is a fully concrete, no-null property set;
     table roles are fully concrete; page settings are fully concrete
  -> raises before generation on any unresolved/undefined/incompatible role
        |
        v
generate_source_hwpx(resolved_contract)
  every doc.styles.ensure_run(...) call passes bold/italic/underline/color/
  font/size explicitly (no argument left at its "don't care" default) so the
  library predicate cannot match/inherit an unrelated charPr
  table cell runs get the same explicit treatment via label/value roles
        |
        v
candidate HWPX — every visual property traces to an institution decision
  or an explicit document override, never to hwpx skeleton state
```

Responsibility is fully separated: baseline records facts, the Institution
Design Contract records decisions, TemplateSpec records structure plus only
the deltas a specific document needs, `resolve()` is the single point where
"what does this section actually look like" becomes a total function (every
property present, nothing deferred to a library default), and
`generate_source_hwpx()` is a pure materializer that judges nothing.

## Fixed decisions

1. **Storage location is not re-decided by this task.** It is adopted as
   already declared by `product-contract-foundation`
   (`docs/product-workflow-contract.md`,
   `docs/contracts/template-authoring-contracts.md`, both DONE
   2026-08-18): schema in the public repo at
   `docs/contracts/institution-design-contract.schema.json`; actual
   institution data at `templates/institutions/<institution>/_design/design.json`,
   inside the private `templates/institutions/` submodule, with reusable
   assets under `_design/assets/` referenced by `asset_id` (never
   base64-copied into a TemplateSpec). This task found no conflict with that
   decision during investigation — `_design/` sits beside, not inside, the
   existing `<institution>/<document_type>/` folders, so it does not collide
   with candidate or approved-package storage, and it is submodule data like
   everything else under `templates/institutions/`, consistent with
   `templates/institutions/AGENTS.md`'s existing invariants.
2. **`title` and `section_title` are not two coincidentally-identical
   styles; they are two different names for what may be the same or
   different institution role.** The current fixture gives both
   `{size_pt: 16, align: left}` — value duplication, not shared reference.
   The redesigned schema requires every section to reference a named
   institution role; if an institution's document title and its section
   headings are meant to look identical, the TemplateSpec references the
   *same* role name for both rather than declaring two roles with copied
   values.
3. **Typography role vocabulary is derived from the existing section
   vocabulary, not invented ahead of demonstrated need** (Minimal
   Abstraction Policy condition 1: the two real uses already exist in
   `hwpx_template_authoring.py`). The roles a resolve step must support for
   this task's scope are exactly the ones the current three section types
   already reference:
   - `TitleSection.style` (document title)
   - `BodySection.heading_style` (section heading)
   - `BodySection.body_style` (body text)
   - `InfoTableSection` row label typography (new — currently unset)
   - `InfoTableSection` row value typography (new — currently unset)
   - `InfoTableSection.style` table-level layout (border/width/cell margin —
     already exists as `TableStyle`, extended with cell margin)
   No fourth "for future use" role is added.
4. **Table layout and table cell typography are separate concerns inside
   the same `table` default entry**, not merged into one object and not
   split into unrelated top-level namespaces. `defaults.table.<role>` owns
   `border_width_mm`/`border_color`/`cell_margin_mm` (layout) and
   `label_style_role`/`value_style_role` (typography, by reference into
   `defaults.styles`) — label and value cells are allowed to reference
   different typography roles, since `docs/hwpx-layout-baseline.md`
   observed exactly this pattern (label cells vs. content cells often
   differ in weight).
5. **A `TemplateSpec` section's `style_override` may only override
   properties of the role it references — it may not introduce a role the
   institution contract does not define, and it may not leave a required
   property permanently unresolved.** Overriding is a narrowing operation
   (this document's specific size/alignment/table width may differ from
   institution default), not a way to bypass institution policy for
   properties the institution has decided (e.g. a document cannot silently
   pick a font family the institution never approved) — whether *any*
   property may be document-overridden or only a fixed allow-list
   (size/align/table width, as `docs/hwpx-layout-baseline.md` §9 already
   anticipates for baseline-vs-document-type precedence) is listed under
   Open decisions below, since the two prior contracts do not settle it.
6. **`resolve()` never reads `docs/hwpx-layout-baseline.md` at runtime.**
   Baseline is evidence for a human writing `design.json`; it is not a
   fallback data source. If `defaults.styles` lacks a property `resolve()`
   needs, that is a `design.json` authoring gap to fix by editing
   `design.json`, never something `resolve()` compensates for by reading the
   baseline markdown or by falling back to an `hwpx`-library default.
7. **This task does not reopen `template-create-authoring-v2`'s completion.**
   Section-based structure materialization (`sections[]` of
   `title`/`info_table`/`body_section`, in order) remains done. This task
   adds a visual-policy resolution stage in front of the existing dispatch
   in `generate_source_hwpx()`; it does not change what gets materialized in
   what order, only what property values each materialization call receives.

## Open decisions

These require human confirmation before implementation begins:

1. **Override allow-list.** Should `style_override` accept any property of
   the referenced role (full override), or only a fixed subset (e.g. only
   `size_pt`/`align`/table `width_mm`, matching the
   precedent in `docs/hwpx-layout-baseline.md` §9's "document-type
   re-definition" list, which names size/placement/table-structure items but
   not font/color)? A full override risks a single document silently
   diverging from institution color/font policy; a restricted allow-list
   needs its exact member list decided.
2. **Section-type ↔ role compatibility enforcement.** Should `resolve()`
   maintain an explicit table of which role *kind* (title-like vs.
   body-like vs. table-label vs. table-value) each section field may
   reference, and reject a mismatch (e.g. `BodySection.heading_style`
   pointing at a role tagged as a table-value role)? Or is any role of the
   correct primitive shape (`text` vs. `table`) acceptable regardless of its
   institution-assigned name? The former catches authoring mistakes early;
   the latter is simpler and matches today's `_require_style()` behavior
   (kind-checked by shape only, e.g. `{size_pt, align}` vs. `{width_mm,
   border_width_mm}`).
3. **Exact property list per typography role.** The Evidence section lists
   the properties `generate_source_hwpx()` currently needs
   (font_family/size/color/bold/align) plus properties named in the task
   brief but not yet used by any current call site (line_spacing_percent,
   spacing_before_pt/spacing_after_pt, indentation — `hwpx`'s
   `apply_paragraph_format()` already accepts these, confirmed by reading
   `.venv/Lib/site-packages/hwpx/_document/ns/styles.py:297-337`, but
   `generate_source_hwpx()` does not call them today). Should this task's
   next implementation step resolve/require all of these now, or only the
   subset current code already sets (size/align), leaving
   line-spacing/paragraph-spacing/indent as a later FOLLOW-UP once a
   section type actually needs them? Doing all of them now is more complete
   but expands implementation scope beyond fixing the reported color/font
   bug.
4. **Table cell typography materialization API.** `hwpx`'s
   `set_cell_text()` has no character-style parameter in its current
   signature (confirmed by reading
   `.venv/Lib/site-packages/hwpx/oxml/table.py:711-758`). The likely
   approach — call `ensure_run()` for the label/value role, then set the
   resulting `char_pr_id_ref` on the cell's paragraph run after
   `set_cell_text()`, mirroring `_materialize_paragraph()`'s existing
   pattern — is not yet verified against the library at a written/tested
   call site. This is implementation-time verification, not a design
   decision, but it affects whether `defaults.table.<role>.label_style_role`/
   `value_style_role` can be materialized as designed; flagged so the next
   task does not assume without checking.
5. **Where the `resolve()` function/module lives.** Candidates: a new small
   adapter module (e.g. `core/adapters/hwpx_authoring_resolve.py`, in
   keeping with `core/AGENTS.md`'s "prefer a small adapter over a broad
   rewrite"), or a set of functions added directly to
   `hwpx_template_authoring.py`. Given `hwpx_template_authoring.py` is
   already ~590 lines covering parsing + materialization + separation-rule
   generation, a separate resolve module is the current lean, but this is
   an implementation-task decision, not fixed here.
6. **Whether `institution_design_id`/`institution_design_version`
   provenance fields become required on `TemplateSpec` in this same
   implementation step**, or whether resolve's institution-contract input is
   passed out-of-band (e.g. as a separate CLI argument to
   `author_hwpx_template.py`) for this first version and folded into
   `TemplateSpec` itself later.  `docs/contracts/template-authoring-contracts.md`
   already names these as required in TemplateSpec's "next runtime
   revision," which argues for doing it now; the counter-argument is
   scope growth beyond fixing the reported bug. Left open for the human
   reviewer.

## Candidate file locations

| Content | Location | Status |
|---|---|---|
| Institution Design Contract schema | `docs/contracts/institution-design-contract.schema.json` | exists (public repo); `defaults.styles`/`defaults.table` internal shape is this task's design output |
| Institution Design Contract example/fixture (not real data) | `tests/fixtures/template-contracts/edudoc.institution_design.json` | exists, currently empty (`defaults.styles: {}`); needs populated example once the internal shape is designed |
| Real institution Design Contract data | `templates/institutions/<institution>/_design/design.json` | does not exist yet; private submodule; out of this repo's authorship |
| Reusable design assets (logos etc.) | `templates/institutions/<institution>/_design/assets/<file>` | does not exist yet; private submodule; already named in `docs/contracts/template-authoring-contracts.md` |
| Resolve step implementation | new module, likely `core/adapters/hwpx_authoring_resolve.py` (see Open decision 5) | does not exist |
| Resolved Authoring Contract | in-memory result of `resolve()`; not proposed as a persisted file — it is a per-authoring-run structure, not a lifecycle artifact tracked in `docs/product-workflow-contract.md`'s artifact table | n/a |

This table confirms there is no conflict between the already-declared
schema/data split and this task's design — it narrows the schema's empty
`defaults.styles`/`defaults.table` shape and adds the resolve step that was
always the missing link, without relocating anything already decided.

## Expected schema responsibilities

**`docs/contracts/institution-design-contract.schema.json` (`defaults`
sub-object, extended):**

- `defaults.styles`: a map of role name → typography properties. Every role
  must state, at minimum: `font_family`, `size_pt`, `color` (hex),
  `bold` (bool), `align`. Properties from Open decision 3
  (`line_spacing_percent`, `spacing_before_pt`, `spacing_after_pt`,
  `indent_left_mm`) are added if that open decision resolves to "require
  them now."
- `defaults.table`: a map of table-role name → `border_width_mm`,
  `border_color`, `cell_margin_mm` (`{left, right, top, bottom}`),
  `label_style_role` (a name that must exist in `defaults.styles`),
  `value_style_role` (same).
- No property in either map may be silently defaulted by the schema itself
  (no JSON Schema `default:` keyword) — an institution that has not decided
  a value must omit the whole role or leave it absent, which `resolve()`
  then reports as unresolved (see Failure semantics), never as a schema-level
  fallback.

**`TemplateSpec.styles` (in `core/adapters/hwpx_template_authoring.py`,
restructured):**

- Each section's `style`/`heading_style`/`body_style` field becomes a
  reference to an institution role **name** (a string), not an inline
  `{size_pt, align}` object.
- An optional sibling `style_override` object may be present, containing
  only the properties this document wants to change from the institution
  default for that role (scope of allowed keys per Open decision 1).
- `InfoTableSection` gains `label_style_override`/`value_style_override`
  (optional) alongside its existing table-role reference, following the
  same override pattern.
- The dataclass-level validation removes today's `{size_pt, align}` vs.
  `{width_mm, border_width_mm}` shape-sniffing (`_parse_styles()`'s
  `is_text`/`is_table` branch) since `TemplateSpec` no longer carries full
  property sets — role names and (optional) partial overrides are the only
  shapes it parses.

## Resolve semantics

`resolve(institution_design, template_spec) -> ResolvedAuthoringContract`

1. **Load & validate** the Institution Design Contract against
   `institution-design-contract.schema.json`. A missing file, invalid JSON,
   or schema-invalid document fails resolve before any section is examined.
2. **Role lookup.** For every section's style reference (`style`,
   `heading_style`, `body_style`, table role, label/value role), look up the
   name in `institution_design.defaults.styles` / `.defaults.table`. An
   undefined role name is rejected — `resolve()` does not guess a nearest
   match.
3. **(If Open decision 2 resolves to "enforce") Kind/role compatibility
   check.** Reject a role reference whose declared kind does not match the
   section field's expected kind (e.g. a table-value role referenced from
   `TitleSection.style`).
4. **Override merge**, per matched role: start from the institution role's
   full property set, then apply the section's `style_override` (or
   `label_style_override`/`value_style_override`) property-by-property.
   Only properties explicitly present in the override replace the
   institution value; anything absent from the override keeps the
   institution default. An override key naming a property the role does not
   have, or (per Open decision 1, if restricted) a property outside the
   allow-list, is rejected.
5. **Required-property completeness check**, per resolved role: every
   property `generate_source_hwpx()` will consume (see Expected schema
   responsibilities) must be present and non-null after the merge. Any gap
   is reported by role name and missing property name — not silently left
   for the `hwpx` library to decide.
6. **Page resolve.** `institution_design.defaults.page` supplies page
   size/orientation/margins; `template_spec.page` (already required today —
   see `_parse_page()`) supplies this document's explicit
   values. Priority: **document-specific `template_spec.page` values are
   currently the only page source in the existing schema; if
   `defaults.page` also exists, template_spec wins for any key it states,
   institution default fills any key the template_spec section omits** —
   consistent with `docs/hwpx-layout-baseline.md` §9's stated precedence
   (`문서 유형별 명시 규칙 → 기관 layout-baseline → HWPX 생성기의 일반
   기본값`, translated to this contract chain as `template_spec explicit →
   institution default`, with no third "library default" tier ever reached).
7. **Table resolve**, analogous to §4/§5 but for `defaults.table.<role>`:
   border/cell-margin layout resolves the same override-merge way; the
   role's `label_style_role`/`value_style_role` are resolved recursively
   through steps 2–5 as ordinary typography roles.
8. **Output**: a `ResolvedAuthoringContract` whose every section-level style
   is a complete, concrete property set (no role names, no partial
   overrides, no missing properties) — structurally parallel to today's
   `TemplateSpec.sections` but with `TextStyle`/`TableStyle` replaced by
   fully-populated resolved equivalents carrying every property listed under
   Expected schema responsibilities.

Priority order, stated once explicitly: **institution default, overridden by
template-specific override where the template explicitly states one.**
Nothing overrides the template-specific override, and nothing beneath the
institution default (no `hwpx` library default, no baseline markdown value)
is ever consulted by `resolve()`.

## Failure semantics

`resolve()` raises (does not warn, does not substitute a default) on:

- Institution Design Contract file missing, unreadable, or schema-invalid.
- A `TemplateSpec` section referencing a style/table role name absent from
  `institution_design.defaults`.
- (If Open decision 2 enforces it) a role reference whose kind does not
  match the section field that references it.
- A `style_override` (or label/value override) containing a property key
  that does not exist on the referenced role, or — if Open decision 1
  restricts overrides — a property outside the allowed override list.
- Any role, after institution-default + override merge, still missing a
  property `generate_source_hwpx()` requires (this is the direct fix for
  today's silent `charPr` reuse: the *absence* of a color/font decision
  becomes a hard authoring failure instead of an implicit library choice).
- A page property required by `_parse_page()`'s existing required-key check
  (`left`/`right`/`top`/`bottom`) still missing after institution-default +
  template-spec merge.

`generate_source_hwpx()` must never be reached with an unresolved value.
Concretely, this means the authoring pipeline (`author_hwpx_template.py`)
gains a `resolve()` call between `load_template_spec()` and
`generate_source_hwpx()`, and a `resolve()` failure is reported the same way
today's `HwpxTemplateAuthoringError` failures are (a `{"ok": false, "stage":
"authoring", "error": ...}` JSON summary, per `scripts/AGENTS.md`'s existing
failure-reporting convention) — not a new failure-reporting shape.

`generate_source_hwpx()` itself is redefined to require its input's
properties to already be complete; it is not responsible for detecting or
reporting an incomplete contract (that is `resolve()`'s job) — it is only
responsible for passing every property it receives through to the `hwpx`
library call explicitly, with no call site left at an implicit "don't care"
default for any contract-owned property.

## Files likely to change

Implementation-task scope (not this task):

| File | Change purpose |
|---|---|
| `docs/contracts/institution-design-contract.schema.json` | Define `defaults.styles`/`defaults.table` internal shape (roles, required typography/table properties) |
| `tests/fixtures/template-contracts/edudoc.institution_design.json` | Populate example roles matching the new shape (still a fixture/example, not real institution data) |
| `core/adapters/hwpx_template_authoring.py` | Restructure `TemplateSpec.styles` parsing to role references + overrides; `generate_source_hwpx()` to accept a Resolved Authoring Contract and pass every property explicitly to `ensure_run()`/table calls |
| new `core/adapters/hwpx_authoring_resolve.py` (or equivalent — Open decision 5) | Implement `resolve()`: load institution design contract, merge with template spec, validate completeness, produce the Resolved Authoring Contract |
| `tests/fixtures/template-spec/weekly_report.template_spec.json` | Migrate `styles` to role references (breaking change to this fixture's shape, consistent with `template-create-authoring-v2`'s established "no compatibility shim" precedent) |
| `scripts/templates/author_hwpx_template.py` | Add a resolve step (and likely a new `--institution-design` / equivalent CLI argument) between `load_template_spec()` and `generate_source_hwpx()` |
| `tests/task_scoped/test_hwpx_template_authoring_weekly_report.py` and/or a new task-scoped test file | New tests for `resolve()` behavior (see Test requirements) |
| `docs/contracts/template-authoring-contracts.md` | Likely needs a short addition once `resolve()`/Resolved Authoring Contract exist as real code, to keep the "current runtime status" column honest — exact wording decided when implementation lands |

## Files that must not change

- `templates/institutions/` — any file under the submodule, in this task or
  its immediate implementation follow-up, without separate human sign-off on
  actual institution values.
- `skills/hwp-skill/`.
- `docs/product-workflow-contract.md` — unless a future, separately-scoped
  documentation task decides its artifact table needs a "current runtime
  status" update once `resolve()` ships; not this task's or its immediate
  follow-up's file scope.
- `docs/hwpx-layout-baseline.md`.
- The renderer, separator, and semantic classifier (`core/templates/hwpx_content_separator.py`,
  any `hwpx_semantic_classifier` module, `core/adapters/hwpx_template_renderer.py`)
  — this task's scope ends at candidate authoring, before `DOCUMENT_RENDER`.
- Any approved template, and `register_hwpx_template.py`.

## Test requirements

For the implementation task that follows this design (Task-Scoped Testing
Policy applies — each item below needs at least one new automated test that
fails pre-change and passes post-change):

1. `resolve()` returns a fully concrete contract when every referenced role
   exists in the institution design and no property is missing — asserted
   by checking the resolved structure has no `None`/missing property for
   every role a `title`/`info_table`/`body_section` spec references.
2. `resolve()` raises when a `TemplateSpec` section references a style role
   name absent from the Institution Design Contract.
3. `resolve()` raises when, after merging institution default + document
   override, a required property (e.g. `color`) is still absent — this is
   the regression test that directly encodes "no silent library default,"
   using a design contract that intentionally omits `color` for a role.
4. `resolve()` applies a document-specific `style_override` correctly: the
   overridden property differs from the institution default in the
   resolved output; every non-overridden property still equals the
   institution default.
5. A **regression test reproducing the originally reported bug**: author a
   candidate `source.hwpx` through the full `resolve()` →
   `generate_source_hwpx()` path with an institution design contract that
   declares an explicit `color` for the `title`/`section_heading` role
   (e.g. `#000000` or any institution-declared value that is *not* the
   `HwpxDocument.new()` skeleton's own default), then parse the generated
   `Contents/header.xml` and assert the `charPr` referenced by the
   title/heading run's `textColor` equals the institution-declared color
   exactly — not the skeleton's `#2E74B5` (or whatever the current skeleton
   default is at implementation time). This test must fail against
   pre-change code (today's `generate_source_hwpx()` never passes `color`)
   and pass post-change.
6. `InfoTableSection` label and value cells can resolve to different
   typography roles (asserted the same way — resolved contract shows
   different concrete properties for `label_style_role` vs.
   `value_style_role`).
7. Page resolve: a design contract's `defaults.page` value is used when
   `template_spec.page` omits it (if Open decision 6 keeps `defaults.page`
   in scope); `template_spec.page`'s existing required-key values continue
   to win when both are present.
8. `resolve()` rejects an override key that does not exist on the
   referenced role (or is outside the allow-list, if Open decision 1
   restricts it).

## Completion criteria

This design task (not the implementation task) is complete when:

1. This document exists at `docs/tasks/institution-design-contract-v1.md`
   and states Fixed vs. Open decisions explicitly, with no invented values.
2. The evidence for the reported bug is traced to specific, cited lines in
   both `core/adapters/hwpx_template_authoring.py` and the `hwpx` library
   itself (done above — items 1–4 under Evidence).
3. The storage-location question is answered by confirming/adopting the
   existing `product-contract-foundation` decision, with the submodule
   conflict check performed and recorded (done — Fixed decision 1).
4. The typography-role / table-layout-vs-cell-typography split is proposed
   using the repository's actual current section vocabulary, not an
   invented generic vocabulary (done — Fixed decision 3, Fixed decision 4).
5. `resolve()`'s semantics, priority order, and failure conditions are fully
   specified (done — Resolve semantics, Failure semantics).
6. `generate_source_hwpx()`'s narrowed responsibility (materialize only,
   never judge) is stated as an explicit target contract (done — Target
   architecture, Failure semantics closing paragraph).
7. No file outside `docs/tasks/institution-design-contract-v1.md` was
   modified by this task.
8. A human has reviewed and approved this design (see Human review gate)
   before any implementation task begins.

## Human review gate

Implementation must not begin until a person:

1. Confirms Fixed decisions 1–7 are acceptable as stated.
2. Resolves Open decisions 1–6 (override allow-list scope, role/section-type
   compatibility enforcement, exact per-role property list, table-cell
   typography materialization approach once verified, `resolve()` module
   location, and whether `TemplateSpec` provenance fields become required in
   this same step).
3. Explicitly authorizes a follow-up implementation task with its own
   contract-authority scope (per root `AGENTS.md`'s work-unit execution
   contract) to modify `core/adapters/hwpx_template_authoring.py`, add the
   `resolve()` module, and migrate the `weekly_report.template_spec.json`
   fixture.

No code in this repository has been modified as part of producing this
document.
