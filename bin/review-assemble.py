#     the shared decision-object envelope). READ-ONLY — mutates nothing.
#     FALLTHROUGH: a bare invocation with no subcommand token briefs.

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("review-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
