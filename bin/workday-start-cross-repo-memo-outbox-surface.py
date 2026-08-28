# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-start-cross-repo-memo-outbox-surface.py — CLI trampoline over claude-klabauter
coordinator_core.ops.workday_start_cross_repo_memo_outbox_surface.

Finish-strangler port (DR-047/DR-059): the bash implementation (outbox
stale-draft nudge surfacer — scans state/memo-outbox/ for drafts older than
the stale threshold) has been fully ported to
coordinator_core/ops/workday_start_cross_repo_memo_outbox_surface.py, with a
co-located pytest suite
(coordinator_core/ops/test_workday_start_cross_repo_memo_outbox_surface.py).
This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
(engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns
engine).

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

Always exits 0 — this is an orientation surfacer (offer-shape only: emits
three action verbs as options, never mutates), never a gate. A claude-klabauter-link
failure degrades to silent-no-nudge (matching the ported module's own
silent-degrade-on-resolver-failure negative-spec), not a blocking error.

Spec backlink: docs/plans/2026-06-15-cross-repo-memo-draft-lifecycle.md § C4
               docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Prior bash implementation: see git log (workday-start-cross-repo-memo-outbox-surface.py,
                            156 lines, retired on this cutover)
"""

from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        # Never block orientation on a transport failure — silent-degrade,
        # matching the ported module's own negative-spec.
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 0
    except ImportError as exc:
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: coordinator_core.cli_entry "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    try:
        code = run_op_main(
            "coordinator_core.ops.workday_start_cross_repo_memo_outbox_surface",
            (sys.argv[1:] if argv is None else argv),
        )
    except ImportError as exc:
        print(
            f"workday-start-cross-repo-memo-outbox-surface.py: coordinator_core.ops."
            f"workday_start_cross_repo_memo_outbox_surface not importable: {exc}",
            file=sys.stderr,
        )
        return 0

    return code


if __name__ == "__main__":
    sys.exit(main())
