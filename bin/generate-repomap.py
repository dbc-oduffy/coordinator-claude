# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import os
import sys

# owned by this trampoline) -- until that lands, this pair reads UNSTAMPED,
GENERATES = [
    {
        "artifact": ".claude/repomap.md",
        "stamp_key": "generated",
        "sources": ["coordinator/bin/repomap/generate-repomap.py"],
    },
]


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.generate_repomap import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"generate-repomap.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"generate-repomap.py: coordinator_core.ops.generate_repomap not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    # ${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)} —
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    return op_main((sys.argv[1:] if argv is None else argv), plugin_root=plugin_root, site=sys.argv[0])


if __name__ == "__main__":
    sys.exit(main())
