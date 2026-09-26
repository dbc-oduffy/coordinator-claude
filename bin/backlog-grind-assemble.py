#     "dogfood"). READ-ONLY — mutates nothing. Dispatched to
#     which receives this trampoline's argv VERBATIM — flags are parsed
#     -- never machine-absolute). READ-ONLY -- and specifically NEVER
#     VERBATIM -- the verb's own FLAGS are parsed there and need no mirror
#     dispatch table. MUTATING. Dispatched to
#     is a QUEUE-GENERIC door, not a bug-blitz-specific one — `grind-row` is

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target

    return run_target("backlog-grind-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
