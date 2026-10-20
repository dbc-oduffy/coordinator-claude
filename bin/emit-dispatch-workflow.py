"""emit-dispatch-workflow.py — thin door-served CLI over
`coordinator_core.ops.dispatch_emit.cli`.

The published surface (skills/hooks citing
`${CLAUDE_PLUGIN_ROOT:-${_content_root}/coordinator}/bin/emit-dispatch-workflow.py`)
probes this exact path — the file name and location stay fixed even though
the emitter it runs now lives entirely in the engine.

`main(argv)` shim, `coordinator/bin/plan-task-brief.py :: main` /
`coordinator/bin/mise-prep-gate.py :: main` shape: engine imports happen
inside `main()`, the module body stays pure, so `serve_classifier`
classifies this file warm-servable. A plain `--plan` argv (only `--plan`,
`--out`, `--force`, `--repo-root`) goes to `dispatch_emit.plan_route` without
importing `cli`; every other argv goes to `dispatch_emit.cli`, where argument
parsing, the restamp/fire dispatch and the exit-code mapping live. This file
owns nothing but the door.

Usage:
  python emit-dispatch-workflow.py --plan PLAN --out OUT [--force] [--fire] [--repo-root PATH]
  python emit-dispatch-workflow.py --inventory RECORD --out OUT [--force] [--fire] [--repo-root PATH]
  python emit-dispatch-workflow.py --ask "PROMPT" [--out OUT] [--repo-root PATH]
  python emit-dispatch-workflow.py --ask --sizing STATE/SIZINGS/X.yaml [--out OUT] [--repo-root PATH]
  (--sizing alone is the same entry; --fire is refused with --ask/--sizing)
  python emit-dispatch-workflow.py --pipeline NAME (--brief TEXT | --brief-file PATH) [--subjects FILE|a,b] [--flag NAME=VALUE ...] [--scratch-dir PATH] [--out OUT] [--repo-root PATH]
  (--pipeline is emit-only; --fire, --writes and every other route selector are refused with it)
  python emit-dispatch-workflow.py --research --ask "Q1" [--target web|repo=PATH|local=PROBE] [--ask "Q2" [--target ...]] [--split|--combine] [--repo-root PATH]
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


PLAN_ROUTE_MODULE = "coordinator_core.ops.dispatch_emit.plan_route"
CLI_MODULE = "coordinator_core.ops.dispatch_emit.cli"
# Mirrors plan_route.ACCEPTED_FLAGS; the door cannot import plan_route to read it.
_PLAN_ROUTE_FLAGS = frozenset({"--plan", "--out", "--force", "--repo-root", "--resume-rows"})


def route_module(args: "list[str]") -> str:
    """`PLAN_ROUTE_MODULE` for a plain `--plan` argv (only plan_route's flags, each well-formed); else `CLI_MODULE`."""
    seen_plan = False
    items = iter(args)
    for item in items:
        flag, eq, _ = item.partition("=")
        if flag not in _PLAN_ROUTE_FLAGS:
            return CLI_MODULE
        if flag == "--force":
            if eq:
                return CLI_MODULE
            continue
        if not eq and next(items, None) is None:
            return CLI_MODULE
        seen_plan = seen_plan or flag == "--plan"
    return PLAN_ROUTE_MODULE if seen_plan else CLI_MODULE


def main(argv: "list[str] | None" = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.cli_entry import run_op_main
    except Exception as exc:
        print(
            f"emit-dispatch-workflow.py: ERROR — coordinator_core unresolvable: {exc}",
            file=sys.stderr,
        )
        return 2

    return run_op_main(route_module(args), args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
