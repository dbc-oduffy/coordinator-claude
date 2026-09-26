# READ-ONLY — mutates nothing. sizing_assemble.route() never writes a

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("sizing-assemble", argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
