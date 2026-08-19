# Task: TEMPLATE_CREATE authoring-v2 (section-based)

## Status

READY

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task MAY revise only:

- TEMPLATE_CREATE stages D through I (layout design, common/per-document
  elements, template_spec authoring, HWPX draft generation, fixed/content
  boundary determination), for the self-authoring sub-path only;
- unresolved decision #5, by concretizing the `TemplateSpec`/layout contract
  for the self-authoring sub-path only. This task does NOT resolve #5 at the
  repository/system-contract level — it defines the contract for this
  sub-path's implementation, nothing wider;
- the `TemplateSpec` schema and the `generate_source_hwpx()` /
  `build_separation_rules()` implementation in
  `core/adapters/hwpx_template_authoring.py`.

Decisions #6 (self-authored vs. external-source fixed/content timing) and #11
(long-term ownership of "authoring" inside `core/adapters/`) are read as
context but are NOT resolved by this task. Both stay exactly as currently
recorded in `docs/product-workflow-contract.md`'s registry; this task's
implementation is consistent with that existing record (the self-authored
path keeps declaring FIXED/CONTENT before QA, as it already did) but does not
newly settle either question at the repository level.

This task MUST NOT revise:

- DOCUMENT_RENDER stages M through W;
- approved-template promotion semantics;
- source-based external-HWPX semantic extraction behavior
  (`hwpx_content_separator.py`, `hwpx_semantic_classifier.py`);
- `skills/hwp-skill/`;
- the existing approved `templates/institutions/edudoc/주간업무보고서`
  (not used as a design source, not modified);
- Notion, GitHub, Slack, Drive, HTTP, or MCP integration.

Any revision to the parent system contract (`docs/product-workflow-contract.md`
itself) requires a separate follow-up task — this task's allowed-file scope
does not include it. See "Known inconsistency" below.

## Goal

Replace the fixed "heading paragraph + one two-column table" authoring shape
with a section-based `TemplateSpec` that expresses a document's structure
(`title` / `info_table` / `body_section`, in order) as data, apply
`docs/hwpx-layout-baseline.md`-sourced page/style values carried in that same
spec, and materialize one 주간업무보고서 candidate preview HWPX for human
review.

## References

Required:

- `docs/product-workflow-contract.md`
- `docs/hwpx-layout-baseline.md`
- `docs/template_spec_redesign_analysis.md`
- `docs/agent-policies/minimal-abstraction.md`
- `docs/agent-policies/task-scoped-testing.md`

Reference precedence:

- `docs/product-workflow-contract.md` is the current system contract, with one
  known exception: its F/G stage entries and registry items #5/#11 currently
  describe an earlier flat design (`heading` + `fields` with top-level scalar
  `page_margins_mm`/`heading_align`/`heading_size_pt`/`table_width_mm`/
  `table_border_weight`/`footer_page_number`) as "구현됨"/"해결". This task
  supersedes that design in code. Updating those entries is out of this
  task's file scope (see "Known inconsistency").
- `docs/template_spec_redesign_analysis.md` is historical design analysis.
  Its materializer-capability findings (`create_document.py` cannot express
  baseline layout; authoring requires direct `hwpx`-library calls) remain
  valid evidence. Its `group: "A" | "B"` domain-model proposal remains
  superseded and MUST NOT be implemented.

## Scope

- remove the fixed single-shape assumption from `TemplateSpec` /
  `generate_source_hwpx()` / `build_separation_rules()` in
  `core/adapters/hwpx_template_authoring.py`;
- introduce a section-based `TemplateSpec`: ordered `sections[]` of type
  `title` / `info_table` / `body_section`, plus document-level `page` and
  `styles` (baseline-sourced layout values referenced by role from the spec
  data, not hardcoded as Python constants);
- materialize sections into HWPX via the `hwpx` library (direction unchanged
  from the existing code — each section type dispatches to the appropriate
  `hwpx` calls);
