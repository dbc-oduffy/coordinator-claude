# workstream-complete-assemble — CLI trampoline over claude-klabauter
# coordinator_core.workstream_complete (the computed-skill assembler for
# `/workstream-complete`'s ceremony spine). Direct-import variant (template-
# variant #1, mirrors coordinator/bin/pickup-assemble): a plain in-process
# function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-21-canonical-resolution-engine.md, chunk W2-B1 [DEAD-CITATION: plan file never committed to this repo]
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (archive-stamp-cli,
# session-claim-cli, pickup-assemble); see docs/plans/2026-07-23-dr-088-
# ladder-enforcement-layers.md for the ladder-registration discipline this
# mirrors.
#
# Subcommand:
#   brief [--decisions <json>]
#     Computes and returns the 8-key decision object (artifact/preflight/
#     gates/directives/judgment_points/decisions/narration/next_move) for
#     the current git worktree's `/workstream-complete` ceremony state.
#     READ-ONLY — mutates nothing (coordinator_core.workstream_complete
#     never performs a mutating action itself; every mutation is returned as
#     a directives[] entry naming an existing atomic CLI).
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   2 — usage error (malformed arguments, malformed --decisions JSON).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, no enclosing git worktree, or the sibling
#       wsc-session-disposition.py bin script could not be loaded) — this
#       trampoline's own transport failure, distinct from any business exit
#       code the underlying module may compute.
from __future__ import annotations
"""workstream-complete-assemble — see the # comment block above for the
RAG-bait purpose text (the polyglot shebang line above makes THIS
triple-quoted string a silently-discarded expression statement, not the
module __doc__ — same convention as archive-stamp-cli / pickup-assemble)."""

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
    import coordinator_core.workstream_complete as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"workstream-complete-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"workstream-complete-assemble: coordinator_core.workstream_complete not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
