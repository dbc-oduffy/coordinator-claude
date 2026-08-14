# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-weekly-staleness.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_weekly_staleness.

Computes how stale the weekly `/workweek-complete` release cadence is, by
reading `state/week-changelog/HEADER.md` for the prior-week reset commit SHA
and the "Week starting" date, then comparing commit distance and calendar
distance against fixed thresholds (>=5 days AND >=15 commits => STALE; one
of the two => MILD; neither => FRESH; unparseable/absent HEADER.md or
outside a git repo => UNKNOWN).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Usage:
  check-weekly-staleness.py

Output: exactly one line — STALE / MILD / FRESH / UNKNOWN — to stdout.
Exit code: always 0 (informational — callers decide whether to surface the
signal), matching the original bash oracle's convention. On a CLAUDE_KLABAUTER_ROOT
resolution/import failure this trampoline follows the SAME never-block
convention: prints UNKNOWN and exits 0, rather than failing loud, because
the ported op is purely informational (never a gate).

Spec backlink: archive/specs/2026-05-04-workweek-cadence-split.md § Trigger Doctrine
Port of: coordinator/bin/check-weekly-staleness.py (bash body retired on cutover; see git log)
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _resolve_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    a bare `main` import, so any paths the op declares become a session
    scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    # Never-block convention (matches the original bash's `echo UNKNOWN; exit 0`
    # short-circuits): a resolution/import failure prints UNKNOWN and exits 0,
    # rather than failing loud like a gate/config-writer trampoline would.
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(f"check-weekly-staleness.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print("UNKNOWN")
        sys.exit(0)
    except ImportError as exc:
        print(
            f"check-weekly-staleness.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        print("UNKNOWN")
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.check_weekly_staleness", sys.argv[1:])
    except ImportError as exc:
        print(
            f"check-weekly-staleness.py: coordinator_core.ops.check_weekly_staleness not importable: {exc}",
            file=sys.stderr,
        )
        print("UNKNOWN")
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
