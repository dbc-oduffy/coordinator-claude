"""
check-auto-memory-drained.py — CLI trampoline over
coordinator_core.ops.check_auto_memory_drained.

Same shape as coordinator/bin/check-harvest-debt.py (its structure is copied
verbatim below, only the target op module/entrypoint differs): a thin
contract-side trampoline over the engine-side op module, per DR-047 (the
contract plane owns contract/generator, the engine plane owns engine).

Exit convention: UNLIKE check-harvest-debt.py, this IS a commit/ceremony
gate (C13/AC15), not an advisory nudge — a trampoline/transport failure
(the engine root unresolvable, module not importable) still exits 0 (fail-open
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


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here. Copied verbatim from check-harvest-debt.py.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.check_auto_memory_drained import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"check-auto-memory-drained: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(
            f"check-auto-memory-drained: coordinator_core.ops.check_auto_memory_drained "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
