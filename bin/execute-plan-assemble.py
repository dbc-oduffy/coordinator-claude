# execute-plan-assemble — CLI trampoline over claude-klabauter
# coordinator_core.execute_plan_assemble.apply (the mutating half of the
# `/execute-plan` Phase-1 pre-execution chain -- stamp-check, authorize-
# invocation, claim-plan --for-execution, the workflow emit -- collapsed
# into one closed dispatch table, gated behind the same judgment points
# `pre_execution.py` emits). Direct-import variant (template-variant #1,
# mirrors coordinator/bin/close-out-and-stamp, pickup-assemble,
# archive-stamp-cli, review-exec-auth-stamp): a plain in-process function
# call after resolving the engine root, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-09-11-the-execute-plan-pre-execution-chain-emi.md, C2
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module -- same shape as
# every other direct-import CLI in this tree.
#
# Usage:
#   execute-plan-assemble apply <plan-path> [--autonomous] [--session-id <id>]
#     Dispatches the four Phase-1 directives (stamp-check, authorize-
#     invocation, claim-plan --for-execution, the workflow emit) through the
#     closed `_CLI_DISPATCH` table, per-directive gated on the judgment
#     points `pre_execution_directives()` emits. `--autonomous` omits the
#     stamp-check/authorize-invocation pair (the skill skips both under
#     `/autonomous`).
#
# Exit codes (locally scoped to this CLI, NOT inherited from any other
# assembler's own contract -- see coordinator_core.execute_plan_assemble.apply
# for the full contract):
#   0 — OK, every directive dispatched (or was already_satisfied).
#   1 — a directive raised (APPLY_EXIT_PARTIAL_MUTATION) or the dispatch was
#       halted at an undispositioned/declined judgment point
#       (APPLY_EXIT_HALTED_AT_JUDGMENT).
#   2 — usage error (missing/unrecognized arguments).
#   3 — transport failure (the engine root unresolvable, coordinator_core
#       import failure, or no enclosing git worktree, or no resolvable
#       session id).
from __future__ import annotations
"""execute-plan-assemble — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ --
same convention as close-out-and-stamp/pickup-assemble/archive-stamp-cli)."""

import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()  # noqa: F841
    import coordinator_core.execute_plan_assemble.apply as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"execute-plan-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"execute-plan-assemble: coordinator_core.execute_plan_assemble.apply "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
