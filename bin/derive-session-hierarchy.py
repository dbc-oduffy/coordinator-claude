"""
derive-session-hierarchy — CLI trampoline over claude-klabauter
coordinator_core.ops.session_hierarchy_derive.

Derives the session/workstream hierarchy projection from handoff frontmatter
lineage (a consumed handoff's ``consumed_by`` IS the harness session_id of the
consuming session) and writes a full-rebuild, atomic, per-machine shard to
``<claude-klabauter-root>/state/session-hierarchy.<machine-slug>.json``.

This op always targets claude-klabauter's OWN checkout (post-migration, handoffs live
there) — it does NOT read/write anything under this repo's tree, regardless
of where this trampoline is invoked from. No arguments; the engine root is
resolved via the usual ladder (env var -> settings-home pointer file ->
Coordinator-claude-klabauter-root.sh), same as every other claude-klabauter-backed trampoline.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).

Usage:
  derive-session-hierarchy

Exit codes: 0 — derived + written; 1 — engine root / import / engine-worktree
resolution failed.

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292 § T3a-g3c
Port of: derive-session-hierarchy.sh (DoE f0aa2d56, 2026-07-16)
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 op runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"derive-session-hierarchy: engine-root resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"derive-session-hierarchy: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main(
            "coordinator_core.ops.session_hierarchy_derive", sys.argv[1:]
        )
    except ImportError as exc:
        print(
            f"derive-session-hierarchy: coordinator_core.ops.session_hierarchy_derive "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
