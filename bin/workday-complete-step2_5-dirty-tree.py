# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-complete-step2_5-dirty-tree.py — CLI trampoline over claude-klabauter
coordinator_core.ops.workday_complete_step2_5_dirty_tree.

Finish-strangler port: the bash implementation (Step 2.5 dirty-tree
auto-disposition classifier — EOL-phantom/submodule/leave-alone/orphan-tmp
skip rules, AUTO-GITIGNORE + AUTO-COMMIT act blocks, SOURCE-TREE/AMBIGUOUS
needs-PM classification, rename-source F8 fold) has been fully ported to
coordinator_core/ops/workday_complete_step2_5_dirty_tree.py (co-located
tests: test_workday_complete_step2_5_dirty_tree.py, including cross-repo
parity tests against this trampoline's own prior bash body). This file is
now a thin DoE-side (contract) trampoline over that claude-klabauter (engine) module,
per DR-047 (DoE owns contract/generator, claude-klabauter owns engine).

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

Exit codes (business codes 0/1/2 identical to the retired bash oracle — see
the claude-klabauter module's own docstring for the full classification-rule table;
rc=3 is this trampoline's own dedicated transport-failure code, per A3b,
and is never emitted by the claude-klabauter module itself):
    0 — all clear-wins handled (or nothing dirty); no source-tree/ambiguous
        paths remain.
    1 — hard error (not a git repo, `git status` failed, `.gitignore`
        unwriteable, a `git add`/`git rm --cached`/`git commit` failed).
    2 — clear-wins handled; source-tree or ambiguous paths remain (needs
        PM attention — printed as `NEEDS-PM` on stdout).
    3 — transport failure (CLAUDE_KLABAUTER_ROOT resolution failed, or
        coordinator_core.ops.workday_complete_step2_5_dirty_tree not
        importable) — a dedicated code, per code-review Finding 2
        (A3b), so a caller can distinguish "this machine's install/
        environment is broken" from "git status genuinely failed in
        this repo," which rc=1 conflated before this fix.

Spec backlink: commands/workday-complete.md § Step 2.5
Spec backlink: docs/plans/2026-07-16-bash-to-naked-python-engine-migration.md [DEAD-CITATION: plan file never committed to this repo]
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the run-op runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes (the `.gitignore` append) is an orphan at the `scoped_git_commit`
    sink.
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
        # Review: code-reviewer (F2) — rc=3 is a dedicated transport-failure code,
        # distinct from the module's own business codes (0/1/2), per A3b.
        print(
            f"workday-complete-step2_5-dirty-tree.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)
    except ImportError as exc:
        # Review: code-reviewer (F2) — same dedicated transport-failure code as above.
        print(
            "workday-complete-step2_5-dirty-tree.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    try:
        code = run_op_main(
            "coordinator_core.ops.workday_complete_step2_5_dirty_tree", sys.argv[1:]
        )
    except ImportError as exc:
        print(
            "workday-complete-step2_5-dirty-tree.py: "
            f"coordinator_core.ops.workday_complete_step2_5_dirty_tree not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)

    sys.exit(code)


if __name__ == "__main__":
    main()
