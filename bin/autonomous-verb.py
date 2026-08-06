#!/usr/bin/env python3
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

Spec backlink: docs/plans/2026-07-24-b1-ceremony-complete-computed-conversion.md § C7

Negative-spec: does NOT parse or validate the toggle token itself — that branch lives
solely in `autonomous_verb.parse_toggle`; this wrapper never duplicates it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root  # noqa: E402

try:
    _REPO_ROOT = Path(resolve_colocated_claude_klabauter_root(__file__))
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.workday_complete.autonomous_verb import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
