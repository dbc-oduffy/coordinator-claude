# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""check-machine-local-regeneratability.py — CLI trampoline over the claude-klabauter
machine-local registry regeneratability observer.

Post-hoc offer (always exits 0): reads the [regeneratability] TOML table from
the machine-local registry and flags session-accumulated entries that live
only in a gitignored *.local.toml with no tracked baseline or idempotent
regenerator, plus any coordinator-owned key absent from the table. Findings
go to stderr; silent on a clean registry.
"""
# bin/check-machine-local-regeneratability.py — Machine-local registry
# regeneratability observer, CLI trampoline over claude-klabauter
# coordinator_core.ops.check_machine_local_regeneratability.
#
# Purpose: POST-HOC OFFER (exit 0 always). Reads the [regeneratability] TOML table
# from the machine-local registry and flags:
#   (1) Any session-accumulated-must-survive-crash entry that lives ONLY in a gitignored
#       *.local.toml with no tracked baseline or idempotent regenerator — this is an
#       install-surface-completeness defect.
#   (2) Any coordinator-owned key absent from the [regeneratability] table
#       (unclassified-key warning).
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C1
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# Offer shape: exit 0 always; findings to stderr; silent on clean.
#
# Exit codes: 0 — always (offer-shaped observer; never blocks a caller).

import os
import sys


def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import, so any paths the op declares become a session
    scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        # Best-effort/never-block observer: a claude-klabauter-link failure degrades to
        # exit 0 (loud on stderr), matching this script's offer-shape posture —
        # it must never block /workstream-complete Step 2.95.
        print(
            f"check-machine-local-regeneratability: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            f"check-machine-local-regeneratability: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main("coordinator_core.ops.check_machine_local_regeneratability", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"check-machine-local-regeneratability: coordinator_core.ops.check_machine_local_regeneratability not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
