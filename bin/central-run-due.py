# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
central-run-due.py — CLI trampoline over claude-klabauter coordinator_core.ops.central_run_due.

Surfaces a "central learn-lessons run due (by VOLUME)" nudge when [universal]
entries accrued since the last COMPLETE central run exceed a threshold. Companion
to the date-based lesson-triage-recheck marker: a fixed cadence over-runs in
quiet weeks and under-runs in busy ones. This bounds the floor ADAPTIVELY —
busy periods cross the threshold sooner. Read-only; surfaces, never dispatches.

Output: a single `CENTRAL_RUN_DUE` line on stdout when over threshold; an
informational under-threshold / no-baseline line on stderr otherwise. Exit 0
always (it is a nudge, not a gate) — surfaced by /workday-start Step 1.75.
Optional positional arg overrides the volume threshold.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape.
This is NOT the legacy polyglot shape the paragraph here used to claim — it is
the pure-Python-with-`.cmd` shape. On Windows the co-located
`central-run-due.cmd` wins via `PATHEXT` when invoked as a bareword, so the
shebang is never read there; on macOS/Linux `python3` is the right
interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash —
git-bash DOES honor the shebang and would exec-127 with no `python3` present.
See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md
§ Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not here).

Port source: this file's own pre-port bash body (109 lines).
Ported logic + tests: coordinator_core/ops/central_run_due.py (claude-klabauter),
    co-located coordinator_core/ops/test_central_run_due.py (pytest).
Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_run_op_main():
    """Resolve the engine root and import `run_op_main` (DR-276: routes the op
    in-process through `coordinator_core.cli_entry` rather than a plain
    `_import_main()` + `sys.exit(op_main(argv))` tail, so any path the op
    declares via `declare_write` becomes a session scope-touch claim instead
    of an unclaimed orphan at the `scoped_git_commit` sink)."""
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"central-run-due: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(f"central-run-due: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(0)
    try:
        code = run_op_main("coordinator_core.ops.central_run_due", sys.argv[1:])
    except ImportError as exc:
        print(f"central-run-due: coordinator_core.ops.central_run_due not importable: {exc}", file=sys.stderr)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
