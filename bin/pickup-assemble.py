# Trampoline for coordinator_core.pickup_brief, routed by
# entry_point_shim.run_target("pickup-assemble", ...).
#
# Subcommand: pickup-assemble brief <artifact> [--no-claim]
#     `brief` writes no tracked content. A single-artifact `brief` takes the
#     brief-stage pickup claim and adopts the artifact into the session baton,
#     so the session's next /handoff supersedes it. `--no-claim` (or a
#     multi-artifact ` AND ` survey) is the read-only inspection form.

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("pickup-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
