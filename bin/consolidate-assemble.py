# consolidate-assemble — CLI trampoline over claude-klabauter
# coordinator_core.consolidate_assemble (the computed-skill assembler for
# `/consolidate-git`'s branch/worktree sprawl inventory + absorb/delete
# sequencing). Direct-import variant (template-variant #1, mirrors
# coordinator/bin/merge-assemble): a plain in-process function call after
# resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: DoE-claude:pln-b4-baton-branch-lifecycle-comp-780d48, chunk C8
#
# Subcommands:
#   brief
#     Computes and returns the consolidate decision object (branch/worktree
#     inventory + ownership category, unique-commit evidence, absorb/delete
#     directives[], judgment_points[]). READ-ONLY.
#   apply [--session-id <id>] [--decisions <json>]
#     Recomputes the brief and dispatches its directives[] through the
#     closed CLI table.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure (brief) / halted-at-judgment (apply).
#   2 — usage error.
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, import failure, no
#       enclosing git worktree).
from __future__ import annotations
"""consolidate-assemble — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as pickup-assemble/merge-assemble)."""

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
    import coordinator_core.consolidate_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"consolidate-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"consolidate-assemble: coordinator_core.consolidate_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
