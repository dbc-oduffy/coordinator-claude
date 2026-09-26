# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workweek-trail-scope.py — Step 7 prelude for /workweek-complete.

CLI trampoline over claude-klabauter coordinator_core.ops.workweek_trail_scope. Reads the
workstream-complete review-trail records for the current week and computes the
narrowed scope for the Staff Engineer reviewer: unreviewed_week_SHAs union
cross-segment-seam SHAs (file paths touched by >= 2 distinct trail segments). Writes a
session-keyed shard state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
so concurrent weekly gates never clobber each other's scope.
"""
#   state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
#   HEADER_FILE — path to state/week-changelog/HEADER.md (required)
#   1 - business failure (missing/unparseable HEADER_FILE, review-coverage-core.py

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
        print(f"workweek-trail-scope.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"workweek-trail-scope.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.workweek_trail_scope", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "workweek-trail-scope.py: coordinator_core.ops.workweek_trail_scope "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
