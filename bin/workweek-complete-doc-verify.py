# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import sys
from pathlib import Path

def main(argv: "list[str] | None" = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3

    from coordinator_core.cli_entry import run_op_main

    return run_op_main("coordinator_core.ops.doc_content_verify", (sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
