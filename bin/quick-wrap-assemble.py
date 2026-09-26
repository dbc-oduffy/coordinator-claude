#     READ-ONLY except for C5 (docs/plans/2026-08-20-the-close-ceremony-commits-what-the-
#     see module docstring "CALLER-OPT-IN, NOT A GLOBAL CARVE-OUT".
#   0 — OK, a decision object was computed and returned. This INCLUDES an

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("quick-wrap-assemble", argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
