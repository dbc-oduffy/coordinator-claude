# review-exec-auth-stamp — CLI trampoline over claude-klabauter
# coordinator_core.review_assemble.exec_auth_stamp (the mutating assembler
# that collapses /review's ordinal-narrated execution-authorization stamp
# sequence into one named op). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/pickup-assemble and archive-stamp-cli): a plain
# in-process function call after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: DoE-claude:pln-computed-skills-b8-review-ci-c-ffa5ad,
# chunk C6
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (pickup-assemble,
# archive-stamp-cli, baton-assemble).
#
# Subcommand:
#   stamp <plan-path> --by <who> --note <verbatim-note> [--at <YYYY-MM-DD>]
#     Computes the plan-body hash and writes all four
#     execution_authorized_{by,at,sha,note} fields onto the plan's own
#     frontmatter, atomically. MUTATING. Idempotent — re-stamping with
#     identical values is a no-op.
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK (stamped or already-converged no-op).
#   1 — business failure (plan unreadable/absent, no parseable frontmatter,
#       lock timeout, mutate abort).
#   2 — usage error (malformed arguments).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or no enclosing git worktree).
from __future__ import annotations
"""review-exec-auth-stamp — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as pickup-assemble/archive-stamp-cli)."""

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
    import coordinator_core.review_assemble.exec_auth_stamp as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"review-exec-auth-stamp: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"review-exec-auth-stamp: coordinator_core.review_assemble.exec_auth_stamp not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
