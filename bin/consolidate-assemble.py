# consolidate-assemble — CLI trampoline over claude-klabauter
# coordinator_core.consolidate_assemble (the computed-skill assembler for
# `/consolidate-git`'s branch/worktree sprawl inventory + absorb/delete
# sequencing). Direct-import variant (template-variant #1, mirrors
# coordinator/bin/merge-assemble): a plain in-process function call after
# resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: DoE-claude:pln-b4-baton-branch-lifecycle-comp-780d48, chunk C8
#
# Subcommands:
#   brief
#     Computes and returns the consolidate decision object (branch/worktree
#     inventory + ownership category, unique-commit evidence, absorb/delete
#     directives[], judgment_points[]). READ-ONLY.
#   apply [--session-id <id>] [--decisions <json>]
#     Recomputes the brief and dispatches its directives[] through the
#     closed CLI table.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure (brief) / halted-at-judgment (apply).
#   2 — usage error.
#   3 — transport failure (the engine root unresolvable, import failure, no
#       enclosing git worktree).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("consolidate-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
