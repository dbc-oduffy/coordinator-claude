
from __future__ import annotations

import os
import sys


def main(argv: "list[str] | None" = None) -> int:
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        claude_klabauter_root = require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"cmd-autorun-guard.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1


    try:
        from coordinator_core.cli_entry import run_op_main
    except ImportError as exc:
        print(
            f"cmd-autorun-guard.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.cmd_autorun_guard", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"cmd-autorun-guard.py: coordinator_core.ops.cmd_autorun_guard not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
