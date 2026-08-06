#!/usr/bin/env python3
"""Stop-hook shim — harness-directive dispatch nudge.

DoE owns only this thin PLUMBING shim: resolve the sibling engine, hand it the
raw Stop payload, and convert its verdict into the documented Stop-hook block
channel. The engine owns the DETECTION LOGIC
(`coordinator_core.hooks.nudge_harness_directive_dispatch.op`).

Why the transport lives here rather than in the engine: a Stop hook speaks to
Claude by writing stderr and exiting 2 (exit 0 ends the turn silently). That is a
process-level contract with the harness, not a decision the engine should hold —
the op returns *whether* to speak, this shim decides *how*.

Contract:
  stdin   — Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id…)
  stderr  — the nudge text, on fire only
  exit 2  — nudge fires (blocks the stop; stderr is shown to Claude)
  exit 0  — every other path, including every failure path

Graceful degradation — REQUIRED: any failure to resolve/import/run the claude-klabauter
engine falls through to exit 0. An unresolvable sibling engine must never wedge
a session's ability to end its turn, so there is no failure mode here that exits
non-zero. The op is additionally self-limiting (once per session, honours
`stop_hook_active`, `COORDINATOR_HARNESS_DIRECTIVE_NUDGE_OFF=1`).

Wiki: docs/wiki/harness-directive-conflicts.md § Why prose alone has not held

Executable body: shared with the sibling `nudge-unrouted-sizing.py` shim via
`_engine_root.run_stop_hook_pointer_shim` — the two shims' bodies differed in
zero executable statements except the imported engine module name, so that
shared body is parameterised on the module name within the existing
`_engine_root.py` seam rather than duplicated here or split into a new
cross-hook module (DR-047/DR-118 declines a families-spanning shared-
transport module; see that function's docstring for the full contract,
including the two code-review findings (non-dict result, non-str "message")
that the shared body still guards against).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import run_stop_hook_pointer_shim as _run_stop_hook_pointer_shim  # noqa: E402
except Exception:
    # A hook script deployed WITHOUT its sibling _engine_root.py must still
    # fail-open rather than crash on import.
    def _run_stop_hook_pointer_shim(module_name: str) -> int:
        return 0


def main() -> int:
    return _run_stop_hook_pointer_shim("nudge_harness_directive_dispatch")


if __name__ == "__main__":
    sys.exit(main())
