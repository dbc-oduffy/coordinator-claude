from __future__ import annotations
# Port backlink: BIG_PORT Wave B, item roadmap-pair

import os
import sys

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.roadmap.number_stubs import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"roadmap-number-stubs: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"roadmap-number-stubs: coordinator_core.roadmap.number_stubs not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    try:
        return op_main((sys.argv[1:] if argv is None else argv))
    except Exception as exc:  # noqa: BLE001 — last-resort trampoline guard
        print(f"roadmap-number-stubs: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
