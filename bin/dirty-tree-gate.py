# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
dirty-tree-gate.py — CLI trampoline over claude-klabauter coordinator_core.ops.dirty_tree_gate.

Pre-terminate dirty-tree gate — classify every dirty working-tree path as
(a) session-authored (staged), (b) known concurrent owner, or (c)
unattributable. Exits 0 when all dirty paths are (a) or (b). Exits 3, listing
case-(c) paths one per line on stdout, when any unattributable file remains.

Usage: dirty-tree-gate.py --terminator <token>

Exit codes:
    0  all dirty paths attributable (phantom / staged-a / consumed-handoff-b)
    1  engine-root resolution or coordinator_core import failure (fail-loud —
       this is a gate script; a silent claude-klabauter-link failure must not let a
       dirty-tree pre-terminate check silently pass)
    2  usage error (missing --terminator, not a git repo)
    3  one or more case-(c) unattributable paths remain (listed on stdout)

The full classifier logic, the case-(c) stderr trailer, and the
concurrent-EM-peer disposition ladder now live in
coordinator_core.ops.dirty_tree_gate (claude-klabauter) — see that module's
docstring for the negative-spec, including the deliberately-preserved
silent-degrade behavior when the shared coordinator-state-root.py resolver
fails (matches the pre-port bash oracle's unchecked `source` behavior).

Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md C2
"""

from __future__ import annotations

import os
import sys

def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.dirty_tree_gate import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"dirty-tree-gate.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"dirty-tree-gate.py: coordinator_core.ops.dirty_tree_gate not importable: {exc}", file=sys.stderr)
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
