#     artifact. READ-ONLY — mutates nothing (coordinator_core.pickup_assemble

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("pickup-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
