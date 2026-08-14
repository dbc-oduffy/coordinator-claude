# merge-assemble — CLI trampoline over claude-klabauter
# coordinator_core.merge_assemble (the computed-skill assembler for
# `/merge-to-main`'s branch/release-tag/PR ceremony). Direct-import variant
# (template-variant #1, mirrors coordinator/bin/pickup-assemble): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-24-computed-skills-b4-baton-branch-lifecycle.md, chunk C6
#
# Subcommands:
#   brief [--tag-prefix <prefix>]
#     Computes and returns the merge decision object (branch_state,
#     release_tag_cut proposal, version_bump proposal, gate_verdicts
#     scaffold, directives[], judgment_points[]). READ-ONLY.
#   apply [--session-id <id>] [--force] [--decisions <json>] [--tag-prefix <prefix>]
#     Recomputes the brief and dispatches its directives[] through the
#     closed CLI table. `--force` bypasses the node ceremony hard-gate.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure (brief) / halted-at-judgment (apply).
#   2 — usage error.
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, import failure, no
#       enclosing git worktree).
from __future__ import annotations
"""merge-assemble — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as pickup-assemble/archive-stamp-cli)."""

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
    import coordinator_core.merge_assemble as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"merge-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"merge-assemble: coordinator_core.merge_assemble not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
