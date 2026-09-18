#!/usr/bin/env python3
"""mise-prep-gate.py — thin door-served CLI over `coordinator_core.roadmap.prep_gate_cli`.

The published surface (`skills/plan-blitz/mise-prep-entry.py :: _gate_cmd`) probes this
exact path — `<plugin_root>/bin/mise-prep-gate.py` — so the file name and location stay
fixed even though the bar it runs now lives entirely in the engine.

`main(argv)` shim, `coordinator/bin/plan-task-brief.py :: main` shape: engine imports
happen inside `main()`, the module body stays pure, so `serve_classifier` classifies
this file warm-servable. Every predicate (SPINE/CENSUS/EXTERNAL_DEPS/PRIME_EXIT/SCHEMA)
is `coordinator_core.roadmap.prep_gate.gate_plan`, called once per target — no spawn, no
git, no corpus-wide sweep. Argument parsing, target expansion and `--json`/`--tally`
rendering live in `coordinator_core.roadmap.prep_gate_cli`; this file owns nothing but
the door.

Usage:
  python mise-prep-gate.py [target ...] [--json] [--tally] [--repo-root PATH]

Exit codes (`coordinator_core.roadmap.prep_gate_cli`):
  0 — every named plan is PREPPED.
  1 — at least one plan is NOT-PREPPED (an authoring fix).
  2 — RESERVED (REFUSED — currently unreachable; see `prep_gate.py`'s own docstring).
  3 — usage error (bad target, coordinator_core unresolvable).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk S1-C8.
"""
from __future__ import annotations

import sys


def main(argv: "list[str] | None" = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.roadmap.prep_gate_cli import main as gate_main
    except Exception as exc:
        print(f"mise-prep-gate.py: ERROR — coordinator_core unresolvable: {exc}", file=sys.stderr)
        return 3

    return gate_main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
