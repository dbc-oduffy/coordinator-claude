# pickup-assemble — CLI trampoline over claude-klabauter
# coordinator_core.pickup_assemble (the computed-skill assembler for
# `/pickup`'s branch inventory). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/archive-stamp-cli): a plain in-process function
# call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-23-computed-skills-pickup-beachhead.md, chunk A2
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# session-claim-cli); see docs/plans/2026-07-23-dr-088-ladder-enforcement-
# layers.md for the ladder-registration discipline this mirrors.
#
# Subcommand:
#   brief <artifact-path> [--decisions <json>] [--json]
#     Computes and returns the five-key decision object (artifact/preflight/
#     gates/directives/judgment_points) for the named handoff/memo/spinoff
#     artifact. READ-ONLY — mutates nothing (coordinator_core.pickup_assemble
#     never performs a mutating action itself; every mutation is returned as a
#     directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   1 — business failure (artifact unreadable/absent-and-not-archived, claim
#       held by a live peer, addressee mismatch without override) — the
#       returned decision object still carries the failing gate's full detail.
#   2 — usage error (malformed arguments, malformed --decisions JSON).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or no enclosing git worktree) — this trampoline's own
#       transport failure, distinct from any business exit code.

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("pickup-assemble", sys.argv[1:]))
