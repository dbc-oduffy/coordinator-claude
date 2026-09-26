# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
#   Module-level (coordinator_core.ops.generate_exec_summary.main), UNCHANGED
#         (per PORTER-BRIEF-ADDENDUM.md § 3b "best-effort/never-block").
#   - Does NOT add a cockpit-contract entity or bump CONTRACT_VERSION (anti-scope).

from __future__ import annotations

import os
import sys

GENERATES = [
    {
        "artifact": "docs/exec-summary.md",
        "stamp_key": "generated",
        "sources": ["coordinator_core/ops/generate_exec_summary.py"],
    },
]


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
        print(f"generate-exec-summary: engine-root resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"generate-exec-summary: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main("coordinator_core.ops.generate_exec_summary", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"generate-exec-summary: coordinator_core.ops.generate_exec_summary not importable: {exc}",
            file=sys.stderr,
        )
        return 0
    return code


if __name__ == "__main__":
    sys.exit(main())
