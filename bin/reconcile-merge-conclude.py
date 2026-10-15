# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
reconcile-merge-conclude.py — CLI trampoline over claude-klabauter
coordinator_core.ops.reconcile_merge_conclude.

Concludes a Step 0 reconcile merge that workday-start-step0-reconcile left
open (`RECONCILE-CONFLICT-OPEN`): refuses while conflict markers, unmerged
paths or foreign-staged paths remain, otherwise commits the merge. Thin
DoE-side (contract) trampoline over the claude-klabauter (engine) module, per DR-047.

Callers must invoke via the extensionless name or a resolved-interpreter
prefix, never a bareword `.py` through git-bash (see coordinator-content-repo's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out).

Exit-code convention: FAIL-LOUD gate script. An engine-root-resolution or
import failure is a hard error (exit 1), never a silent exit 0.

Exit codes (owned by the op module):
    0 — merge concluded.
    3 — a refusal; nothing written.
    1 — unexpected error (including this trampoline's own link failure).

DR-276: routed through `coordinator_core.cli_entry.run_op_main` so paths the
op declares via `declare_write` become a session scope-touch claim.
"""

from __future__ import annotations

import sys


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"reconcile-merge-conclude.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(
            "reconcile-merge-conclude.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.reconcile_merge_conclude", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "reconcile-merge-conclude.py: "
            f"coordinator_core.ops.reconcile_merge_conclude not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
