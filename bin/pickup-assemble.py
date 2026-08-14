# pickup-assemble — CLI trampoline over claude-klabauter
# coordinator_core.pickup_assemble (the computed-skill assembler for
# `/pickup`'s branch inventory). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/archive-stamp-cli): a plain in-process function
# call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-23-computed-skills-pickup-beachhead.md, chunk A2
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# session-claim-cli); see docs/plans/2026-07-23-dr-088-ladder-enforcement-
# layers.md for the ladder-registration discipline this mirrors.
#
# Subcommand:
#   brief <artifact-path> [--decisions <json>] [--json]
#     Computes and returns the five-key decision object (artifact/preflight/
#     gates/directives/judgment_points) for the named handoff/memo/spinoff
#     artifact. READ-ONLY — mutates nothing (coordinator_core.pickup_assemble
#     never performs a mutating action itself; every mutation is returned as a
#     directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   1 — business failure (artifact unreadable/absent-and-not-archived, claim
#       held by a live peer, addressee mismatch without override) — the
#       returned decision object still carries the failing gate's full detail.
#   2 — usage error (malformed arguments, malformed --decisions JSON).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or no enclosing git worktree) — this trampoline's own
#       transport failure, distinct from any business exit code.
from __future__ import annotations
"""pickup-assemble — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as archive-stamp-cli)."""

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
    import coordinator_core.pickup_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"pickup-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"pickup-assemble: coordinator_core.pickup_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
