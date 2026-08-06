"""
check-auto-memory-drained.py — CLI trampoline over
coordinator_core.ops.check_auto_memory_drained.

Same shape as coordinator/bin/check-harvest-debt.py (its structure is copied
verbatim below, only the target op module/entrypoint differs): a thin
contract-side trampoline over the engine-side op module, per DR-047 (the
contract plane owns contract/generator, the engine plane owns engine).

Exit convention: UNLIKE check-harvest-debt.py, this IS a commit/ceremony
gate (C13/AC15), not an advisory nudge — a trampoline/transport failure
(CLAUDE_KLABAUTER_ROOT unresolvable, module not importable) still exits 0 (fail-open
on the SEAM, matching every other ceremony-gate trampoline in this directory
(e.g. check-harvest-debt.py) — a broken
install must never silently block every closure ceremony), but once the op
itself runs, its exit code (0 drained/absent, 1 residue found) is passed
through unchanged.

Spec backlink: DoE-claude
  docs/plans/2026-07-30-boot-doctrine-cut-and-refill-gate.md § C13, AC15.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here. Copied verbatim from check-harvest-debt.py.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.check_auto_memory_drained import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-auto-memory-drained: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"check-auto-memory-drained: coordinator_core.ops.check_auto_memory_drained "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
