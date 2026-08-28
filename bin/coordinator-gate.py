# coordinator-gate.py — one dispatcher, a subcommand per current
# `check-*`/`verify-*`/`assert-*` entry point, batching multiple predicates
# into ONE interpreter invocation.
#
# Why this file exists (docs/plans/2026-08-16-a-process-per-predicate.md,
# chunk C10): this is the 60-entry-point family that produces the "a
# ceremony running eight of them pays 16 processes" figure the plan's §
# Problem opens with, and the family C7's fan-in measurement (8 predicates
# as 8 separate processes at p90 6337.80ms vs the same 8 in ONE process at
# 883.83ms, 7.17x) was made against. A dispatcher that can only run one
# predicate per invocation reproduces today's per-process cost exactly while
# adding indirection — that is a fail against this chunk's requirement, not
# a partial credit. An 8-gate ceremony goes from 16 processes to 2 (one
# `coordinator-gate` invocation carrying all 8, plus the caller). Usage:
#
#   coordinator-gate.py <name> [-- <args for name>] [<name2> [-- <args>] ...]
#
# Each `<name>` must be one of entry_point_shim.GATE_TARGETS. Args for a
# given subcommand run from the token after its name up to (but not
# including) the next recognized subcommand name, OR up to a literal `--`
# token immediately following the name (the `--` itself is consumed, not
# forwarded) — the `--` form disambiguates an argument that happens to
# collide with another target's bare name. All subcommands run in this same
# process, in argv order, each via `entry_point_shim.run_gate_target`.
#
# Exit code: 0 iff every subcommand returned 0. Otherwise the exit code of
# the FIRST subcommand that returned non-zero (matches shell `&&`-chained
# semantics of running the same names as separate processes) — every
# subcommand still runs; this dispatcher does not abort early on a mid-batch
# failure, since the 60 targets are independent reads over disjoint
# artifacts, not a pipeline.
#
# Spec backlink: docs/plans/2026-08-16-a-process-per-predicate.md, chunk C10
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


_USAGE_FAIL = 2


def _parse_batch(argv: List[str]) -> List[Tuple[str, List[str]]]:
    """Split argv into (subcommand_name, subcommand_argv) groups."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import GATE_TARGETS, UnknownTargetError

    batch: List[Tuple[str, List[str]]] = []
    i = 0
    n = len(argv)
    while i < n:
        name = argv[i]
        if name not in GATE_TARGETS:
            raise UnknownTargetError(name)
        i += 1
        if i < n and argv[i] == "--":
            i += 1
        args: List[str] = []
        while i < n and argv[i] not in GATE_TARGETS:
            args.append(argv[i])
            i += 1
        batch.append((name, args))
    return batch


def main(argv: List[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import GATE_TARGETS, UnknownTargetError, run_gate_target

    if not argv or argv[0] in ("--help", "-h", "help"):
        names = "\n  ".join(GATE_TARGETS)
        usage = (
            "usage: coordinator-gate <name> [-- <args>] [<name2> [-- <args>] ...]\n"
            "\n"
            "Runs one or more check-/verify-/assert- entry points IN ONE\n"
            "INTERPRETER. Batching is the point: eight predicates as eight\n"
            "processes measured p90 6337.80ms against 883.83ms for the same\n"
            "eight in one process (7.17x -- see\n"
            "coordinator_core/benchmarks/shim_decision_record_fanin.json).\n"
            "Invoking this once per name reproduces the cost it exists to\n"
            "remove.\n"
            "\n"
            f"known names:\n  {names}\n"
        )
        # --help is a successful query, not a usage error; `<no args>` is not.
        if argv:
            print(usage)
            return 0
        print(usage, file=sys.stderr)
        return _USAGE_FAIL

    try:
        batch = _parse_batch(argv)
    except UnknownTargetError as exc:
        print(f"coordinator-gate: unknown subcommand: {exc}", file=sys.stderr)
        return _USAGE_FAIL

    exit_code = 0
    for name, args in batch:
        rc = run_gate_target(name, args)
        if rc != 0 and exit_code == 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
