# quick-wrap-assemble — CLI trampoline over claude-klabauter
# coordinator_core.quick_wrap_assemble (the computed-skill assembler for
# `/quick-wrap`'s four-condition entry test). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble).
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: state/handoffs/2026-08-14-fact-layer-library-sweep.md
# Fold-in ask: cross-repo/archive/2026-08-14-doe-claude-em-quick-wrap-has-no-assembler-at-all.md
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree.
#
# Subcommand:
#   brief
#     Computes and returns the decision object for this session's light close:
#     gates.close_gate carries the five DoE-named fields (pickup_kind,
#     governing_plan, diff, terminal_sizings, fold_sidecars) and
#     gates.entry_test carries the four-condition verdict plus its route.
#     READ-ONLY — mutates nothing; every mutation is returned as a
#     directives[] entry naming an existing atomic CLI.
#
# Exit codes (locally scoped to this CLI, NOT inherited):
#   0 — OK, a decision object was computed and returned. This INCLUDES an
#       entry test that fails: a failing gate is a successfully computed
#       routing verdict, not an error. Read gates.entry_test.verdict.
#   2 — usage error (malformed arguments).
#   3 — transport failure (no enclosing git worktree, unresolvable session id,
#       the engine root unresolvable, or coordinator_core import failure).

# --- routing half: this file is a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("quick-wrap-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
