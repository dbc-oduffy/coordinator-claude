# sizing-assemble — CLI trampoline over claude-klabauter
# coordinator_core.sizing_assemble (the computed-skill assembler for
# `/sizing`'s route table). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/pickup-assemble): a plain in-process function
# call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md, DR-090
# Spec backlink: docs/plans/2026-07-24-sizing-lobby-core.md, chunk C7
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (pickup-assemble,
# archive-stamp-cli, session-claim-cli).
#
# Subcommand: none — this trampoline forwards straight to
# coordinator_core.sizing_assemble.main(argv). See that module's `main()`
# for the flag surface (--appetite, --tshirt, --express-lane,
# --probe-signal, --jtbd-unclear, --well-trodden-step-change,
# --premise-provenance, --boundary-in-notch, --scout-evidence-kind,
# --scout-evidence).
#
# READ-ONLY — mutates nothing. sizing_assemble.route() never writes a
# sizing-object; it returns the route/detents/fork fields for the caller to
# persist.
#
# Exit codes (locally scoped to this CLI, NOT inherited):
#   0 — OK, a decision object was computed and printed.
#   1 — reserved for a future business-failure class (unused today —
#       route() has no business-failure path, only usage errors).
#   2 — usage error (missing/malformed --appetite or --tshirt).
#   3 — transport failure (the engine root unresolvable, coordinator_core
#       import failure, or an unexpected exception inside route()).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("sizing-assemble", argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
