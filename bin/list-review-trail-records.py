# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
list-review-trail-records.py — CLI trampoline over claude-klabauter
coordinator_core.ops.list_review_trail_records.

Finish-strangler port (clean-slate migration): the bash implementation
(union reader for state/review-trail/**/*.json and archive/review-trail/**/*.json,
sorted by basename) has been fully ported to
coordinator_core/ops/list_review_trail_records.py, with a co-located pytest
(test_list_review_trail_records.py). This file is now a thin DoE-side
(contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
contract/generator, claude-klabauter owns engine).

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

Exit convention: this is a FAIL-LOUD reader — the original oracle exits 1 on
tool failure, bad --date-prefix, or unresolvable state root. A claude-klabauter-link
failure (the engine root unresolvable, or the ported module not importable) is
the same class of failure and also exits 1 here (NOT the never-block
exit-0 convention used by hook-shaped scripts like coordinator-auto-push).

Op registered? NO — plain module, direct import (template variant #1). This
is a read-only CLI reader, not a JSON-RPC op; no registry edits.

Spec backlink: docs/plans/2026-05-28-archive-aware-review-oracle-and-audit-skill.md § Chunk C0
               docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys


def _import_run_op_main():
    """Resolve the engine root and import `run_op_main` (DR-276: routes the op
    in-process through `coordinator_core.cli_entry` rather than a plain
    `_import_main()` + `sys.exit(op_main(argv))` tail, so any path the op
    declares via `declare_write` becomes a session scope-touch claim instead
    of an unclaimed orphan at the `scoped_git_commit` sink)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"list-review-trail-records.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"list-review-trail-records.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        return 1
    try:
        code = run_op_main("coordinator_core.ops.list_review_trail_records", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(f"list-review-trail-records.py: coordinator_core.ops.list_review_trail_records not importable: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
