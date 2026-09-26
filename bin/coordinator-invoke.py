
from __future__ import annotations

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.invoke.__main__ import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    del argv
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            "coordinator-invoke.py: engine unreachable (searched "
            "COORDINATOR_ENGINE_ROOT, machine-local pointer files, "
            "repos.claude_klabauter, self-location). Run: python3 "
            "<claude-klabauter>/scripts/setup.py (cloud box: scripts/cloud_setup.py)",
            file=sys.stderr,
        )
        print(f"coordinator-invoke.py: detail: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"coordinator-invoke.py: coordinator_core.invoke.__main__ "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    op_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
