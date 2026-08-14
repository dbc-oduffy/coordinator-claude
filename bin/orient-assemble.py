# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# orient-assemble — CLI trampoline over claude-klabauter
# coordinator_core.orient_assemble (the computed-skill assembler for the
# shared cadence-parameterized orient spine). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b2-ceremony-start.md, chunk C1
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# pickup-assemble); see docs/plans/2026-07-23-dr-088-ladder-enforcement-
# layers.md for the ladder-registration discipline this mirrors.
#
# Subcommand:
#   brief --cadence {session|day|week}
#     Computes and returns the 8-key decision object (artifact/preflight/
#     gates/directives/judgment_points/decisions/narration/next_move) for the
#     named cadence. READ-ONLY — mutates nothing (coordinator_core.orient_assemble
#     never performs a mutating action itself; every mutation is returned as a
#     directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   2 — usage error (malformed arguments, missing/unknown --cadence value).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or no enclosing git worktree) — this trampoline's own
#       transport failure, distinct from any business exit code.
from __future__ import annotations
"""orient-assemble — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as pickup-assemble)."""

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
    import coordinator_core.orient_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"orient-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"orient-assemble: coordinator_core.orient_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
