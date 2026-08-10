# HWPX template routing rules

Root `AGENTS.md` points here for the complete HWPX template routing rule.

## Goal

Reuse an exact approved template when it exists. Create a new QA candidate only
when no approved template exists or the user explicitly requests
re-extraction.

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

## Required route

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
   from the institution, document type, and source contents.
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

Which formatting a placeholder must preserve (paragraph style, paragraph
margins, cell margins) is currently decided in four separate places, and the
contract exists for only one approved template. The single recorded contract
that replaces them is designed in
[HWPX 레이아웃 보존 계약 (설계)](hwpx-layout-context.md). That design is
planned, not implemented.

## Pipeline diagram

[HWPX 렌더링·QA 파이프라인 다이어그램](hwpx-render-pipeline-diagram.md) shows
how approved-template final rendering and candidate QA share input resolution
and the render/verify kernel described above.
