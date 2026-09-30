# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# workday-complete-backfill-scan.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.workday_complete_backfill_scan (skipped-workday
# backfill detector — TSV rows of days with commits but no daily-summary
# record). Finish-strangler port (DR-047/DR-059): the bash implementation
# (391 lines — global-fallback scan, per-machine gap predicate, exclusive-
# commit main-exclusion escape hatch, dangling-defer guard) has been fully
# ported to coordinator_core/ops/workday_complete_backfill_scan.py (co-located
# pytest: test_workday_complete_backfill_scan.py). This file is now a thin
# DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
# (DoE owns contract/generator, claude-klabauter owns engine).
#
# Exit codes (this trampoline):
#   0 — claude-klabauter-link (transport) failure: the engine root unresolved or
#       coordinator_core.ops.workday_complete_backfill_scan not importable.
#       This scanner only ever feeds a nudge (`/workday-start` Step 1.85) or
#       an auto-backfill fan-out (`/workday-complete` Step 3.5) — never a hard
#       ceremony gate — so a transport failure degrades to exit 0, loud on
#       stderr, per the porter addendum's best-effort/never-block posture
#       (rule 3b). Distinct from the op's own business exit codes below.
#   0/1 — the op's own business exit code, passed through unchanged once the
#       import succeeds: see workday_complete_backfill_scan.py's own Usage
#       docstring / module docstring for its 0/1 contract (0 = success
#       including the healthy empty-output case; 1 = CLI usage error or cwd
#       not a git repo with COORDINATOR_ROOT unset).
#
# Spec backlink: coordinator-content-repo:pln-bash-polyglot-clean-slate-full-5c71ee
# Prior bash implementation: see git log (workday-complete-backfill-scan.py,
# 391 lines, retired on this cutover)

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.workday_complete_backfill_scan import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"workday-complete-backfill-scan: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            "workday-complete-backfill-scan: "
            f"coordinator_core.ops.workday_complete_backfill_scan not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