- generate FIXED/CONTENT separation rules from the same placement facts the
  generator produced, generalized across section types (not re-derived by
  re-searching text);
- migrate `tests/fixtures/template-spec/weekly_report.template_spec.json` and
  `tests/task_scoped/test_hwpx_template_authoring_weekly_report.py` to the new
  schema;
- produce one candidate/preview HWPX for 주간업무보고서 via the existing
  `qa_hwpx_template.py` pipeline, left unregistered (no `--approve`).

## Out of scope

- repeating/variable-cardinality sections (a "repeat_section" concept):
  completely excluded from this task — not in the schema, not in the parser,
  not in the generator, not even as a reserved-but-unimplemented type value.
  Allowed `section.type` values are exactly `title`, `info_table`,
  `body_section`. A future task designs a repeat mechanism from scratch if
  one is needed.
- masthead, bullet hierarchy, image slots, color, footer contact-line: not
  part of this task's section vocabulary.
- DOCUMENT_RENDER, renderer, separator, semantic classifier, QA/approval-flow
  changes.
- updating `docs/product-workflow-contract.md` (file-scope excluded; recorded
  as FOLLOW-UP).
- deleting `tests/fixtures/template-spec/quarterly_summary.template_spec.json`,
  which becomes unreferenced once the flat-schema override test it feeds is
  replaced (not in this task's allowed-file scope; recorded as FOLLOW-UP).
- unrelated cleanup discovered during implementation.

## Fixed decisions

- `TemplateSpec` = what to place (`sections`, in order). `page`/`styles` = how
  it looks. Layout values live in the `template_spec` instance's own data,
  never hardcoded as Python constants inside `core/adapters/`.
- No `group` enum and no per-document-type code branch. Section `type` is the
  only structural switch, and its vocabulary is fixed to `title` /
  `info_table` / `body_section` for this task.
- Repeating/variable-cardinality sections are entirely out of scope (see
  "Out of scope") — not a reserved type, not a parser branch, not a generator
  branch. `section.type` accepts exactly `title` / `info_table` /
  `body_section`; any other value is a validation error.
- The 주간업무보고서 structure used in this task's example is decided from
  `docs/hwpx-layout-baseline.md`'s observed group-A pattern (numbered section
  heading + body paragraph) and `docs/template_spec_redesign_analysis.md` —
  not reverse-engineered from the existing approved
  `edudoc/주간업무보고서` template.
- Whether `body_section` content carries a baseline bullet marker is left
  unset (no default applied) — undecided pending human confirmation, not
  fabricated.
- No compatibility shim for the old flat `TemplateSpec` fields (`heading` as
  a bare top-level string, `page_margins_mm`/`heading_align`/
  `heading_size_pt`/`table_width_mm`/`table_border_weight`/
  `footer_page_number` as top-level scalars). Callers migrate to the new
  shape; there is no dual-path in this codebase.
