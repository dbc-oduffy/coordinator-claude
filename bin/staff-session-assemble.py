# staff-session-assemble — CLI trampoline over claude-klabauter
# coordinator_core.staff_session_assemble (the computed-skill assembler for
# `/staff-session`'s persona-roster tables). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/sizing-assemble and
# coordinator/bin/pickup-assemble): a plain in-process function call after
# resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md, DR-090
# Spec backlink: DoE-claude:pln-computed-skills-b5-planning-cl-a28764,
# chunk C11 (Design Option A, AC17)
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (sizing-assemble, pickup-assemble,
# archive-stamp-cli, session-claim-cli).
#
# Subcommand: none — this trampoline forwards straight to
# coordinator_core.staff_session_assemble.main(argv). See that module's
# `main()` for the flag surface (--domain-signal, --session-mode, --slug
# (repeatable, explicit override)).
#
# READ-ONLY — mutates nothing. staff_session_assemble.resolve_roster() never
# writes; it reads DoE-claude's coordinator/routing.md (the doctrine-side
# roster home, F1 reconciliation) and prints the resolved roster.
#
# Exit codes (locally scoped to this CLI, NOT inherited):
#   0 — OK, a roster decision was resolved and printed.
#   1 — reserved for a future business-failure class (unused today).
#   2 — usage error (missing/malformed --domain-signal, --session-mode, or an
#       unresolvable doctrine-side routing.md read — see
#       coordinator_core.staff_session_assemble.StaffSessionAssembleError).
#   3 — transport failure (the engine root unresolvable, coordinator_core import
#       failure, or an unexpected exception inside resolve_roster()).

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("staff-session-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
