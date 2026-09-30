# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
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
