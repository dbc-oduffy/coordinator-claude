# learn-lessons-reconcile-candidates — CLI trampoline over claude-klabauter
# coordinator_core.learn_lessons_assemble (the candidate-restatement
# generator for a doctrine-wiki edit: surfaces places in a target wiki file
# that already say something adjacent to the text a dispatch is about to
# add). Direct-import variant (template-variant #1, mirrors coordinator/bin/
# baton-assemble and pickup-assemble): a plain in-process function call
# after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (baton-assemble, pickup-assemble,
# archive-stamp-cli, session-claim-cli).
#
# Usage:
#   learn-lessons-reconcile-candidates <target-wiki-path> <incoming-text>
#   learn-lessons-reconcile-candidates <target-wiki-path> --text-file <path>
#
# Computes and returns the 8-key decision object (artifact/preflight/gates/
# directives/judgment_points/decisions/narration/next_move). READ-ONLY —
# mutates nothing; `directives`/`judgment_points` are ALWAYS empty for this
# generator (see coordinator_core.learn_lessons_assemble's own module
# docstring — it is a candidate generator, never an adjudicator; there is no
# mutating action for it to name). Candidates + signal counts are carried on
# the envelope's `gates` key.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK, a decision object was computed and returned.
#   2 — usage error (missing/malformed arguments, unreadable --text-file).
#   3 — transport failure (the engine root unresolvable, coordinator_core import
#       failure).
from __future__ import annotations
"""learn-lessons-reconcile-candidates — see the # comment block above for
the RAG-bait purpose text (the polyglot shebang line above makes THIS
triple-quoted string a silently-discarded expression statement, not the
module __doc__ — same convention as baton-assemble/pickup-assemble)."""

import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.learn_lessons_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"learn-lessons-reconcile-candidates: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"learn-lessons-reconcile-candidates: coordinator_core.learn_lessons_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
