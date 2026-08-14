# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-start-step0-reconcile.py — CLI trampoline over claude-klabauter
coordinator_core.ops.workday_start_step0_reconcile.

Finish-strangler port (DR-059): the bash implementation (Step 0.4.5 —
Reconcile with origin/main, called by workday-start-step0.py after the
precedence switch resolves on a non-main active branch) has been fully
ported to coordinator_core/ops/workday_start_step0_reconcile.py, co-located
test coordinator_core/ops/test_workday_start_step0_reconcile.py. This file
is now a thin DoE-side (contract) trampoline over that claude-klabauter (engine)
module, per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

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

Exit-code convention: this is a FAIL-LOUD gate script, not a never-block
hook (contrast coordinator-auto-push). A CLAUDE_KLABAUTER_ROOT-resolution or
import failure is a hard error — sys.exit(1) — matching the ported module's
own "1 — unexpected error" convention, never a silent exit 0.

Exit codes (parity-critical, unchanged from the bash oracle / ported module):
    0 — already-includes / fast-forward / merge succeeded.
    3 — merge conflict; PM resolves first.
    1 — unexpected error (including this trampoline's own link failure).

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292

DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than a
plain in-process `import ... as _op_main` + `sys.exit(op_main(argv))` tail, so
any paths the op declares via `declare_write` become a session scope-touch
claim (this op reconciles via `git merge`/`git fetch` subprocess calls only —
it never writes a repo file directly — so it declares none; routing it is a
baseline-shrink, not a behavior change).
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"workday-start-step0-reconcile.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            "workday-start-step0-reconcile.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.workday_start_step0_reconcile", sys.argv[1:])
    except ImportError as exc:
        print(
            "workday-start-step0-reconcile.py: "
            f"coordinator_core.ops.workday_start_step0_reconcile not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
