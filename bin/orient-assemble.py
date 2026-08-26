# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# orient-assemble — CLI trampoline over claude-klabauter
# coordinator_core.orient_assemble (the computed-skill assembler for the
# shared cadence-parameterized orient spine). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b2-ceremony-start.md, chunk C1
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# pickup-assemble); see docs/plans/2026-07-23-dr-088-ladder-enforcement-
# layers.md for the ladder-registration discipline this mirrors.
#
# Subcommand:
#   brief --cadence {session|day|week}
#     Computes and returns the 8-key decision object (artifact/preflight/
#     gates/directives/judgment_points/decisions/narration/next_move) for the
#     named cadence. READ-ONLY — mutates nothing (coordinator_core.orient_assemble
#     never performs a mutating action itself; every mutation is returned as a
#     directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   2 — usage error (malformed arguments, missing/unknown --cadence value).
#   3 — transport failure (the engine root unresolvable, coordinator_core import
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
    sys.exit(run_target("orient-assemble", sys.argv[1:]))
