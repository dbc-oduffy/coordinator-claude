# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""orphan-branch-sweep.py — read-only sweep classifying orphaned work/feature branches.

Enumerates user-owned work/* and feature/* branches in the current repo and
classifies each as CRITICAL (commits post-dating a merged PR), WARNING (open,
no PR, aged past threshold), or OK. Emits JSON lines (or text) to stdout;
never mutates branches, refs, or PRs. Sweep logic lives claude-klabauter-side in
coordinator_core.ops.orphan_branch_sweep; this file is a thin trampoline.
"""
# merged PR (CRITICAL), is an open branch with no PR and a branch-name date
# Bash-4 note: the retired bash implementation guarded on BASH_VERSINFO[0]<4
# of this file as a BASH_VERSINFO<4 exemplar is now stale (flagged, not fixed
from __future__ import annotations

import os
import sys

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.orphan_branch_sweep import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    # ORIGINAL script's own "Exits 0 always" posture, rather than mapping to a
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"orphan-branch-sweep.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"orphan-branch-sweep.py: coordinator_core.ops.orphan_branch_sweep not importable: {exc}",
            file=sys.stderr,
        )
        return 0
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
