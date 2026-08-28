# coordinator-assemble.py — one dispatcher, a subcommand per current
# `-assemble` entry point, batching multiple subcommands into ONE
# interpreter invocation.
#
# Why this file exists (docs/plans/2026-08-16-a-process-per-predicate.md,
# chunk C8): the win here is fan-in, not the shim (see
# coordinator/bin/lib/entry_point_shim.py's docstring for the shim-mechanism
# measurement). C7 measured 8 predicates run as 8 separate processes at p90
# 6337.80ms against the same 8 predicates run in ONE process at 883.83ms — a
# 7.17x reduction, the seven interpreter cold-starts the batched shape
# removes. A dispatcher that can only run one subcommand per invocation
# reproduces today's per-process cost exactly while adding indirection —
# that is a fail against this chunk's AC7, not a partial credit. Usage:
#
#   coordinator-assemble.py <name> [-- <args for name>] [<name2> [-- <args>] ...]
#
# Each `<name>` must be one of entry_point_shim.ASSEMBLE_TARGETS. Args for a
# given subcommand run from the token after its name up to (but not
# including) the next recognized subcommand name, OR up to a literal `--`
# token immediately following the name (the `--` itself is consumed, not
# forwarded) — the `--` form disambiguates an argument that happens to
# collide with another target's bare name. All subcommands run in this
# same process, in argv order, each via `entry_point_shim.run_target`.
#
# Exit code: 0 iff every subcommand returned 0. Otherwise the exit code of
# the FIRST subcommand that returned non-zero (matches shell `&&`-chained
# semantics of running the same names as separate processes, one failure
# stopping the story at that point being visible via this process's own
# exit code) — every subcommand still runs; this dispatcher does not abort
# early on a mid-batch failure, since the 13 targets are independent reads/
# writes over disjoint artifacts, not a pipeline.
#
# Spec backlink: docs/plans/2026-08-16-a-process-per-predicate.md, chunk C8
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


_USAGE_FAIL = 2


def _parse_batch(argv: List[str]) -> List[Tuple[str, List[str]]]:
    """Split argv into (subcommand_name, subcommand_argv) groups."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import ASSEMBLE_TARGETS, UnknownTargetError

    batch: List[Tuple[str, List[str]]] = []
    i = 0
    n = len(argv)
    while i < n:
        name = argv[i]
        if name not in ASSEMBLE_TARGETS:
            raise UnknownTargetError(name)
        i += 1
        if i < n and argv[i] == "--":
            i += 1
        args: List[str] = []
        while i < n and argv[i] not in ASSEMBLE_TARGETS:
            args.append(argv[i])
            i += 1
        batch.append((name, args))
    return batch


def main(argv: List[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import ASSEMBLE_TARGETS, UnknownTargetError, run_target

    if not argv or argv[0] in ("--help", "-h", "help"):
        names = "\n  ".join(ASSEMBLE_TARGETS)
        usage = (
            "usage: coordinator-assemble <name> [-- <args>] [<name2> [-- <args>] ...]\n"
            "\n"
            "Runs one or more -assemble entry points IN ONE INTERPRETER. Batching is\n"
            "the point: eight predicates as eight processes measured p90 6337.80ms\n"
            "against 883.83ms for the same eight in one process (7.17x -- see\n"
            "coordinator_core/benchmarks/shim_decision_record_fanin.json). Invoking\n"
            "this once per name reproduces the cost it exists to remove.\n"
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
        print(f"coordinator-assemble: unknown subcommand: {exc}", file=sys.stderr)
        return _USAGE_FAIL

    exit_code = 0
    for name, args in batch:
        rc = run_target(name, args)
        if rc != 0 and exit_code == 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
