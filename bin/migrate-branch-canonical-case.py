# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
migrate-branch-canonical-case.py — CLI trampoline over claude-klabauter
coordinator_core.ops.migrate_branch_canonical_case.

Finish-strangler port (DR-059): the bash implementation (one-shot mixed-case
work/* branch remediation — HEAD-text fix + local ref rename + optional
remote cleanup) has been fully ported to
coordinator_core/ops/migrate_branch_canonical_case.py, with co-located test
test_migrate_branch_canonical_case.py. This file is now a thin DoE-side
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

This is a fail-loud operator remediation tool (one-shot rerunnable script,
not a hot per-commit hook), so unlike coordinator-auto-push (which must
never block a commit and always exits 0), a claude-klabauter-link failure here exits
1 — the operator needs to know the remediation did NOT run, not have it
silently swallowed.

Spec backlink: docs/plans/2026-05-07-mixed-case-branch-creation-tripwire.md
               docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
Prior bash implementation: see git log (migrate-branch-canonical-case.py,
141 lines, retired on this cutover)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Plain in-process import, not an RPC invoke — this is an operator-run,
    not-registered-as-an-op module (see the claude-klabauter module's own docstring),
    so cc_invoke's subprocess-spawn transport is deliberately not used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.migrate_branch_canonical_case import main as _op_main

    return _op_main


def main() -> None:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"migrate-branch-canonical-case.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            "migrate-branch-canonical-case.py: "
            f"coordinator_core.ops.migrate_branch_canonical_case not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
