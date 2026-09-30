# merge-assemble — CLI trampoline over claude-klabauter
# coordinator_core.merge_assemble (the computed-skill assembler for
# `/merge-to-main`'s branch/release-tag/PR ceremony). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: coordinator-content-repo coordinator/docs/wiki/computed-skills.md
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
#   3 — transport failure (the engine root unresolvable, import failure, no
#       enclosing git worktree).

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("merge-assemble", list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
