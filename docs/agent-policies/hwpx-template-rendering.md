# HWPX template routing rules

Root `AGENTS.md` points here for the source-based candidate extraction and
approved-template rendering subroutes.

The top-level TEMPLATE_CREATE and DOCUMENT_RENDER E2E contracts are owned by
[`docs/product-workflow-contract.md`](../product-workflow-contract.md).

## Scope and goal

This policy applies only when:

1. an approved template is being resolved for final rendering; or
2. an exact existing HWPX source is being extracted or re-extracted as a
   candidate template.

This policy does NOT define the full TEMPLATE_CREATE workflow.

When the user requests a newly authored template from natural-language
requirements, do not require an existing source HWPX and do not force the
request into the source-extraction route defined below.

That request follows the TEMPLATE_CREATE authoring path defined by
`docs/product-workflow-contract.md` and the active task contract. Once that
path's `generate_source_hwpx()` produces a `source.hwpx`, it has no attached
source to resolve — that is not a missing or guessed source, it is the
expected shape of this second entry point — and the result joins the same
candidate QA route this policy defines below.

For the source-based route covered by this policy, reuse an exact approved
template when it exists and create a QA candidate only when no approved
template exists or the user explicitly requests re-extraction.

## The agent MUST NOT

- recursively search `exports/`, `sandbox/`, references, or unrelated HWPX files
  to discover a template or guess which attachment the user meant
- create a candidate before calling
  `TemplateRegistry.find(institution, document_type)`
- regenerate an approved template merely because the user attached an example
- create a second template when the requested `template_id` conflicts with the
  approved template for the same institution and document type
- guess a missing source, institution, or document type, or ask the user to
  invent a new `template_id`
- overwrite an existing candidate directory
- write an unapproved candidate into `templates/institutions/` or change its
  status to `approved`
- claim that strict package validation proves visual fidelity or institution
  approval
- invent missing field values or silently fall back to generic `md2hwpx`
- require the user to repeat internal CLI commands or QA steps

## Required source-based route

1. Resolve only the exact attached source. If it is missing or ambiguous, ask
   for the file.
2. Obtain `institution` and `document_type`, then call
   `TemplateRegistry.find(institution, document_type)`. This checks only
   `templates/institutions/<institution>/<document-type>/template.json`.
3. If an approved template exists, reuse it and do not create a candidate.
4. If the user supplied a different `template_id`, report the conflict and stop
   until the user decides.
5. If no approved template exists, run
   `scripts/templates/qa_hwpx_template.py` in a new ignored
   `sandbox/template-candidates/` directory. Omit `--template-id` unless the
   user explicitly supplied one; the command derives a stable ASCII-safe ID
   from the institution, document type, and source contents. Separation
   classifies the whole document before writing any placeholder; if any text
   node remains `AMBIGUOUS`, the command exits 1 with `error_code
   "semantic_ambiguity"` and no placeholder map, sample content, or roundtrip
   output is produced (see Semantic classification below).
6. If the user explicitly requests re-extraction, create a separate candidate
   without modifying the approved template.
7. Convert legacy HWP to HWPX before candidate QA.

`qa_hwpx_template.py` must leave `template.json` as `candidate`, generate the
sample/test round-trip outputs, and strictly validate them. Human review is
required before any candidate is promoted.

Approved-template output uses
`scripts/templates/render_hwpx_template.py`. Candidate QA and approved-template
output are separate routes.

## Layout preservation

Placeholder layout is recorded as `layout-context-v1` and checked by the shared
`verify_recorded_layout()` boundary during separation, QA round-trip, and final
rendering. The implemented contract is documented in
[HWPX 레이아웃 보존 계약](hwpx-layout-context.md).

## Semantic classification

Before `separate_hwpx_template_content()` patches any XML, it classifies every
`<hp:t>` text node from document-level structural evidence
(`core/templates/hwpx_structural_observations.py`,
`core/templates/hwpx_semantic_classifier.py`) into one deterministic role:
`FIXED`, `CONTENT`, `MARKER_CONTENT`, or `AMBIGUOUS`. A leading symbol span
(e.g. `- 부제 -`, `* 설명`) is boundary evidence only; it becomes
`MARKER_CONTENT` solely when independent content evidence resolves it, and
never from position or symbol presence alone. The full decision set for the
document is written to `semantic_classification.json` before any placeholder
is written.

If any node remains `AMBIGUOUS`, separation stops before creating
`placeholder_map.json`, `content.sample.json`, or roundtrip output. The
candidate directory keeps only `source.hwpx`, `raw/`, the unpatched
`template/` copies, `template.review.md`, and `semantic_classification.json`.
`qa_hwpx_template.py` reports this as `error_code: "semantic_ambiguity"` with
the unresolved node list and a resolution skeleton, and exits 1. A human
completes that skeleton and passes it back via `--rules` to resolve the
remaining nodes on a later run; deterministic decisions already made cannot
be overridden.

Only nodes resolved as `CONTENT` or `MARKER_CONTENT` become placeholders;
`FIXED` text stays literal even when it carries a marker span.

## Repeat boundary

Candidate extraction reports structure and creates independent replacement
fields. It does not infer semantic repeat regions from an arbitrary document.
Only a human-reviewed `alias_map.json` `blocks` contract may declare a repeat
anchor, levels, and separators; the renderer then expands that declared source
structure for the supplied item count. A template without that contract follows
the ordinary non-repeat render path.

## Pipeline diagram

[HWPX 렌더링·QA 파이프라인 다이어그램](hwpx-render-pipeline-diagram.md) shows
how approved-template final rendering and candidate QA share input resolution
and the render/verify kernel described above.
