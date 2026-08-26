# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workweek-trail-scope.py — Step 7 prelude for /workweek-complete.

CLI trampoline over claude-klabauter coordinator_core.ops.workweek_trail_scope. Reads the
workstream-complete review-trail records for the current week and computes the
narrowed scope for the Staff Engineer reviewer: unreviewed_week_SHAs union
cross-segment-seam SHAs (file paths touched by >= 2 distinct trail segments). Writes a
session-keyed shard state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
so concurrent weekly gates never clobber each other's scope.
"""
# workweek-trail-scope.py — Step 7 prelude for /workweek-complete.
#
# CLI trampoline over claude-klabauter coordinator_core.ops.workweek_trail_scope. Reads
# the workstream-complete review-trail records for the current week and
# computes the narrowed scope for the Staff Engineer reviewer:
#
#   staff_eng_scope = unreviewed_week_SHAs ∪ cross-segment-seam SHAs
#
# A "segment" is the sha_range of one trail record (one workstream-complete
# review). Cross-segment seams are file paths touched by ≥2 distinct segments.
#
# Output: writes a session-keyed shard
#   state/review-trail/.weekly-reviewer-scopes-<TIMESTAMP>-<SID_SHORT>.json
# with shape:
#   { "staff_eng": [sha...], "staff_eng_seam_files": [path...], "mechanical_workers": "full" }
#
# Session-keyed append-only (not a singleton overwrite): two concurrent
# /workweek-complete weekly gates each write their own shard rather than
# clobbering a shared filename. Consumers select the most-recent shard for
# their own session (falling back to the newest shard overall) — see
# coordinator/commands/workweek-complete.md § Step 7 read logic.
#
# Fail-loud on any error.
#
# Env:
#   HEADER_FILE — path to state/week-changelog/HEADER.md (required)
#
# Exit codes:
#   0 - success
#   1 - business failure (missing/unparseable HEADER_FILE, review-coverage-core.py
#       business error propagated verbatim, git-log failure, unresolvable
#       session id, scope-shard write failure) — see the claude-klabauter module's own
#       docstring for the full negative-spec.
#   2 - transport failure: the engine root / coordinator_core.ops.workweek_trail_scope
#       could not be resolved/imported. Kept distinct from exit 1 (this script's
#       own contract is fail-loud on any error, never silent exit 0 — unlike
#       coordinator-auto-push's best-effort/never-block posture).
#
# Spec backlink: coordinator/commands/workweek-complete.md § Step 7 prelude
# C2 extraction backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2
# Singleton→session-keyed-shard backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2 (concurrency fix)
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# Rename backlink (.sh -> .py, naked-Python cutover): docs/plans/2026-07-21-bash-clean-slate-residual-migration.md
# bin/-residency backlink (lib/ -> bin/ port): docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the run-op runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, the session-keyed
    scope shard this CLI writes is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"workweek-trail-scope.py: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"workweek-trail-scope.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.workweek_trail_scope", sys.argv[1:])
    except ImportError as exc:
        print(
            "workweek-trail-scope.py: coordinator_core.ops.workweek_trail_scope "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
