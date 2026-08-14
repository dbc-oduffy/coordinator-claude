# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
assert-no-dangling-plan-backlinks.py — CLI trampoline over claude-klabauter
coordinator_core.ops.assert_no_dangling_plan_backlinks.

AC9 gate for programmatic terminal-plan archival: after the C4 backfill moves
a terminal plan docs/plans/<name>.md -> archive/specs/YYYY-MM/<name>.md,
every spec_backlink that still cites the old docs/plans/ path dangles. This
gate asserts ZERO such dangling backlinks in active doctrine surfaces, and
--fix repoints them to the archive location. The bash implementation (111
lines, declare -A moved-plan map, perl-based --fix rewrite) has been ported
to coordinator_core/ops/assert_no_dangling_plan_backlinks.py (13 tests in the
co-located test_assert_no_dangling_plan_backlinks.py) per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine). This file is now a thin DoE-side
trampoline over that claude-klabauter module.

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

Exit convention: this is a fail-loud GATE script (asserts zero dangling
backlinks; used at doc-hygiene/distill cadence), NOT a never-block hook like
coordinator-auto-push — a claude-klabauter-link failure (CLAUDE_KLABAUTER_ROOT unresolved, module
not importable) exits 1 here, not 0, so the failure is visible rather than
silently swallowed.

Spec backlink: archive/specs/2026-06/2026-06-23-programmatic-terminal-plan-archival.md § AC9 / C6
               docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Prior bash implementation: see git log (assert-no-dangling-plan-backlinks.py, 111 lines, retired on this cutover)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 in-process
    runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    calling the op's `main` directly, so the `--fix` write it declares becomes
    a session scope-touch claim instead of an orphan at the
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
            f"assert-no-dangling-plan-backlinks.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            f"assert-no-dangling-plan-backlinks.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.assert_no_dangling_plan_backlinks", sys.argv[1:])
    except ImportError as exc:
        print(
            "assert-no-dangling-plan-backlinks.py: "
            f"coordinator_core.ops.assert_no_dangling_plan_backlinks not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
