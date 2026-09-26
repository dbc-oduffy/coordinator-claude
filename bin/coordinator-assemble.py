# Each `<name>` must be one of entry_point_shim.ASSEMBLE_TARGETS. Args for a
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple


_USAGE_FAIL = 2


def _parse_batch(argv: List[str]) -> List[Tuple[str, List[str]]]:
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
