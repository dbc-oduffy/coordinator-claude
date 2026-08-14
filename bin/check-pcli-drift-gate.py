# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-pcli-drift-gate.py — CLI trampoline over claude-klabauter
coordinator_core.ops.check_pcli_drift_gate.

Detects divergence between the `dispatch_feed` contract and the captured
live `Workflow` `agent()` option surface (both owned by the sibling DoE
repo's schema files), plus capture staleness and a C7
subagent-catering-resolution.json source-hash check. Direct-import shape
(same as check-harvest-debt.py), deliberately NOT the registered-op
`cc_invoke.route()` trampoline shape (schema-drift-gate.py's shape) — the
detection module is a plain, unregistered coordinator_core.ops module
(mirrors check_import_budget_staleness.py), so there is no op name to route
through. This CLI owns argument parsing and exit-code mapping only; all
detection logic lives in coordinator_core.ops.check_pcli_drift_gate.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in the sibling DoE repo's coordinator/docs/wiki/bash-on-windows-gotchas.md
§ Carve-out (cross-repo — that wiki lives in the sibling repo, not here).

Exit codes: this is a BLOCKING gate, not an advisory nudge — a transport
failure (CLAUDE_KLABAUTER_ROOT unresolvable, module not importable) maps to
EXIT_ERROR (2), never a silent 0. Business-logic exit codes (0 PASS / 1 FAIL
/ 2 ERROR) are otherwise produced by
coordinator_core.ops.check_pcli_drift_gate.main() once import succeeds —
see that module's own docstring for the full three-way contract.

Usage:
    check-pcli-drift-gate.py

Spec backlink: state/handoffs/2026-08-13-pcli-04-drift-gate.md
Spec backlink: state/debt-backlog/2026-08-13-pcli-04-drift-gate-dispatch-feed-vs-the-bce793e4e50e.yaml
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

_EXIT_ERROR = 2


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported
    entrypoint. Plain in-process import (not cc_invoke's subprocess-spawn
    RPC transport) — same shape as check-harvest-debt.py's `_import_main`."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.check_pcli_drift_gate import main as _op_main

    return _op_main


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print(f"check-pcli-drift-gate.py: unexpected argument(s): {' '.join(argv)}", file=sys.stderr)
        return _EXIT_ERROR

    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-pcli-drift-gate.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except ImportError as exc:
        print(
            f"check-pcli-drift-gate.py: coordinator_core.ops.check_pcli_drift_gate not importable: {exc}",
            file=sys.stderr,
        )
        return _EXIT_ERROR

    return op_main([])


if __name__ == "__main__":
    sys.exit(main())
