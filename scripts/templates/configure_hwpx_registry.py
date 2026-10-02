#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.registry_config import (  # noqa: E402
    RegistryConfigError,
    connect_registry,
    initialize_registry,
    resolve_registry_root,
    save_registry_root,
    validate_registry_root,
)


def main(
    argv: list[str] | None = None,
    *,
    config_path: Path | None = None,
    package_root: Path = ROOT,
) -> int:
    parser = argparse.ArgumentParser(description="외부 HWPX template registry 설정")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="현재 registry 설정 조회")
    for name in ("connect", "init"):
        command = commands.add_parser(name, help="기존 registry 연결" if name == "connect" else "신규 registry 초기화")
        command.add_argument("--registry-root", required=True, type=Path, help="registry 절대 경로")
    args = parser.parse_args(argv)

    try:
        if args.command == "show":
            selected = resolve_registry_root(config_path=config_path, package_root=package_root)
        else:
            selected = validate_registry_root(args.registry_root, package_root=package_root)
            if args.command == "connect":
                connect_registry(selected)
            else:
                initialize_registry(
                    selected,
                    provision_source=ROOT / "templates" / "institutions" / "edudoc",
                )
            save_registry_root(selected, config_path=config_path, package_root=package_root)
    except (RegistryConfigError, OSError) as exc:
        print(json.dumps({"ok": False, "registry_root": None, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, "registry_root": str(selected), "error": None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
