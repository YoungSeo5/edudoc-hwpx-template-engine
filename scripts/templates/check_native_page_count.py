#!/usr/bin/env python3
"""Run Hancom native page-count validation from the current Windows user session."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.adapters.hancom_page_count import validate_native_page_count  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hancom Automation native PageCount smoke test")
    parser.add_argument("--input", required=True, type=Path, help="candidate HWPX path")
    parser.add_argument("--required-pages", required=True, type=int)
    args = parser.parse_args(argv)
    result = validate_native_page_count(args.input, args.required_pages)
    discovery = result.discovery
    print(f"hancom_automation = {discovery.hancom_automation}")
    print(f"security_module = {discovery.security_module}")
    register_module_status = (
        "unavailable"
        if result.register_module_result is None
        else str(result.register_module_result).lower()
    )
    print(f"register_module = {register_module_status}")
    print(f"open = {'success' if result.open_succeeded else 'not_completed'}")
    print(f"page_count = {result.observed_pages if result.observed_pages is not None else 'unavailable'}")
    print(f"required_pages = {result.expected_pages}")
    print(f"native_page_validation = {'pass' if result.passed else 'fail'}")
    if result.reason is not None:
        print(f"reason = {result.reason}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
