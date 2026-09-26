from __future__ import annotations
# Finish-strangler port (BIG_PORT Wave B, 2026-07-17): the node implementation
# Session self-claim (SCOPE-DROP CLOSED 2026-07-27): the oracle used to
# own docstring — HARDENED per the 2026-07-17 porter-brief addendum, NOT
#   1 — BUSINESS fail: --check found out-of-sync file(s), OR a callout hit a
#   3 — TRANSPORT failure: the record-query layer is unavailable/broken. Once

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.text.refresh_queries import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"refresh-queries.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"refresh-queries.py: coordinator_core.text.refresh_queries not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
