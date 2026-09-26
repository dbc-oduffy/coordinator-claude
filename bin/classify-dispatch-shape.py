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
# non-deferred row count — then counts distinct EXECUTOR-CLASS agentIds in the
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.dispatch_shape_classify import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"classify-dispatch-shape.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            f"classify-dispatch-shape.sh: coordinator_core.ops.dispatch_shape_classify "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        code = op_main((sys.argv[1:] if argv is None else argv), script_dir=_SCRIPT_DIR)
    return code


if __name__ == "__main__":
    sys.exit(main())
