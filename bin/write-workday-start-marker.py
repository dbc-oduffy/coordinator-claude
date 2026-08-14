# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
write-workday-start-marker.py — CLI trampoline over claude-klabauter
coordinator_core.ops.write_workday_start_marker.

This is the real writer the day-cadence `d-workday-marker-write` directive
(`coordinator_core/orient_assemble/readers_health_reaper.py`) names as its
`cli`. Idempotently writes today's local date into
`state/.workday-start-marker`, resolved through the same state-root seam
`readers_health_reaper._read_marker_freshness` reads through
(`coordinator_core.ops.check_weekly_staleness._resolve_state_root`).

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not here).

Exit convention: this is a once-a-day bookkeeping write, never a gate — mirrors
central-run-due.py's fail-open shape (CLAUDE_KLABAUTER_ROOT/import resolution failure
degrades to a stderr note + exit 0, never a nonzero abort), NOT
capture-fan-out-threshold.py's fail-loud install-gate shape.

Spec backlink: DoE-claude:pln-computed-skills-b2-ceremony-st-e82420 § Reader-in-process port scoping, chunk C2d
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the marker path it
    declares becomes a session scope-touch claim. Without that, the marker
    write is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"write-workday-start-marker: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"write-workday-start-marker: coordinator_core.cli_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.write_workday_start_marker", sys.argv[1:])
    except ImportError as exc:
        print(
            f"write-workday-start-marker: coordinator_core.ops.write_workday_start_marker "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
