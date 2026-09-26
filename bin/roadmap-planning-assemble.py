# entry_point_shim.py's ASSEMBLE_TARGETS dispatch table): a plain
# inside main(), only after CLAUDE_KLABAUTER_ROOT resolves. Mirrors sizing-assemble's
# READ-ONLY — mutates nothing. roadmap_planning_assemble.brief() never
# writes a stub/OVERVIEW/spine record; it returns the routing fields for a
from __future__ import annotations

import os
import sys


_TRANSPORT_FAIL = 3


def _main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

    try:
        require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"roadmap-planning-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    try:
        import coordinator_core.roadmap_planning_assemble as mod
    except ImportError as exc:
        print(
            f"roadmap-planning-assemble: coordinator_core.roadmap_planning_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return mod.main(argv)


def main(argv: list[str]) -> int:
    return _main(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