- `template_spec`(`sections[]` 포함)은 최종 사용자가 손으로 작성하는 문서가
  아니라, 에이전트가 자연어 요청("문서 종류/목적 + 필요한 항목 수준") +
  `docs/hwpx-layout-baseline.md`를 근거로 생성하는 내부 authoring 산출물이다.
  그 생성 인터페이스 자체(부모 계약 미결정 #1/#2)는 이 task 범위 밖 FOLLOW-UP
  이며, 이 task는 그 산출물이 가질 내부 계약(스키마)과 그것을 소재화하는
  코드만 다룬다 — `tests/fixtures/template-spec/weekly_report.template_spec.json`은
  그 산출물의 예시로 사람이 대신 작성한다.
- self-authored 경로는 `source.hwpx` 생성 후 `hwpx_semantic_classifier`로
  FIXED/CONTENT를 재판정하지 않는다. `build_separation_rules()`가 생성 시점의
  배치 사실에서 만든 규칙이 모든 텍스트 노드를 커버해 기존
  `SeparationRules`/`_classify_node`의 legacy_role override로 확정되므로,
  구조 기반 fallback 분류 경로(external-source가 쓰는 것과 같은 코드)에는
  도달하지 않는다 — external-source 경로의 semantic classifier 자체는
  변경도, self-authored 경로에서의 호출도 없다.

## Inputs

- `docs/hwpx-layout-baseline.md` (baseline layout values, cited per use);
- the installed `hwpx` library's actual API surface, confirmed against
  `.venv/Lib/site-packages/hwpx` (`document.py`,
  `_document/ns/page.py`, `_document/ns/styles.py`, `oxml/table.py`);
- the current content of the 5 in-scope files.

## Outputs

- rewritten `core/adapters/hwpx_template_authoring.py` (section-based
  `TemplateSpec`, generator, rules builder);
- rewritten `tests/fixtures/template-spec/weekly_report.template_spec.json`
  (section-based example);
- rewritten `tests/task_scoped/test_hwpx_template_authoring_weekly_report.py`;
- `scripts/templates/author_hwpx_template.py`, changed only if the new
  function signatures require it (its calls are generic against stable
  function names, so no change is currently expected — verify during
  implementation rather than assume);
- a candidate/preview HWPX for `edudoc`/`주간업무보고서`, produced via
  `scripts/templates/author_hwpx_template.py`, left unregistered.

## Completion criteria

1. `TemplateSpec` expresses the order of `title`/`info_table`/`body_section`
   sections as data (a list), not as separate fixed Python-level slots.
2. `generate_source_hwpx()` contains no code path that assumes exactly one
   heading paragraph followed by exactly one two-column table; behavior
   follows `spec.sections`.
3. `page`/`styles` values from the `template_spec` instance are read at
   generation time (not hardcoded per-role Python constants) and are
   materially reflected in the generated `source.hwpx` (margins, font size,
   alignment, table border/width) — verified against the generated XML, not
   just schema presence.
4. FIXED/CONTENT separation rules are generated from the same placement facts
   `generate_source_hwpx()` produced, covering every section type used —
   not re-derived by re-searching rendered text.
5. New task-scoped tests covering criteria 1-4 pass; no test depends on the
   removed flat schema.
6. Running `scripts/templates/author_hwpx_template.py` against a
   section-based 주간업무보고서 `template_spec` produces a `candidate`-status
   `template.json` via the existing `qa_hwpx_template.py` pipeline, with no
   `AMBIGUOUS` semantic decisions and strict roundtrip validation passing.
7. `register_hwpx_template.py` is not invoked by this task; nothing is
   auto-approved.

## Known inconsistency (recorded, not fixed by this task)

`docs/product-workflow-contract.md`'s F/G stage entries and registry items
#5/#11 currently describe the flat design (superseded by this task) as
"구현됨"/"해결". This task's file scope does not include
`docs/product-workflow-contract.md`, so that inconsistency remains after this
task completes and must be corrected by a follow-up documentation task before
those entries are treated as accurate.

To be explicit: this task itself does not claim to resolve #11 (long-term
`core/adapters/` responsibility placement) or #6 (self-authored vs.
external-source fixed/content timing) at the repository level, regardless of
what the parent contract currently says. Only #5 is concretized, and only for
this sub-path.

## Discovered issues

### BLOCKER

- none initially

### FOLLOW-UP

- `docs/product-workflow-contract.md` F/G stage entries and registry #5/#11
  need re-sync to the section-based design (out of this task's file scope).
- `tests/fixtures/template-spec/quarterly_summary.template_spec.json` becomes
  unreferenced after this task (not in allowed-file scope to delete).
- masthead/bullet-hierarchy/image-slot/color/footer-contact-line schema
  support, if a future candidate needs them.
- a repeat/variable-cardinality section mechanism, if a future candidate needs
  one — this task leaves no reserved type or scaffold for it; it would be
  designed from scratch in its own task.
- `scripts/AGENTS.md`'s script table still does not list
  `author_hwpx_template.py` (pre-existing gap, out of this task's scope).

### OUT_OF_SCOPE

- none initially
