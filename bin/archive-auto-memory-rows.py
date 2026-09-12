"""
archive-auto-memory-rows.py — CLI trampoline over
coordinator_core.ops.archive_auto_memory_rows.

Same shape as coordinator/bin/check-auto-memory-drained.py (its structure is
copied verbatim below, only the target op module/entrypoint and exit
convention differ): a thin contract-side trampoline over the engine-side op
module, per DR-047 (the contract plane owns contract/generator, the engine
plane owns engine).

Exit convention: UNLIKE check-auto-memory-drained.py, this is a WRITE-then-
COMMIT op, not an advisory gate, so a trampoline/transport failure (the
engine root unresolvable, module not importable) is a genuine failure to
archive, not a broken install that must never block a ceremony -- it exits
1 rather than 0, naming the failure on stderr. Once the op itself runs, its
own exit code (0 archived/nothing-to-archive, 1 failed) is passed through
unchanged.

Spec backlink: this repo
  docs/plans/2026-08-07-archive-on-drain-memory-evicts-to-cold-tier.md § C7.
"""

from __future__ import annotations

import sys


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here. Copied verbatim from
    check-auto-memory-drained.py.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.archive_auto_memory_rows import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"archive-auto-memory-rows: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"archive-auto-memory-rows: coordinator_core.ops.archive_auto_memory_rows "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
