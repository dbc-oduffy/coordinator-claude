# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import os
import sys

def _import_runner():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"render-template: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"render-template: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        return 1

    try:
        code = run_op_main("coordinator_core.ops.render_template", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(f"render-template: coordinator_core.ops.render_template not importable: {exc}", file=sys.stderr)
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
