# close-out-and-stamp — CLI trampoline over claude-klabauter
# coordinator_core.execute_plan_assemble.close_out_and_stamp (the mutating
# assembler that collapses `/execute-plan` Phase 4's ordinal-narrated
# close-out sequence -- decide shipped-vs-halted, stamp `status:
# implemented` on the full-shipped path only, land one scoped commit --
# into one named op). Direct-import variant (template-variant #1, mirrors
# coordinator/bin/pickup-assemble, archive-stamp-cli, review-exec-auth-stamp):
# a plain in-process function call after resolving the engine root, no
# cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: DoE-claude coordinator/skills/execute-plan/SKILL.md § Phase 4
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module -- same shape as
# every other direct-import CLI in this tree (pickup-assemble,
# archive-stamp-cli, review-exec-auth-stamp).
#
# Usage:
#   close-out-and-stamp <plan-path> [--dry-run]
#     Determines full-shipped vs. halted from the plan's `## Tasks` spine
#     cross-referenced against `git log --oneline -- <plan-path>` commit
#     subjects, stamps `status: implemented` on the full-shipped path only,
#     then lands one scoped `coordinator-safe-commit` covering every changed
#     path plus the plan doc itself. MUTATING BY DEFAULT.
#
#     --dry-run: computes and returns the identical full verdict (shipped,
#     stamped, status_target, open_chunk_ids, missing_chunk_ids,
#     disposition_ref_rejections, message, the lot) while writing NOTHING --
#     no frontmatter stamp, no plan-body disposition backfill, no commit, no
#     push. Added 2026-08-04 after an agent asked purely to READ this
#     ceremony's verdict had no way to do so short of running the mutating
#     path -- and did, stamping/committing/pushing to a shared branch as a
#     side effect of a read. The returned JSON always carries a top-level
#     "dry_run": bool key, so a caller can never mistake a preview for a
#     completed close-out. Opt-in only -- the bare positional form above is
#     UNCHANGED and still mutates, so no existing caller (`/execute-plan`
#     Phase 4 included) silently stops stamping.
#
# Exit codes (locally scoped to this CLI, NOT inherited from the op's own
# EXIT_OK/EXIT_BUSINESS_FAIL/EXIT_USAGE constants -- see the module for the
# full contract):
#   0 — OK (shipped-and-stamped, or halted-and-committed-partial; under
#       --dry-run, the identical verdict computed but not written/committed).
#   1 — business failure (plan unreadable/absent, no parseable frontmatter,
#       malformed ## Tasks spine, stamp write failed, commit failed --
#       --dry-run still reports 1 here, since a write/commit that WOULD have
#       failed live is a genuine verdict, not suppressed by --dry-run).
#   2 — usage error (missing/unrecognized arguments; --dry-run is the only
#       recognized flag, and does not itself constitute an "extra" argument).
#   3 — transport failure (the engine root unresolvable, coordinator_core import
#       failure, or no enclosing git worktree).
from __future__ import annotations
"""close-out-and-stamp — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as pickup-assemble/archive-stamp-cli/review-exec-auth-stamp)."""

import os
import sys

_TRANSPORT_FAIL = 3


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.execute_plan_assemble.close_out_and_stamp as _mod

    return _mod


def main(argv: list[str]) -> int:
    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"close-out-and-stamp: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"close-out-and-stamp: coordinator_core.execute_plan_assemble.close_out_and_stamp "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
