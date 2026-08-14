"""Stop-hook shim — unrouted-sizing nudge.

Deliberately carries NO shebang: the hooks.json registration invokes this file
through an explicit `python3 -c ... runpy.run_path(...)` wrapper, so the file is
never exec'd directly and an `#!/usr/bin/env python3` line would be dead weight
that trips the P0 Windows guard (`test_posix_exec_assumptions_baseline.py`,
`env_shebang`). The grandfathered sibling shims predate that ratchet; do not
copy their first line, and do not widen the baseline to admit this one.

The doctrine plane owns only this thin PLUMBING shim: resolve the sibling engine, hand it the
raw Stop payload, and convert its verdict into the documented Stop-hook block
channel. The engine owns the DETECTION LOGIC
(`coordinator_core.hooks.nudge_unrouted_sizing.op`).

Per DR-118 (`docs/decisions/DR-118-doe-resident-transport-seam-is-a-pointer.md`),
a doctrine-plane-resident transport seam contains a pointer only: resolve, hand over,
translate, degrade unconditionally at every step — no fail-open policy, no
detection policy of its own. This shim demonstrably satisfies that rule; DR-118
walks its body line by line as the ruling's own conformance example.

Why the transport lives here rather than in the engine: a Stop hook speaks to
Claude by writing stderr and exiting 2 (exit 0 ends the turn silently). That is a
process-level contract with the harness, not a decision the engine should hold —
the op returns *whether* to speak, this shim decides *how*.

Contract:
  stdin   — Stop JSON (session_id, transcript_path, cwd, stop_hook_active, agent_id…)
  stderr  — the nudge text, on fire only
  exit 2  — nudge fires (blocks the stop; stderr is shown to Claude)
  exit 0  — every other path, including every failure path

Graceful degradation — REQUIRED: any failure to resolve/import/run the sibling
engine falls through to exit 0. An unresolvable sibling engine must never wedge
a session's ability to end its turn, so there is no failure mode here that exits
non-zero. The op is additionally self-limiting (honours
`COORDINATOR_UNROUTED_SIZING_NUDGE_OFF=1`).

Wiki: docs/wiki/coordinator-tripwires.md § NUDGE-UNROUTED-SIZING

PERFORMANCE — this fires on EVERY turn-end of every EM session in the fleet.
Stay near-free: stdin read + JSON parse is the entire pre-engine cost budget.
No process spawns, no filesystem probes, no settings-home lookup of its own
(the `_engine_root` import above already handles cross-machine resolution —
reuse it, do not re-derive a path), no imports beyond what this module and
its sibling shim already import. A future editor adding "just one more check"
before the `m.op(payload)` call is adding that cost to every turn-end in the
fleet, not just this one.

Executable body: shared with the sibling `nudge-harness-directive-dispatch.py`
shim via `_engine_root.run_stop_hook_pointer_shim` — the two shims' bodies
differed in zero executable statements except the imported engine module
name, so that shared body is parameterised on the module name within the
existing `_engine_root.py` seam rather than duplicated here or split into a
new cross-hook module (DR-047/DR-118 declines a families-spanning shared-
transport module; see that function's docstring for the full contract).
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
    return _run_stop_hook_pointer_shim("nudge_unrouted_sizing")


if __name__ == "__main__":
    sys.exit(main())
