# Exit codes (HARDENED per the 2026-07-17 porter-brief addendum A3/A3b — mirrors
#   3 — TRANSPORT failure: engine-root resolution or
# Spec backlink: tasks/2026-07-16-clean-slate-recon (BIG_PORT Wave B, item verify-coverage)

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
        print(f"verify-coverage: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"verify-coverage: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    try:
        code = run_op_main("coordinator_core.ops.verify_coverage", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-coverage: coordinator_core.ops.verify_coverage not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    return code


if __name__ == "__main__":
    sys.exit(main())
