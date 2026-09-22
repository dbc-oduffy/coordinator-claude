"""emit-dispatch-workflow.py — thin door-served CLI over
`coordinator_core.ops.dispatch_emit.cli`.

The published surface (skills/hooks citing
`${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/emit-dispatch-workflow.py`)
probes this exact path — the file name and location stay fixed even though
the emitter it runs now lives entirely in the engine.

`main(argv)` shim, `coordinator/bin/plan-task-brief.py :: main` /
`coordinator/bin/mise-prep-gate.py :: main` shape: engine imports happen
inside `main()`, the module body stays pure, so `serve_classifier`
classifies this file warm-servable. Argument parsing, the emit/restamp/fire
dispatch and the exit-code mapping all live in
`coordinator_core.ops.dispatch_emit.cli`; this file owns nothing but the
door.

Usage:
  python emit-dispatch-workflow.py --plan PLAN --out OUT [--force] [--fire] [--repo-root PATH]
  python emit-dispatch-workflow.py --inventory RECORD --out OUT [--force] [--fire] [--repo-root PATH]
  python emit-dispatch-workflow.py --restamp SCRIPT

Exit codes (`coordinator_core.ops.dispatch_emit.cli`):
  0 — emission (or restamp, or fire) succeeded.
  1 — data/refusal error (mutually-exclusive params, foreign emission,
      foreign restamp session, no receipt to restamp, a non-zero-ERROR
      emit verdict).
  2 — usage error (missing required flag, unresolvable combination,
      coordinator_core unresolvable).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk S1-C7.
"""
from __future__ import annotations

import sys


def main(argv: "list[str] | None" = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.ops.dispatch_emit.cli import main as emit_main
    except Exception as exc:
        print(
            f"emit-dispatch-workflow.py: ERROR — coordinator_core unresolvable: {exc}",
            file=sys.stderr,
        )
        return 2

    return emit_main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
