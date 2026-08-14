# staff-session-assemble — CLI trampoline over claude-klabauter
# coordinator_core.staff_session_assemble (the computed-skill assembler for
# `/staff-session`'s persona-roster tables). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/sizing-assemble and
# coordinator/bin/pickup-assemble): a plain in-process function call after
# resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
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
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or an unexpected exception inside resolve_roster()).
from __future__ import annotations
"""staff-session-assemble — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as sizing-assemble/pickup-assemble)."""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_TRANSPORT_FAIL = 3


def _import_module():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    import coordinator_core.staff_session_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"staff-session-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"staff-session-assemble: coordinator_core.staff_session_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
