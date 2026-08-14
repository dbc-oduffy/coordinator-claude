# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-rag-state.py — CLI trampoline over claude-klabauter coordinator_core.ops.check_rag_state.

Finish-strangler port: the bash implementation (env-var fast-path → marker-file
read → unknown fallback, plus the DoE-root/plugin-root trust-guard preflight)
has been fully ported to coordinator_core/ops/check_rag_state.py, with a
co-located pytest (test_check_rag_state.py, 16 tests).

Port source: coordinator/bin/check-rag-state.py (this file, pre-port bash body
retired; see git log)
Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292

This is a **direct-import trampoline** (template-variant #1) — no JSON-RPC
op registration, no cc_invoke() round trip. `check-rag-state.py` is invoked
synchronously and frequently (update-docs, enrich-and-review, repomap gating)
but is not a per-commit hot path; direct import still avoids a second
subprocess hop for no benefit, same rationale as coordinator-auto-push.

Exit-code convention: this is a FAIL-LOUD gate-shaped script (its own bash
oracle `exit 1`s on both "state is unknown" and "DoE-root/trust preflight
failed") — the trampoline preserves that: sys.exit(1) on CLAUDE_KLABAUTER_ROOT
resolution failure or import failure, exactly like handoff-gate-aging, NOT
the auto-push "never block" exit-0 shape.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _prepare_claude_klabauter_root() -> None:
    """DR-276: routes through `coordinator_core.cli_entry.run_op_main` so any
    `declare_write()`d paths become a session scope-touch claim rather than an
    unclaimed orphan at the `scoped_git_commit` sink."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)


def main() -> None:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"check-rag-state.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.check_rag_state", sys.argv[1:])
    except ImportError as exc:
        print(f"check-rag-state.py: coordinator_core.ops.check_rag_state not importable: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
