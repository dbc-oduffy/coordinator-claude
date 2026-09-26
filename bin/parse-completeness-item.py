# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import os
import sys

_TRANSPORT_FAILURE_EXIT = 2


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"parse-completeness-item: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAILURE_EXIT
    except ImportError as exc:
        print(
            f"parse-completeness-item: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT

    try:
        code = run_op_main("coordinator_core.ops.parse_completeness_item", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"parse-completeness-item: coordinator_core.ops.parse_completeness_item not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_EXIT

    return code


if __name__ == "__main__":
    sys.exit(main())
