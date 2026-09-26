# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""review-brightline-gate.py — mechanical partition-vs-single-reviewer gate.

CLI trampoline over claude-klabauter coordinator_core.ops.review_brightline_gate, used
at /workstream-complete Step 2.9 to decide whether a diff must be reviewed
as a partitioned multi-chunk slice or a single reviewer suffices. Computes
loc/commits/surfaces over a git range and prints a
VERDICT={PARTITION-MANDATORY|single-reviewer-ok} line; any one threshold
(loc>=500, commits>=5, surfaces>=4) trips PARTITION-MANDATORY.
"""
from __future__ import annotations
# `range=… loc=… commits=… surfaces=… files=… [filtered_to=…] VERDICT={PARTITION-MANDATORY|single-reviewer-ok}`.
# Thresholds (any one trips PARTITION-MANDATORY): loc>=500 (gross insertions+

import os
import sys

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.review_brightline_gate import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"review-brightline-gate.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"review-brightline-gate.py: coordinator_core.ops.review_brightline_gate not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
