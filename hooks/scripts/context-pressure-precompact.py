#!/usr/bin/env python3
"""PreCompact(*) naked-Python direct port of `context-pressure-precompact.sh`
(W4b, recipe § 2.6). NOT a SessionStart hook — PreCompact fires mid-session,
not at boot, so this stub is exempt from the AC8 boot-race fast-path
constraint that governs `session-init.py`/`project-orientation.py`'s
Claude-klabauter-root resolution (recipe § 4).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the engine repo, hand it the raw stdin payload, let it write the
two bridge files. The engine repo owns the port LOGIC
(`coordinator_core.hooks.context_pressure_precompact.run`). The engine is
imported and run IN-PROCESS — no bash, no `python3 -m` subprocess re-spawn —
mirroring `preuse-write-dispatch.py`'s
`_resolve_claude_klabauter_root()` -> `sys.path.insert` -> direct-call shape exactly
(same helper name/body, copied verbatim per that file's own precedent).

Contract:
  stdin   — PreCompact hook JSON (session_id, transcript_path, …)
  stdout  — NOTHING. Not because PreCompact output is ignored: it is not.
            `decision: "block"` / `continue: false` REFUSE the compaction, and
            `newCustomInstructions` rewrites the summarizer's prompt. We decline
            both surfaces deliberately.
  exit 0  — ALWAYS, unconditionally, on every code path including every
            resolve/import/run failure. This is load-bearing, NOT incidental:
            a non-zero exit from a PreCompact hook BLOCKS the compaction, on all
            five paths (manual, auto, reactive, precomputed, fork). The published
            hooks reference says exit 2 does not prevent compaction; measured
            against claude v2.1.274, it does. So the ordinary habit of exiting
            non-zero on failure would, here, silently strand a session at its
            context ceiling. Our entire product is the on-disk sentinel +
            state-snapshot side-effect, or a silent no-op.

Graceful degradation — REQUIRED: any failure to resolve/import/run the
engine repo falls through to fail-open silent no-op (exit 0, no stdout, no
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
        return 0  # fail-open: engine repo unresolvable on this machine

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

    return 0  # non-zero here BLOCKS the compaction — see the Contract note


if __name__ == "__main__":
    sys.exit(main())
