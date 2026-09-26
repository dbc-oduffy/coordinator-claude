

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_gate_target

    return run_gate_target("check-posix-exec-assumptions", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
