# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""review-coverage-core.py — shared coverage-computation core for review-trail gates.

CLI trampoline over claude-klabauter coordinator_core.ops.review_coverage_core (direct-import,
no @register_op — a plain in-process module call, not a JSON-RPC op). Provides the
reusable primitives consumed by review-trail coverage consumers: SAFE_RANGE
argument-injection validation, JSON-OR-JSONL dual-shape trail-record parsing, per-record
`git rev-list <sha_range>` resolution, and the canonical verdict filter (pending
excluded; ok/warn/blocked/waived/absent included). Called as a subprocess by
test_review_coverage_core.py and, via --segments-json, feeds workweek-trail-scope.py's
seam detection.
"""
# review-coverage-core.py — shared coverage-computation core for review-trail gates.
#
# Purpose: provides the reusable primitives consumed by review-trail coverage
# consumers — SAFE_RANGE argument-injection validator, JSON-OR-JSONL dual-shape
# trail-record parser, per-record `git rev-list <sha_range>` resolution, and the
# canonical verdict filter (pending excluded; ok/warn/blocked/waived/absent
# included). CLI trampoline over claude-klabauter
# coordinator_core.ops.review_coverage_core, direct-import (template-variant #1,
# no @register_op — this is a plain-module in-process call, not a JSON-RPC op).
#
# Interface (called as a subprocess, never sourced):
#
#   review-coverage-core.py --reviewed-set <trail-path> [<trail-path>...]
#       Prints one reviewed SHA per line on stdout (union across all records).
#       Returns exit 0 on success, 1 on fatal error.
#
#   review-coverage-core.py --segments-json <trail-path> [<trail-path>...]
#       Prints a JSON array of segment objects on stdout:
#         [{"sha_range":"...","shas":["..."],"files":["..."]}]
#       Each entry represents one valid diff trail record with its per-commit
#       coverage info. Used by workweek-trail-scope.py for seam detection.
#       Returns exit 0 on success, 1 on fatal error.
#
# Environment:
#   TRAIL_FILES — newline-separated list of trail-file paths (alternative to
#                 passing paths as positional args).
#   WEEK_START  — if set, only records whose filename date-prefix falls within
#                 [WEEK_START, TODAY] are processed (weekly-gate filtering).
#   TODAY       — if set, upper bound for date-prefix filtering (pairs with WEEK_START).
#
# Flags: --on-record-error skip|fail (default: fail) — JSON/JSONL parse failures.
#        --on-unresolvable-ref skip|fail (default: inherits --on-record-error) —
#          git ref-resolution failures (cross-machine SHAs on multi-machine weeks).
#        --intersect <path> (--reviewed-set only) — filter emitted union to SHAs
#          present in this newline-separated file.
#
# Exit codes:
#   0 - success (mode-dependent output on stdout; WARN/INFO possible on stderr)
#   1 - business failure: usage error, or a fail-mode record-parse /
#       git-ref-resolution failure (see --on-record-error /
#       --on-unresolvable-ref above).
#   2 - transport failure: CLAUDE_KLABAUTER_ROOT / coordinator_core.ops.review_coverage_core
#       could not be resolved/imported. Kept distinct from exit 1, matching the
#       sibling workweek-trail-scope.py trampoline (porter-brief-addendum rule
#       3b). (review: code-reviewer — this trampoline previously shared exit 1
#       across both classes; every current caller only branches on
#       zero-vs-nonzero so this is behavior-preserving for them, but a future
#       transport-aware caller now gets a real signal.)
#
# Divergence from the pre-port bash oracle: the --reviewed-set batched
# `git rev-list <range1> <range2> ...` optimization is NOT reproduced — it was
# a confirmed, tracked, open defect (state/bug-backlog/
# 2026-07-03-review-coverage-core-batch-git-rev-list.yaml, claude-klabauter) that
# under-counted reviewed_set whenever two trail records had adjacent/touching
# sha_ranges. Fixed forward per that ticket's own proposed fix (per-range
# independent resolution) — see coordinator_core.ops.review_coverage_core
# module docstring (claude-klabauter) for the full account.
#
# Cross-platform: relies on the claude-klabauter Python engine for all logic; this file
# is pure CLI-argument passthrough.
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C2
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# De-bash rename backlink: docs/plans/2026-07-19-debash-coordinator-windows.md
#   (E3-e — .sh -> .py rename; content was already a pure-Python trampoline)

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported CLI entry.

    Plain in-process import, not an RPC invoke — this trampoline is a thin CLI
    veneer, called by test_review_coverage_core.py (bash) and (in-process,
    bypassing this file entirely) coordinator_core.ops.workweek_trail_scope.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.review_coverage_core import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        # Review: code-reviewer — was exit 1 (shared with business failures below,
        # diverging from sibling workweek-trail-scope.py's dedicated transport
        # code); now exit 2 per porter-brief-addendum rule 3b, matching the sibling.
        print(f"review-coverage-core.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"review-coverage-core.py: coordinator_core.ops.review_coverage_core not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
