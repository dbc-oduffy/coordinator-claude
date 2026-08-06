#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""classify-dispatch-shape.py — CLI trampoline over the claude-klabauter dispatch-shape
classify op (Flag 9 post-hoc dispatch-shape observer).

Given a plan slug, compares the plan's declared parallel-permitted chunk
count (the `## Tasks` fenced plan-tasks spine's non-deferred row count)
against the distinct EXECUTOR-CLASS agentIds observed in the EM session's
dispatched-agents.txt, and emits a question-framed offer (never a verdict) to
stderr when fewer executors ran than chunks were declared. Survives the
2026-07-13 Dispatch Ledger retirement as the hand-orchestrated carve-out
path's serial-grind backstop.
"""
# classify-dispatch-shape.sh — CLI trampoline over claude-klabauter
# coordinator_core.ops.dispatch_shape_classify (Flag 9 post-hoc dispatch-shape
# observer). Given a plan slug, counts the plan's declared parallel-permitted
# chunk count — the `## Tasks` fenced ```yaml plan-tasks``` spine's
# non-deferred row count — then counts distinct EXECUTOR-CLASS agentIds in the
# EM session's dispatched-agents.txt. If N > 1 declared chunks were observed
# but only 1 distinct executor ran, emits a question-framed offer (never a
# verdict) to stderr. Full behavioral spec, binding constraints (F2-F4),
# forbidden mechanisms, and fidelity limits now live on the claude-klabauter module
# docstring (coordinator_core/ops/dispatch_shape_classify.py) — this file is a
# thin argv/exit-code passthrough over that module's main().
#
# Survives the 2026-07-13 Dispatch Ledger retirement as the hand-orchestrated
# carve-out path's serial-grind post-hoc backstop (DEC-3 /
# docs/plans/2026-07-13-retire-plan-body-dispatch-ledger.md).
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C3
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
#
# Exit codes (parity-critical — OFFER SHAPE, unchanged from the bash oracle):
#   0 — ALWAYS. This is a best-effort / never-block advisory observer, not a
#       gate. A finding (if any) is printed to stderr; stdout is unused.
#       A claude-klabauter-link (transport) failure ALSO degrades to exit 0, loud on
#       stderr — consistent with this script's own never-block posture (it
#       must not be able to block a caller even when the engine is
#       unreachable). No dedicated transport-failure code is allocated here
#       because there is no non-zero business code to avoid colliding with.
#
# Usage:
#   classify-dispatch-shape.sh <plan-slug>
#   classify-dispatch-shape.sh --plan-file <path/to/plan.md>
#
# Examples:
#   classify-dispatch-shape.sh 2026-06-22-invariant-verification-observers
#   classify-dispatch-shape.sh --plan-file docs/plans/2026-06-22-foo.md
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.dispatch_shape_classify import main as _op_main
    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"classify-dispatch-shape.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            f"classify-dispatch-shape.sh: coordinator_core.ops.dispatch_shape_classify "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    # DR-276: op_main takes a `script_dir=` kwarg that run_op_main's plain
    # argv-forwarding contract has no room for, so this CLI owns its own
    # main() and wraps the call in recording_declared_writes() directly
    # rather than routing through run_op_main — any paths op_main declares
    # via declare_write() still become a session scope-touch claim instead
    # of landing unclaimed as an orphan at the scoped_git_commit sink.
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        code = op_main(sys.argv[1:], script_dir=_SCRIPT_DIR)
    sys.exit(code)


if __name__ == "__main__":
    main()
