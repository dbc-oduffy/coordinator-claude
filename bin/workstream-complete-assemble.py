# workstream-complete-assemble — CLI trampoline over claude-klabauter
# coordinator_core.workstream_complete (the computed-skill assembler for
# `/workstream-complete`'s ceremony spine). Direct-import variant (template-
# variant #1, mirrors coordinator/bin/pickup-assemble): a plain in-process
# function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-21-canonical-resolution-engine.md, chunk W2-B1 [DEAD-CITATION: plan file never committed to this repo]
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# session-claim-cli, pickup-assemble); see docs/plans/2026-07-23-dr-088-
# ladder-enforcement-layers.md for the ladder-registration discipline this
# mirrors.
#
# Subcommand:
#   brief [--decisions <json>]
#     Computes and returns the 8-key decision object (artifact/preflight/
#     gates/directives/judgment_points/decisions/narration/next_move) for
#     the current git worktree's `/workstream-complete` ceremony state.
#     READ-ONLY — mutates nothing (coordinator_core.workstream_complete
#     never performs a mutating action itself; every mutation is returned as
#     a directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   2 — usage error (malformed arguments, malformed --decisions JSON).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, no enclosing git worktree, or the sibling
#       wsc-session-disposition.py bin script could not be loaded) — this
#       trampoline's own transport failure, distinct from any business exit
#       code the underlying module may compute.

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("workstream-complete-assemble", sys.argv[1:]))
