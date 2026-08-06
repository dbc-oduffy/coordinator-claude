#!/usr/bin/env python3
"""PreCompact(*) naked-Python direct port of `context-pressure-precompact.sh`
(W4b, recipe § 2.6). NOT a SessionStart hook — PreCompact fires mid-session,
not at boot, so this stub is exempt from the AC8 boot-race fast-path
constraint that governs `session-init.py`/`project-orientation.py`'s
Claude-klabauter-root resolution (recipe § 4).

DoE owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the claude-klabauter engine, hand it the raw stdin payload, let it write the
two bridge files. Claude-klabauter owns the port LOGIC
(`coordinator_core.hooks.context_pressure_precompact.run`). The engine is
imported and run IN-PROCESS — no bash, no `python3 -m` subprocess re-spawn —
mirroring `preuse-write-dispatch.py`'s
`_resolve_claude_klabauter_root()` -> `sys.path.insert` -> direct-call shape exactly
(same helper name/body, copied verbatim per that file's own precedent).

Contract:
  stdin   — PreCompact hook JSON (session_id, transcript_path, …)
  stdout  — NOTHING (PreCompact output is ignored by Claude Code — the legacy
            bash oracle never wrote to stdout either)
  exit 0  — ALWAYS, unconditionally, on every code path including every
            resolve/import/run failure. This hook has no advisory/deny
            surface to convey via exit code (unlike the PreToolUse dispatcher
            this mirrors) — its entire product is the on-disk sentinel +
            state-snapshot side-effect, or silent no-op.

Graceful degradation — REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine falls through to fail-open silent no-op (exit 0, no stdout, no
files written). A missing sibling engine must NEVER brick a compaction event
— identical philosophy to `preuse-write-dispatch.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0  # fail-open — cannot even drain stdin, nothing to do

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open: claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.context_pressure_precompact import run
    except Exception:
        return 0  # engine unimportable → fail-open, no-op

    try:
        run(raw)
    except Exception:
        # `run()` already contains its own errors (see its docstring), but a
        # bare backstop here matches the philosophy of every other Shape-P1
        # stub in this cohort: a hook body must NEVER be able to brick the
        # PreCompact event, no matter what regressed inside the engine.
        pass

    return 0  # PreCompact always exits 0 — no advisory/deny surface exists


if __name__ == "__main__":
    sys.exit(main())
