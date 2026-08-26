# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""agent-worktree-sweep.py — CLI trampoline over the claude-klabauter worktree-sweep op.

Scans (and, with --reap, cleans up) the per-dispatch git worktrees Claude Code
2.1.x auto-creates under <repo>/.claude/worktrees/agent-<hash>/ for
backgrounded Agent dispatches. These persist locked until session deletion
and accumulate across days; /workday-start and /workstream-start invoke this
trampoline to surface and salvage them. Resolves the engine root and delegates to
coordinator_core.ops.agent_worktree_sweep for the actual scan/reap logic.
"""
# agent-worktree-sweep.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.agent_worktree_sweep. Finds and (optionally) reaps the
# per-dispatch git worktrees Claude Code 2.1.x auto-creates under
# <repo>/.claude/worktrees/agent-<hash>/ for backgrounded Agent dispatches
# (opt-out-only behavior, no per-dispatch flag yet — anthropics/claude-code#58597).
# These persist locked until session deletion, accumulating across days;
# `/workday-start` and `/workstream-start` invoke this trampoline to surface
# and salvage them.
#
# Usage:
#   agent-worktree-sweep.py [--reap] [--format json|text]
#     --reap            Remove empty-clean worktrees; cherry-pick + remove
#                       commits-clean worktrees. Without it, scan only.
#     --format json     Default. One JSON line per worktree.
#     --format text     Human-readable summary.
#     --help            Show this help.
#
# Exit codes (parity-critical — 0/2/3 unchanged from the bash oracle; 4 is new):
#   0 — completed (with or without findings)
#   2 — not a git repo / no `git` on PATH / CLI usage error (op ran, business fail)
#   3 — --reap requested but a cherry-pick conflict left a worktree mid-state,
#       or a `git worktree remove` invocation was rejected (op ran, business fail)
#   4 — claude-klabauter transport failure (the engine root unresolvable, or
#       coordinator_core.ops.agent_worktree_sweep not importable) — the op
#       never ran at all. Deliberately its OWN code, not reusing 2 (which
#       already means a business-level "not a git repo / usage error" from
#       the ported op itself) or 3 (mid-reap conflict) — collapsing transport
#       failure onto either would let a caller misclassify "the engine never
#       ran" as one of the ported script's own legitimate failure states.
#
# Port source: coordinator/bin/agent-worktree-sweep.py (DoE-claude, this file,
# 307-line bash oracle retired on this cutover; see git log)
# Ported to: coordinator_core/ops/agent_worktree_sweep.py (claude-klabauter)
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 in-process
    runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    calling the op's `main` directly, so any `--reap` worktree-removal it
    declares becomes a session scope-touch claim instead of an orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        # CLAUDE_KLABAUTER_ROOT resolution failed. This is a fail-loud gate script (rc
        # encodes real business outcomes 0/2/3), so a transport failure gets
        # its own dedicated exit (4) -- see the exit-code table above for why
        # it must not collide with 2 or 3.
        print(f"agent-worktree-sweep.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(4)
    except ImportError as exc:
        print(
            f"agent-worktree-sweep.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(4)

    try:
        code = run_op_main("coordinator_core.ops.agent_worktree_sweep", sys.argv[1:])
    except ImportError as exc:
        print(
            f"agent-worktree-sweep.py: coordinator_core.ops.agent_worktree_sweep not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(4)
    sys.exit(code)


if __name__ == "__main__":
    main()
