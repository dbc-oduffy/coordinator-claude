"""plan-assemble.py — CLI trampoline over the engine's coordinator_core.plan_assemble
(route-selected residue for plan assembly, and future plan-assemble subcommands).

Direct-import variant (template-variant #1, mirrors coordinator/bin/
baton-assemble, pickup-assemble, and archive-stamp-cli): a plain
in-process function call after resolving the engine root, no cc_invoke/IPC
hop.

Contract: coordinator/docs/wiki/computed-skills.md (sibling coordinator-claude repo)
Spec backlink: pln-plan-assemble-brief-route-the-2d016a,
chunk C2
Registration seam: a new engine capability registers by shipping a thin
bin/ trampoline over an in-process coordinator_core module — same shape
as every other direct-import CLI in this tree (baton-assemble,
pickup-assemble, archive-stamp-cli, session-claim-cli).

Subcommands:
  [brief] [--route plan|spec-dispatch]
    Computes and returns the route-selected residue decision object for
    the resolved plan/brief surface, wrapped in the shared decision-object
    envelope. READ-ONLY — mutates nothing.
    FALLTHROUGH: a bare invocation with no subcommand token briefs.

Exit codes (locally scoped to this CLI, NOT inherited — see the
contract's own § Exit-code contract):
  0 — OK.
  1 — business failure (e.g. no applicable route/residue).
  2 — usage error (malformed arguments).
  3 — transport failure (the engine root unresolvable, coordinator_core
      import failure, or an unresolvable content root).
"""


# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("plan-assemble", sys.argv[1:]))
