"""normalize-consumed-frontmatter.py — reconciles a record's frontmatter with its consumed marker.

Flips a record's frontmatter to match its body's `<!-- consumed: YYYY-MM-DD
[notes] -->` marker: status -> consumed, deployment_state -> shipped,
consumed_at/shipped_in insertion, gate_dependency strip. A byte-parity port
of the retired node oracle's own module; engine logic lives claude-klabauter-side in
coordinator_core.ops.normalize_claimed_frontmatter (module renamed from
normalize_consumed_frontmatter per DR-084), and this file is a thin DoE-side
trampoline (direct in-process import, no subprocess re-spawn tax).
"""
from __future__ import annotations
# `<!-- consumed: YYYY-MM-DD [notes] -->` marker (status -> consumed,
#   3 — TRANSPORT failure: engine-root resolution or

import os
import sys


def _import_runner():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"normalize-consumed-frontmatter.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 3
    except ImportError as exc:
        print(
            "normalize-consumed-frontmatter.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3

    try:
        code = run_op_main("coordinator_core.ops.normalize_claimed_frontmatter", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "normalize-consumed-frontmatter.py: "
            f"coordinator_core.ops.normalize_claimed_frontmatter not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())
