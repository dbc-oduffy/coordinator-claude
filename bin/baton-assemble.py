# baton-assemble — CLI trampoline over claude-klabauter
# coordinator_core.baton_assemble (the kind-flagged computed-skill assembler
# shared by `/handoff` and `/spinoff`'s id-inheritance/lineage cascade).
# Direct-import variant (template-variant #1, mirrors coordinator/bin/
# pickup-assemble and archive-stamp-cli): a plain in-process function call
# after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b4-baton-branch-lifecycle.md,
# chunk C1
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (pickup-assemble,
# archive-stamp-cli, session-claim-cli).
#
# Subcommands:
#   brief <kind> [artifact-path] [--decisions <json>] [--title <text>]
#     Computes and returns the 8-key decision object (artifact/preflight/
#     gates/directives/judgment_points/decisions/narration/next_move) for
#     the named handoff/spinoff artifact. READ-ONLY — mutates nothing.
#     artifact-path is OPTIONAL for kind=handoff (2026-07-28): when omitted,
#     self-resolves the predecessor from the current session's own held
#     handoff claim in the durable claim ledger (fails loud if zero or more
#     than one claim is held — see coordinator_core.baton_assemble.
#     _resolve_held_handoff_for_session). kind=spinoff still requires it.
#   apply <kind> [artifact-path] [--session-id <id>] [--decisions <json>]
#     Recomputes the brief and executes its directives[] through the closed
#     dispatch table (coordinator_core.contract.apply_base). MUTATING.
#     artifact-path is OPTIONAL for kind=handoff on the SAME terms as brief
#     above — this is the verb an operator actually runs, so the
#     self-resolution seam would be unreachable in practice if only brief
#     accepted the omission.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure.
#   2 — usage error (malformed arguments, malformed --decisions JSON).
#   3 — transport failure (the engine root unresolvable, coordinator_core import
#       failure, or no enclosing git worktree).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("baton-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
