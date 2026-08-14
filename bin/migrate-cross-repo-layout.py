# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""migrate-cross-repo-layout.py — one-time idempotent cross-repo memo layout migration.

Re-homes a repo's cross-repo memo channel from the legacy flat layout to the
inbox/archive co-located layout: `cross-repo/*.md` (non-README) moves into
`cross-repo/inbox/`, `archive/cross-repo/*` moves into `cross-repo/archive/`,
and the now-empty top-level `archive/cross-repo/` is removed. Migration logic
lives claude-klabauter-side in coordinator_core.ops.migrate_cross_repo_layout; this
file is a thin DoE-side trampoline.
"""

from __future__ import annotations

# migrate-cross-repo-layout — CLI trampoline over claude-klabauter
# coordinator_core.ops.migrate_cross_repo_layout.
#
# One-time idempotent migration primitive: re-homes a repo's cross-repo memo
# channel from the legacy flat layout to the inbox/archive co-located layout.
#   - cross-repo/*.md (non-README) -> cross-repo/inbox/
#   - archive/cross-repo/*         -> cross-repo/archive/
#   - Removes top-level archive/cross-repo/ if empty after moves.
#
# Finish-strangler port (bash->naked-Python engine migration, BIG_PORT wave):
# the bash implementation has been fully ported to
# coordinator_core/ops/migrate_cross_repo_layout.py (co-located pytest:
# coordinator_core/ops/test_migrate_cross_repo_layout.py). This file is now a
# thin DoE-side (contract) trampoline over that claude-klabauter (engine) module, per
# DR-047 (DoE owns contract/generator, claude-klabauter owns engine).
#
# Not a JSON-RPC op — plain in-process import + call (template-variant #1),
# same shape as coordinator-auto-push / handoff-gate-aging. This is a
# single-shot local file-move op with no hot-path/per-commit pressure, so the
# extra subprocess hop an IPC/cc_invoke() round-trip would add buys nothing.
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
# Usage:
#   cd <repo-root>
#   ./migrate-cross-repo-layout.py
#
#   Or with explicit repo root:
#   ./migrate-cross-repo-layout.py --root /path/to/repo
#
# Exit codes (parity with the bash oracle, and with the ported module's own
# contract — see coordinator_core/ops/migrate_cross_repo_layout.py docstring):
#   0 — success (N moves or idempotent no-op)
#   1 — usage/environment error or target-collision detected
#   2 — one or more move operations failed
#   3 — claude-klabauter-link (transport) failure: CLAUDE_KLABAUTER_ROOT unresolvable or
#       coordinator_core.ops.migrate_cross_repo_layout not importable. This is
#       a DEDICATED code distinct from the business codes 0/1/2 above (porter-
#       brief addendum §3b) — a fail-loud script must not let a caller
#       misclassify a claude-klabauter-link outage as a legitimate business outcome
#       (e.g. confusing it with rc=1's usage/collision meaning).
#
# Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk F
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
#
# DR-276: routed through coordinator_core.cli_entry.run_op_main rather than a
# bare in-process main() call, so the files this migration moves become a
# session scope-touch claim instead of orphans at the scoped_git_commit sink.

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import cli_entry.run_op_main.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"migrate-cross-repo-layout: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    except ImportError as exc:
        print(
            "migrate-cross-repo-layout: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main("coordinator_core.ops.migrate_cross_repo_layout", sys.argv[1:])
    except ImportError as exc:
        print(
            "migrate-cross-repo-layout: "
            f"coordinator_core.ops.migrate_cross_repo_layout not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(code)


if __name__ == "__main__":
    main()
