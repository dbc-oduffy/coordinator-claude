# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
#   CROSS_REPO_INBOX_DIR=/some/tmpdir workday-start-cross-repo-memo-surface.py
#   CROSS_REPO_INBOX_DIR — override inbox directory (default: cross-repo/inbox/ at
#   MOCK_TODAY           — override today's date (ISO-8601, e.g. "2026-06-15") for

from __future__ import annotations

import os
import sys

def _resolve_run_op_main():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here. This is an on-demand /workday-start-time
    surfacer, not a per-commit hot path, but the direct-import shape is still
    correct: there is no reason to add a second subprocess/JSON-RPC hop for a
    plain function call.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import — this op declares no writes (pure read/print), so
    this changes nothing behaviorally, but keeps every operator CLI on the one
    recording seam uniformly.
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
        print(
            f"workday-start-cross-repo-memo-surface.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            "workday-start-cross-repo-memo-surface.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main("coordinator_core.ops.workday_start_cross_repo_memo_surface", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "workday-start-cross-repo-memo-surface.py: "
            f"coordinator_core.ops.workday_start_cross_repo_memo_surface not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
