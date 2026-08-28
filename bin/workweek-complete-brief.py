# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/workweek-complete-brief.py — thin CLI wrapper over
coordinator_core.workweek_complete.brief.

Purpose: `commands/workweek-complete.md` Step 0.95 invokes the bareword,
settings-home-installed entrypoint
`"${COORDINATOR_SETTINGS_HOME:-...}/bin/workweek-complete-brief"` — the
`workweek_complete` assembler's read-only compute half
(`coordinator_core/workweek_complete/brief.py`) computes the whole
mechanical spine of the weekly release ceremony (week-changelog gap
backfill, guard-sweep battery, staleness checks, version-consistency,
archive/reset directives) but, prior to this file, had no bareword
`coordinator/bin/` CLI trampoline through which it was reachable outside a
Python REPL. This file is that trampoline: direct-import variant (mirrors
`coordinator/bin/autonomous-verb.py` over `workday_complete.autonomous_verb`
and `coordinator/bin/pickup-assemble` over `pickup_assemble`), forwarding
argv verbatim to the module's own `main(argv)`.

Only `brief` is wired to a bareword CLI here — unlike `workday-complete-
assemble`'s `brief`/`apply` pair, `workweek-complete.md` never names an
"apply" verb: every ceremony mutation dispatches as a `directives[]` entry
naming an existing atomic CLI directly (Step 16's `/merge-to-main`, the
guard-sweep fixes, etc.), read and executed by the EM inline rather than
through a second assembler-owned mutation pass. `coordinator_core.
workweek_complete.apply` exists on disk but is not named by any doctrine
surface today — this trampoline does not front it; see this file's own
spec-backlink survey before adding one.

Usage:
    python3 workweek-complete-brief.py

Exit code and stdout/stderr are exactly
`coordinator_core.workweek_complete.brief.main`'s.

Spec backlink: DoE-claude coordinator/commands/workweek-complete.md § Step 0.95
Spec backlink: claude-klabauter coordinator_core/workweek_complete/brief.py

Negative-spec: does NOT parse or reinterpret argv itself — `brief.main`
today accepts none (mirrors `workday_complete.brief`'s CLI shape); this
wrapper is argv passthrough only, never a reimplementation of the compute.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    from pathlib import Path

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3

    from coordinator_core.workweek_complete.brief import main as _brief_main

    return _brief_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
