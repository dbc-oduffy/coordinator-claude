# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# Port (DOE-PORT R1/BIG_PORT, template-variant #1 — direct-import, no registered

from __future__ import annotations

import os
import sys


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
        print(f"new-project-scaffold.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"new-project-scaffold.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.new_project_scaffold", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"new-project-scaffold.py: coordinator_core.ops.new_project_scaffold not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
