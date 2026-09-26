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
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: coordinator_core.cli_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main(
            "coordinator_core.ops.workday_start_cross_repo_memo_outbox_surface",
            (sys.argv[1:] if argv is None else argv),
        )
    except ImportError as exc:
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: coordinator_core.ops."
            f"workday_start_cross_repo_memo_outbox_surface not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
