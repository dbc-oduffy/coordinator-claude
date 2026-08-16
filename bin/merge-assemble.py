# merge-assemble — CLI trampoline over claude-klabauter
# coordinator_core.merge_assemble (the computed-skill assembler for
# `/merge-to-main`'s branch/release-tag/PR ceremony). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b4-baton-branch-lifecycle.md, chunk C6
#
# Subcommands:
#   brief [--tag-prefix <prefix>]
#     Computes and returns the merge decision object (branch_state,
#     release_tag_cut proposal, version_bump proposal, gate_verdicts
#     scaffold, directives[], judgment_points[]). READ-ONLY.
#   apply [--session-id <id>] [--force] [--decisions <json>] [--tag-prefix <prefix>]
#     Recomputes the brief and dispatches its directives[] through the
#     closed CLI table. `--force` bypasses the node ceremony hard-gate.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure (brief) / halted-at-judgment (apply).
#   2 — usage error.
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, import failure, no
#       enclosing git worktree).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("merge-assemble", sys.argv[1:]))
