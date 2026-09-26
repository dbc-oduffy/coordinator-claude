# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-schema-registry-sync.py — SSOT drift gate over the schema registry.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.verify_schema_registry_sync. Checks that every
schemas/*.yaml carrying an applies_to: has a corresponding query --type
recognised by bin/query-records.js at runtime, so a new schema wired into
schemas/ but forgotten in query-records.js TYPE_TO_GLOB fails loudly instead
of silently drifting. Consumer: SSOT drift verification at cadence/CI gates.
"""
from __future__ import annotations
# Adding a new schema without wiring it into query-records.js TYPE_TO_GLOB

import os
import sys


def _resolve_plugin_root() -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import data_root

    return str(data_root("schemas").parent)


def _resolve_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-schema-registry-sync: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(
            f"verify-schema-registry-sync: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        plugin_root = _resolve_plugin_root()
    except RuntimeError as exc:
        print(
            f"verify-schema-registry-sync: schemas dir resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.verify_schema_registry_sync", [plugin_root] + (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-schema-registry-sync: coordinator_core.ops.verify_schema_registry_sync "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
