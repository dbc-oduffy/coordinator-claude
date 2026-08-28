# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workday-start-cross-repo-memo-surface.py — inbound cross-repo memo staleness surfacer.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.workday_start_cross_repo_memo_surface. Globs THIS
repo's cross-repo/inbox/ directory, parses frontmatter, filters to
status: open / status: in_progress memos, computes staleness, and emits one
line per qualifying memo for `/workday-start` Step 1.45 orientation. Emits
nothing when there are zero qualifying memos.
"""
# Filename note: the `.sh` suffix is KEPT (not dropped, unlike coordinator-auto-push)
# — three live callers hardcode the literal `.sh` name (coordinator/skills/workstream-
# start/SKILL.md, coordinator/commands/workday-start.md, coordinator/pipelines/
# workday-start-internals.md).
#
# workday-start-cross-repo-memo-surface.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.workday_start_cross_repo_memo_surface.
#
# Purpose: Glob THIS repo's cross-repo/inbox/ directory (receiver-inbound), parse
# frontmatter, filter to status: open / status: in_progress memos (skipping
# grandfathered pre-cutoff ones), compute staleness, emit one line per memo.
# Emits nothing if zero qualifying memos — callers may skip the section heading.
#
# Single-delivery-copy model: sender writes ONE dirty file into receiver's
# cross-repo/. This script surfaces memos awaiting THIS repo's EM action
# (status: open). Receiver flips status: open -> actioned in place via Edit +
# commit — no move.
#
# Usage:
#   workday-start-cross-repo-memo-surface.py
#   CROSS_REPO_INBOX_DIR=/some/tmpdir workday-start-cross-repo-memo-surface.py
#
# Environment:
#   CROSS_REPO_INBOX_DIR — override inbox directory (default: cross-repo/inbox/ at
#                          repo root). Used by smoke tests. Detect repo root via git
#                          if available, otherwise falls back to cwd.
#   MOCK_TODAY           — override today's date (ISO-8601, e.g. "2026-06-15") for
#                          age/staleness computation. Used by tests only.
#
# Exit codes: ALWAYS 0. This is a best-effort orientation surfacer, never a gate —
# an engine-root resolution failure or import failure degrades to a loud stderr
# note + exit 0 (never blocks /workday-start Step 1.45), matching the never-block
# posture of coordinator-auto-push (porter-brief-addendum § 3b: best-effort /
# advisory / never-block scripts degrade transport failure to exit 0, not a
# caller-facing error code). Emits nothing when no qualifying memos exist.
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
# Prior spec: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 3
# Migration spec: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# Port of: coordinator/bin/workday-start-cross-repo-memo-surface.py (bash oracle, 213 lines)
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).

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
        # Never-block posture (like coordinator-auto-push): an engine-root
        # resolution failure must not block /workday-start Step 1.45.
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
        # The ported op's main() always returns 0 internally (best-effort
        # surfacer, never a gate) -- no additional try/except needed here.
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
