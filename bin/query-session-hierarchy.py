# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""query-session-hierarchy.py — reverse-query interface over the session/workstream hierarchy.

CLI trampoline over claude-klabauter coordinator_core.ops.session_hierarchy_query,
operating over the union of all per-machine session-hierarchy projection
shards (state/session-hierarchy.<machine>.json). Given a workstream slug,
returns its member session_ids; given a session_id, returns its workstream,
branch, parent_session_id, and session_type.
"""
from __future__ import annotations
# query-session-hierarchy.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.session_hierarchy_query.
#
# Reverse-query interface over the per-machine session/workstream hierarchy
# projection shards (state/session-hierarchy.<machine>.json). Given a
# workstream slug, returns the session_ids that belong to it. Given a
# session_id, returns its workstream, branch, parent_session_id, and
# session_type. Operates over the UNION of all per-machine shards.
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
#   query-session-hierarchy.py --workstream <slug>
#   query-session-hierarchy.py --session <session_id>
#   query-session-hierarchy.py [--help | -h]
#
# Exit codes: 0 — success (incl. empty --workstream result); 1 — not-found /
# shard-resolution error / engine-root-link failure; 2 — argument error.
#
# Spec backlink: docs/plans/2026-06-27-ccos-5-session-workstream-hierarchy-record.md § C3
# Port of: coordinator/bin/query-session-hierarchy.py (retired bash body on cutover; see git log)

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    no coordinator_core.invoke subprocess is spawned for this read-only query.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so any paths it declares become a
    session scope-touch claim (session_hierarchy_query is read-only today,
    but the seam is uniform across every trampoline over this route).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"query-session-hierarchy.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"query-session-hierarchy.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.session_hierarchy_query", sys.argv[1:])
    except ImportError as exc:
        print(
            f"query-session-hierarchy.py: coordinator_core.ops.session_hierarchy_query not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
