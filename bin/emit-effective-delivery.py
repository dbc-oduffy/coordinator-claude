#!/usr/bin/env python3
from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.cli_entry import run_op_main
    except (RuntimeError, ImportError) as exc:
        sys.stderr.write("emit-effective-delivery: engine unreachable (%s)\n" % exc)
        return 2
    return run_op_main(
        "coordinator_core.ops.session.emit_effective_delivery",
        sys.argv[1:] if argv is None else argv,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
