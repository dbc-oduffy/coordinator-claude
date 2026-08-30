# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/autonomous-verb.py — thin CLI wrapper over
coordinator_core.workday_complete.autonomous_verb.

Purpose: the bareword, settings-home-installed entrypoint `commands/autonomous.md`'s
`/autonomous [on|off]` invokes (`"${COORDINATOR_SETTINGS_HOME:-...}/bin/autonomous-verb"
$ARGUMENTS`). Forwards argv verbatim to the module's own `main(argv)` — which already
owns the full on/off/yes/no/stop token-to-action mapping and the sentinel-CLI dispatch
(see that module's docstring) — so this file is argv passthrough only, never a
reimplementation of the toggle logic.

Usage:
    python3 coordinator/bin/autonomous-verb.py [on|off|yes|no|stop]

Exit code and stdout/stderr are exactly `coordinator_core.workday_complete.autonomous_verb.main`'s.

Spec backlink: DoE-claude:pln-b1-ceremony-complete-computed--9ffa54 § C7

Negative-spec: does NOT parse or validate the toggle token itself — that branch lives
solely in `autonomous_verb.parse_toggle`; this wrapper never duplicates it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
        return 1

    from coordinator_core.workday_complete.autonomous_verb import main as _sub_main

    return _sub_main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
