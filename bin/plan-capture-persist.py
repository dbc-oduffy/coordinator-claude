"""
plan-capture-persist.py — CLI trampoline over the engine repo's
coordinator_core.ops.plan_capture_persist.

This is the engine-repo-side half of the seam a sibling doctrine repo's hook
(``coordinator/hooks/scripts/plan-persistence-check.py``,
PostToolUse(ExitPlanMode)) is expected to call once wired — see the
invocation-contract memo shipped alongside this change. It is NOT wired
into that hook by this change: that edit belongs to the hook's own repo,
outside this change's scope.

Usage (mirrors the invocation-contract memo verbatim):
    echo "$PLAN_BODY" | python3 coordinator/bin/plan-capture-persist.py \\
        --repo-root <path> [--sizing-object <path>] [--title <text>] \\
        [--branch <name>]

Prints ONE JSON line to stdout (the ``persist_captured_plan`` result dict —
see the op module's own docstring for the exact shape) and exits 0 for every
EXPECTED outcome (ok/idempotent/collision), 1 for a genuine error. The
CALLER is responsible for fail-open behaviour (a bounded timeout + treat any
non-zero exit / timeout / unparseable stdout as "fall back to the existing
raw write") — this trampoline itself is an ordinary fail-loud CLI.

No shebang, matching the current `coordinator/bin/*.py` convention —
invoke via `python3 coordinator/bin/plan-capture-persist.py` on
macOS/Linux; the co-located `.cmd` twin is the Windows entrypoint.

Spec backlink: state/handoffs/2026-08-13-vanilla-plan-mode-capture-safety-net.md § Part 2
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 in-process
    runner — mirrors assert-plan-sizing-citation.py's identical helper verbatim.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    calling the op's `main` directly, so this op's declared writes become a
    session scope-touch claim instead of an orphan at the `scoped_git_commit`
    sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"plan-capture-persist.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"plan-capture-persist.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.plan_capture_persist", sys.argv[1:])
    except ImportError as exc:
        print(
            "plan-capture-persist.py: "
            f"coordinator_core.ops.plan_capture_persist not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
