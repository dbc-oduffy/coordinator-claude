# review-assemble — CLI trampoline over claude-klabauter
# coordinator_core.review_assemble (the `/review` skill's read-only
# residue-brief compute, and future review-assemble subcommands).
# Direct-import variant (template-variant #1, mirrors coordinator/bin/
# baton-assemble, pickup-assemble, and archive-stamp-cli): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC
# hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-26-review-skill-computed-residue.md,
# chunk C4
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape
# as every other direct-import CLI in this tree (baton-assemble,
# pickup-assemble, archive-stamp-cli, session-claim-cli).
#
# Subcommands:
#   brief [--artifact <path>]
#     Computes and returns the review-residue decision object (the
#     segments[] applicable to the resolved plan/diff surface, wrapped in
#     the shared decision-object envelope). READ-ONLY — mutates nothing.
#     FALLTHROUGH: a bare invocation with no subcommand token briefs.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the
# contract's own § Exit-code contract):
#   0 — OK.
#   1 — business failure (e.g. no applicable residue segments).
#   2 — usage error (malformed arguments).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core
#       import failure, or an unresolvable content root).
from __future__ import annotations
"""review-assemble — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module
__doc__ — same convention as baton-assemble/pickup-assemble/
archive-stamp-cli)."""

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
    import coordinator_core.review_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"review-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"review-assemble: coordinator_core.review_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
