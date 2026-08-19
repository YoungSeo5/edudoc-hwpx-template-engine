# Task: Hancom native page QA discovery

## Status

DONE

## Parent system contract

`docs/product-workflow-contract.md`

## Contract authority

Mode: `REVISE`

This task may revise candidate QA for self-authored `one_page_report` templates
only, adding an optional native page-count evidence gate. It preserves all
rendering, approval, and external-source extraction behavior.

## Goal

Discover Hancom Automation through its COM ProgID and discover any installed
Automation security module through `HKCU\Software\HNC\HwpAutomation\Modules`.
When the module is available, use the native engine to validate a declared
template page count. When it is unavailable, report that state without
guessing executable paths or treating XML as page evidence.

## Completion criteria

1. No Hancom executable path or security-module name is hardcoded.
2. Discovery distinguishes Automation absent, security module absent, and
   native page validation available.
3. A required native page check fails candidate QA when native validation is
   unavailable or the observed count differs.
4. Documents without a native-page requirement retain existing QA behavior.
