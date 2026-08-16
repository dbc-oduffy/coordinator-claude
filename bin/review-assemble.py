# review-assemble — CLI trampoline over claude-klabauter
# coordinator_core.review_assemble (the `/review` skill's read-only
# residue-brief compute, and future review-assemble subcommands).
# Direct-import variant (template-variant #1, mirrors coordinator/bin/
# baton-assemble, pickup-assemble, and archive-stamp-cli): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC
# hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-26-review-skill-computed-residue.md,
# chunk C4
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape
# as every other direct-import CLI in this tree (baton-assemble,
# pickup-assemble, archive-stamp-cli, session-claim-cli).
#
# Subcommands:
#   brief [--artifact <path>]
#     Computes and returns the review-residue decision object (the
#     segments[] applicable to the resolved plan/diff surface, wrapped in
#     the shared decision-object envelope). READ-ONLY — mutates nothing.
#     FALLTHROUGH: a bare invocation with no subcommand token briefs.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the
# contract's own § Exit-code contract):
#   0 — OK.
#   1 — business failure (e.g. no applicable residue segments).
#   2 — usage error (malformed arguments).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core
#       import failure, or an unresolvable content root).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("review-assemble", sys.argv[1:]))
