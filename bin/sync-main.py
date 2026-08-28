# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sync-main.py — CLI trampoline over claude-klabauter coordinator_core.ops.sync_main.

Ensures local `main` == `origin/main` before any branch creation in the
coordinator pipeline. Every branch-creation site calls this before
`git checkout -b main`; after this script succeeds, local main matches
origin/main regardless of which branch the working tree is currently on.
Fail-loud: exits non-zero on a claude-klabauter-link failure rather than proceeding as
if the sync had succeeded.
"""
from __future__ import annotations
# sync-main.py — CLI trampoline over claude-klabauter coordinator_core.ops.sync_main.
#
# Ensures local `main` == `origin/main` before any branch creation. Every
# branch-creation site in the coordinator pipeline calls this before
# `git checkout -b main` — after this script succeeds, local main == origin/main
# regardless of which branch the working tree is on.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# Exit convention (fail-loud, matches the retired bash oracle): unlike the
# never-block `coordinator-auto-push` shape, sync-main is a gate a caller relies
# on for correctness (branch-creation invariant) — sys.exit(1) on a
# claude-klabauter-link failure, mirroring the oracle's own `die()` semantics rather than
# silently proceeding as if the sync had succeeded.
#
# Spec backlink: archive/specs/2026-05-01-orphan-branch-prevention.md § 1.1.5
# Prior bash implementation: see git log (sync-main.py, 124 lines, retired on
# this cutover)

import os
import sys

def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.sync_main import main as _op_main

    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"sync-main.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"sync-main.py: coordinator_core.ops.sync_main not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
