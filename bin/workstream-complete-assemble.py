# Spec backlink: docs/plans/2026-07-21-canonical-resolution-engine.md, chunk W2-B1 [DEAD-CITATION: plan file never committed to this repo]
#     READ-ONLY — mutates nothing (coordinator_core.workstream_complete

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from entry_point_shim import run_target  # noqa: E402

    return run_target("workstream-complete-assemble", argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
