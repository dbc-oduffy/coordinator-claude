# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""prune-resolved-queue-entries.py — strips resolved-state bloat from legacy prose queues.

CLI trampoline over claude-klabauter coordinator_core.ops.prune_resolved_queue_entries.
Applies 8 pattern rules (entry-shape, section-body, ceremony-lines,
H3-closure-block, strikethrough-closure, table-row-closure, buffer-orphan-guard)
to improvement-queue.md and bug-backlog.md, invoked from /update-docs
(Phase 11i, S5) to keep the legacy queue files from accreting closed entries.
"""
# prune-resolved-queue-entries.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.prune_resolved_queue_entries.
#
# Strips resolved-state bloat (8 pattern rules: entry-shape, section-body,
# ceremony-lines, H3-closure-block, strikethrough-closure, table-row-closure,
# buffer-orphan-guard) from the legacy prose queue files improvement-queue.md
# and bug-backlog.md. Invoked from /update-docs (Phase 11i, S5).
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
#   prune-resolved-queue-entries.py <queue-file>
#
# Exit codes (parity-critical — matches the ported module's own contract):
#   0 — file pruned and atomically replaced (or no changes needed)
#   1 — usage error, disallowed basename, or file-not-found (business
#       failure — fails loud with a stderr message, never skips silently)
#   2 — claude-klabauter-link transport failure (the engine root unresolvable, or
#       coordinator_core.ops.prune_resolved_queue_entries not importable) —
#       a DEDICATED code, distinct from both business codes above, so a
#       caller (e.g. /update-docs) cannot mistake a claude-klabauter outage for a
#       legitimate "nothing to prune" / "bad input" result. This is a
#       fail-loud validator script (it mutates a queue file in place), not a
#       best-effort/never-block script like coordinator-auto-push — so
#       transport failure does NOT degrade to exit 0 here.
#
# Spec backlink: docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5
#                (lives in consumer-project docs/plans/, not in this plugin tree)
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
# Port of: prune-resolved-queue-entries.sh (DoE b5a4192c, 2026-07-20) — the
#          8-rule awk program's fixture-diff regression net
#          (prune-resolved-queue-entries.test.sh, DoE 3a561713, 2026-07-22)
#          was ported to pytest claude-klabauter-side as
#          coordinator_core/ops/test_prune_resolved_queue_entries.py.

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
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the file it atomically
    replaces becomes a session scope-touch claim. Without that, this file's
    write is an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"prune-resolved-queue-entries.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    except ImportError as exc:
        print(
            f"prune-resolved-queue-entries.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main(
            "coordinator_core.ops.prune_resolved_queue_entries", sys.argv[1:]
        )
    except ImportError as exc:
        print(
            "prune-resolved-queue-entries.py: "
            f"coordinator_core.ops.prune_resolved_queue_entries not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
