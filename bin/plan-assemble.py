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

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("plan-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
