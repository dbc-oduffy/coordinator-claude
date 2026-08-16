"""query-goals.py -- the porter over `sections/goals.py:collect(ctx)`.

No shebang line, no exec bit: this is only ever spawned as `python3
query-goals.py`, never as a bare word -- no launch path via
`gen-launcher-shim.py` is generated or asserted here (same posture as
`query-routine-signals.py`).

Purpose: a per-repo, one-process entry point a non-Python caller (project-
Cockpit's `fleetobs-06` goals acquisition) can spawn to read this repo's
`goals_current` records -- the emit projection over the declared-goals wire
log -- without linking against `coordinator_core` or standing up a JSON-RPC
client of its own.

`sections/goals.py:collect` has NO registered op behind it -- it is an
emit *section*, a plain in-process function, not something
`cc_invoke.route` can dispatch. This file therefore does NOT use
`coordinator/bin/lib/op_trampoline.py`'s `run()` (that entrypoint exists
to route a *named op*; there is no op name here, and minting one is the
engine change this porter's plan explicitly rules out). It DOES reuse
`op_trampoline.resolve_repo_root_or_exit()` and
`op_trampoline.resolve_claude_klabauter_root_or_exit()` -- the two pieces of the
Shape-A recipe that apply unchanged -- and hand-implements the same exit-1
failure-diagnostic convention around its own `collect(ctx)` call, so the
two shapes do not drift. See `query-routine-signals.py`'s module docstring
for the fuller version of this reasoning; both porters are the same shape
over a different section.

Shape note this porter does NOT share with `query-routine-signals.py`:
`collect(ctx)` here can RAISE `GoalsStateRootUnreadable` when
`ctx.central_state_root` exists but cannot be listed (permission-denied,
not merely empty). That raise exists specifically so an unscannable root
is distinguishable from a genuinely empty goals corpus -- this section has
no envelope-visible malformed channel to report a degraded scan through
(see `sections/goals.py`'s own module docstring). This CLI's broad
`except Exception` already turns that raise into exit 1 with its message,
the same as any other collect-side failure -- there is no special-case
branch needed, only the deliberate absence of one that would swallow it
back into an empty-list exit 0.

Usage:
    python3 query-goals.py
    python3 query-goals.py --help

Exit codes:
    0 -- success, `goals.collect(ctx)`'s records list printed to stdout as
         JSON.
    1 -- repo-root resolution failure, or any exception raised while
         building the context or calling `collect()` -- including
         `GoalsStateRootUnreadable`, which surfaces here with its own
         message, never as a silent zero-goals exit 0.
    2 -- unrecognized argument (this CLI takes no flags besides the
         automatic -h/--help; argparse's own usage-error convention,
         matching `query-routine-signals.py`).

Spec backlink: plan `2026-08-15-two-more-porter-trampolines-query-goals.md` § C1

Negative-spec: does NOT add filtering, caching, or any goals-abstraction
layer -- this porter is a read-only trampoline over `collect(ctx)` in the
shape of this directory's other `query-*` CLIs, not a goals API. Does NOT
mint a registered op for `goals.collect` -- that would be the engine
change the plan's Anti-scope rules out. Does NOT "optimise" `collect()`.
Does NOT edit `coordinator_core/ops/emit/sections/goals.py` -- that file
is READ-ONLY to this plan. Does NOT reshape, rename, or filter fields out
of the emitted records -- the output is `goals.collect(ctx)`'s existing
shape verbatim, including a `key_results_status` field that is
absent-when-absent and currently absent on every row in this repo (the
`key_results_status` writer-to-emit gap is real but tracked separately --
see the plan's Out of scope -- an empty key-results rung here is a
producer gap, not a defect in this porter). Does NOT generate a
`.cmd`/`.ps1` shim.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from op_trampoline import (  # noqa: E402
    resolve_claude_klabauter_root_or_exit,
    resolve_repo_root_or_exit,
)


_HONESTY_DISCLOSURES = """\
One honesty disclosure a consumer of this CLI needs and must not lose:

  `key_results_status` is absent-when-absent on every emitted record, and
  currently absent on EVERY record in this repo -- no caller inside
  `coordinator_core` supplies it yet (a writer surface exists at
  `append-goal-event.py`'s `--key-results-status` flag, but the only
  caller that would populate it, the `goal-setting` skill, does not pass
  it through). An empty key-results rung in this CLI's output is a
  producer gap upstream of `collect()`, not a defect in this porter."""


def build_parser() -> argparse.ArgumentParser:
    """No flags beyond the automatic -h/--help -- this CLI takes no
    arguments (see module docstring's Negative-spec: no filtering, no
    caching, no goals-abstraction layer)."""
    return argparse.ArgumentParser(
        prog="query-goals.py",
        description=_HONESTY_DISCLOSURES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    parser.parse_args(argv)  # exits 2 on any unrecognized argument

    repo_root = resolve_repo_root_or_exit()
    if isinstance(repo_root, int):
        return repo_root

    claude_klabauter_root = resolve_claude_klabauter_root_or_exit("query-goals")
    if isinstance(claude_klabauter_root, int):
        return claude_klabauter_root

    try:
        from coordinator_core.ops.emit.envelope import resolve_context
        from coordinator_core.ops.emit.sections import goals
    except ImportError as exc:
        print(f"query-goals: coordinator_core not importable: {exc}", file=sys.stderr)
        return 1

    try:
        ctx = resolve_context(Path(repo_root))
        records, _malformed = goals.collect(ctx)
    except Exception as exc:  # noqa: BLE001 -- any failure on this path is exit 1,
        # including GoalsStateRootUnreadable (see module docstring's shape note).
        print(f"query-goals: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(records, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
