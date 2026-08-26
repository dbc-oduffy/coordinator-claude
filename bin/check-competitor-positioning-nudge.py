# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-competitor-positioning-nudge.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_competitor_positioning_nudge.

Absent-OR-empty-triggered competitive-positioning offer, shared by
/workweek-start Step 4.5 and /workweek-complete Step 4j so the trigger logic
(and its decline-memory) lives in exactly one place instead of two
byte-identical copies drifting independently.

spec-backlink: coordinator/DoE-claude:pln-per-repo-competitor-peer-self--f0b04e

Usage:
  check-competitor-positioning-nudge.py                  — print the nudge (or nothing) to stdout
  check-competitor-positioning-nudge.py --record-decline  — write/refresh the decline marker

Invokable three ways that all "just work": direct exec, `python
check-competitor-positioning-nudge.py ...`, and `bash
check-competitor-positioning-nudge.py ...` (callers in workweek-start.md /
workweek-complete.md invoke via `bash`). Line 2 is inert-Python-but-executable-sh:
under sh/bash it resolves `python3 || python || py` and `exec`s it; under Python
it's a no-op string.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root and import the DR-276 runner.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"check-competitor-positioning-nudge.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(f"check-competitor-positioning-nudge.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.check_competitor_positioning_nudge", sys.argv[1:])
    except ImportError as exc:
        print(f"check-competitor-positioning-nudge.py: coordinator_core.ops.check_competitor_positioning_nudge not importable: {exc}", file=sys.stderr)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
