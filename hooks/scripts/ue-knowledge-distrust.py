#!/usr/bin/env python3
"""SessionStart(startup|clear|compact) naked-Python port of
the retired bash SessionStart hook of the same shape.

W4b bash-to-naked-python-hook-migration cohort, recipe section 2.5
(doctrine repo: scratch/subagent-sandbox/bash-to-python-migration/W4a-sessionstart-recipe.md):
naked-Python DIRECT PORT.

The doctrine plane owns only this thin PLUMBING stub (same DR-047 transport-seam carve-out as
`preuse-write-dispatch.py` / `coordinator-reminder.py` / `project-rag-detect.py`):
resolve the claude-klabauter engine, call its detect+gate+banner function IN-PROCESS,
relay stdout/stderr. Claude-klabauter owns the LOGIC
(`coordinator_core.hooks.ue_knowledge_distrust.run`) -- the bounded
`.uproject` search, the per-project plugin-gating settings.json read/decide,
and the UE PROJECT DETECTED banner text. No bash, no `python3 -m` subprocess
re-spawn for THIS hook's own logic -- the claude-klabauter op's own bootstrap write/merge
logic (`_run_bootstrap`) is a native-Python port of `claude-ue-bootstrap.py`'s
write/merge logic (C5: retired the prior `["bash", script, cwd]` subprocess
spawn this hook used to make on the session-hot-path); `claude-ue-bootstrap.py`
itself survives as a doctrine-plane-owned manual entrypoint for bootstrapping other
project dirs by hand, not as something this hook ever subprocess-invokes.

Contract (mirrors the bash hook it replaces):
  stdin   -- SessionStart JSON payload (not required; this hook only needs
             cwd, and reads it from the process cwd exactly as the bash
             oracle did via `$(pwd)`, not from the payload) -- drained anyway
             so the harness never sees a broken pipe, matching
             project-rag-detect.py's convention.
  stdout  -- the UE PROJECT DETECTED banner text, or NOTHING when no
             `.uproject` was found (silent exit, matches the bash oracle)
  stderr  -- operator-facing bootstrap-status lines (override written /
             override skipped), or NOTHING
  exit 0  -- always (SessionStart hooks MUST exit 0 unconditionally; this
             hook fails open on any resolve/import/run error, identical
             philosophy to preuse-write-dispatch.py's fail-open ALLOW)

Graceful degradation -- REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine falls through to fail-open silent exit 0 (no stdout, no
stderr). A missing sibling engine must never brick session start on a UE
repo -- identical philosophy to every other Shape-P1 stub in this cohort.

NOT WIRED: the 2026-07-15 PM directive (full-kill-keep-fast-orientation)
removed all boot-time guardrail/reminder/detector SessionStart hooks except
the orientation cache injector (see hooks.json's SessionStart block) -- this
stub, and the bash hook it replaced, are both orphaned with no hooks.json
registration.
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
    # This hook needs only cwd (exactly as the bash oracle used `$(pwd)`, not
    # the SessionStart JSON payload) -- but SessionStart hooks are invoked
    # with a JSON payload on stdin regardless of whether the hook consumes
    # it; drain it so the harness never sees a broken pipe (matches
    # project-rag-detect.py's convention).
    try:
        sys.stdin.read()
    except Exception:
        pass

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open silent exit -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks.ue_knowledge_distrust import run
    except Exception:
        return 0  # engine unimportable -> fail-open silent exit

    # PLUGIN_ROOT: the bash oracle derived this from
    # `${BASH_SOURCE[0]}/../..` (hooks/scripts -> plugin root). Historically
    # passed to the claude-klabauter op so it could locate the retired bash bootstrap script;
    # claude-klabauter's `_run_bootstrap` (C5) now natively ports that write/merge logic
    # in-process and keeps this parameter only for call-site compatibility
    # (unused). Kept here too, mirroring coordinator-reminder.py's
    # capability-catalog.md path convention.
    # __file__ parents: [0]=scripts [1]=hooks [2]=coordinator (plugin root).
    plugin_root = str(Path(__file__).resolve().parents[2])

    try:
        result = run(os.getcwd(), plugin_root)
    except Exception:
        return 0  # any engine failure -> fail-open silent exit

    for line in result.stderr_lines:
        try:
            sys.stderr.write(line)
            sys.stderr.write("\n")
        except Exception:
            pass

    if result.banner:
        # Write raw bytes, not sys.stdout.write() -- on Windows, text-mode
        # stdout translates LF to CRLF, which would diverge byte-for-byte
        # from the bash oracle's LF-only heredoc output (golden-diff parity
        # requirement, matches coordinator-reminder.py's convention).
        sys.stdout.buffer.write(result.banner.encode("utf-8"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
