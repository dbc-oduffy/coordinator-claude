# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
blocked.py — CLI trampoline over claude-klabauter coordinator_core.ops.blocked.

Finish-strangler port: the bash implementation (two-part blocked-work
detector — blocked/paused handoffs via query-records.js, blocked/paused
tasks/*/todo.md lines via direct scan) has been ported to
coordinator_core/ops/blocked.py, co-located test in
coordinator_core/ops/test_blocked.py. This file is now a thin DoE-side
(contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE
owns contract/generator, claude-klabauter owns engine).

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

Exit convention (fail-loud, matches the bash oracle): the bash script exits
1 only when NOT run inside a git repository (an ERROR line to stderr); every
other path — found items, no items — exits 0. This trampoline preserves
that exact split: a claude-klabauter-link failure (the engine root unresolved, module not
importable) is ALSO a fail-loud condition (this is a diagnostic tool whose
whole job is to report ground truth; silently exiting 0 on a broken link
would misreport "no blocked items" when the detector never actually ran) —
sys.exit(1) on link failure, NOT sys.exit(0).

Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T2
"""

from __future__ import annotations

import os
import sys


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke.

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
    # Point the ported module at THIS script's own directory for
    # query-records.js -- mirrors the bash oracle's `$SCRIPT_DIR` exactly.
    os.environ.setdefault(
        "BLOCKED_QUERY_RECORDS_DIR", os.path.dirname(os.path.abspath(__file__))
    )
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"blocked.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"blocked.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.blocked", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"blocked.py: coordinator_core.ops.blocked not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
