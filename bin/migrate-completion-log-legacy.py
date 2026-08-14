# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
migrate-completion-log-legacy.py — CLI trampoline over claude-klabauter
coordinator_core.ops.migrate_completion_log_legacy.

Idempotent migration helper: moves legacy monthly monolith files
(archive/completed/YYYY-MM.md) under archive/completed/legacy/ so the
completion-log query tooling (query-completions.py) can ignore them without
needing special-case glob exclusions.

Invocation contexts:
  PM-invoked one-shot: run manually when first adopting the per-entry layout.
  Per-close-out wrap: invoked automatically by coordinator-complete-entry.py
    (step 2.6.2) at each workstream close-out when a root monolith is
    detected. Full idempotency (re-entrant, safe to call repeatedly) makes
    this safe.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Usage:
  cd <repo-root>
  python ~/.claude/plugins/coordinator/bin/migrate-completion-log-legacy.py

Or, with an explicit repo root:
  migrate-completion-log-legacy.py --root <path>
  REPO_ROOT=/path/to/repo MIGRATION_REPO_ROOT=/path/to/repo migrate-completion-log-legacy.py

Root resolution order: explicit --root flag > MIGRATION_REPO_ROOT env var >
`git rev-parse --show-toplevel` auto-discovery > hard error.

Exit codes (matches the retired bash oracle exactly):
  0 — success (0 or more files moved, or no-op)
  1 — usage or environment error (not in a repo with archive/completed/)
  2 — one or more git mv operations failed

Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 7
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
Prior bash implementation: see git log (migrate-completion-log-legacy.py
body, 176 lines, retired on this cutover)

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain `sys.exit(op_main(argv))` tail, so the `git mv` destinations the ported
module declares via `declare_write` become a session scope-touch claim — a
plain in-process import never reaches `ipc.dispatch_message`, the sole
chokepoint that already turns a subprocess handler's self-reported writes
into that claim.
Spec backlink: docs/decisions/DR-276-operator-clis-record-session-writes-at-a.md
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the run_op_main runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the `git mv` destination
    it declares (`declare_write(dst)`) becomes a session scope-touch claim.
    Without that, every file this CLI moves is an orphan at the
    `scoped_git_commit` sink.
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
            f"migrate-completion-log-legacy.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            "migrate-completion-log-legacy.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.migrate_completion_log_legacy", sys.argv[1:])
    except ImportError as exc:
        print(
            "migrate-completion-log-legacy.py: "
            f"coordinator_core.ops.migrate_completion_log_legacy not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
