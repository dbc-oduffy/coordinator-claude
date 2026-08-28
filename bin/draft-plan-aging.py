# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""draft-plan-aging.py — CLI trampoline over the claude-klabauter draft-plan staleness
detector.

Flags plans stuck in status:draft for >=14 days with no real-work commit on
their declared scope and no active baton in state/handoffs/, so
/workday-start and /workweek-start can surface abandoned drafts. Prints one
`STALE: <file> (...)` line per stale draft to stdout and exits non-zero when
any are found.
"""
# draft-plan-aging.sh — CLI trampoline over claude-klabauter
# coordinator_core.ops.draft_plan_aging (mechanized draft-plan staleness
# detector: status:draft + age>=14d + no real-work commit on scope + no
# active baton in state/handoffs/).
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
#
# Filename note: `.sh` is KEPT (not dropped, unlike coordinator-auto-push /
# handoff-gate-aging) — three live callers hardcode the `.sh` suffix
# (workday-start.md, workweek-start.md, stamp-plan-status-on-ship.integration.test.sh)
# and dropping it would require repointing all three for zero functional
# benefit; the polyglot shebang mechanism works identically regardless of
# filename suffix.
#
# Usage:
#   draft-plan-aging.sh <plan-path>       # single-file check
#   draft-plan-aging.sh <directory>       # scan *.md files (one level)
#
# Output: one `STALE: <file> (...)` line per stale draft plan, to stdout.
# Exit codes:
#   0 — no stale draft plans found
#   1 — one or more stale draft plans found (fail loud)
#   2 — internal error (missing path, bad frontmatter, unparseable date,
#       git-log failure, or unresolvable handoff-read failure) — business
#       code owned by coordinator_core.ops.draft_plan_aging
#
# Transport-failure exit code (this trampoline's own — NEVER returned by the
# claude-klabauter op itself, so it can never collide with the op's 0/1/2 business
# codes above; per porter-brief addendum § 3b, this is a fail-loud
# gate/validator script whose callers (workday-start, workweek-start) branch
# on 0/1/2, so claude-klabauter-link failure gets a DEDICATED code rather than reusing
# business code 2 or silently degrading to 0 — mirrors
# verify-dist-publish-repo-sync.py's identical resolution):
#   3 — engine-root resolution failed, or coordinator_core.ops.draft_plan_aging
#       was not importable
#
# Spec backlink: DoE-claude:pln-continuity-artifact-staleness--bec61c § Design Fix #2, § Chunks C1
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
# Port of: draft-plan-aging.sh (DoE b5a4192c, 2026-07-20)

from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"draft-plan-aging.sh: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"draft-plan-aging.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    try:
        code = run_op_main("coordinator_core.ops.draft_plan_aging", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"draft-plan-aging.sh: coordinator_core.ops.draft_plan_aging not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    return code


if __name__ == "__main__":
    sys.exit(main())
