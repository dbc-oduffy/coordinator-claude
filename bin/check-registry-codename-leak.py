# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-registry-codename-leak.sh — CLI trampoline over claude-klabauter
coordinator_core.ops.check_registry_codename_leak.

Finish-strangler port: the bash implementation (registry-derived novel-leak
guard — greps a target dir for private-repo codenames from the machine-local
registry's repos.* keys, after subtracting the D1 keep-set) has been fully
ported to coordinator_core/ops/check_registry_codename_leak.py (co-located
pytest: test_check_registry_codename_leak.py). This file is now a thin
DoE-side (contract) trampoline over that claude-klabauter (engine) module, per DR-047
(DoE owns contract/generator, claude-klabauter owns engine).

Fail-loud exit convention: this is a gate script (publish-tree leak guard) —
on claude-klabauter-link failure, exit 2 (usage/internal-error code, matching the
original script's own convention for "could not run the check"), NOT 0.
A silent exit 0 here would mean a percolate publish proceeds without the leak
check ever running — the opposite of what a fail-closed gate must do.

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

Spec backlink: docs/plans/2026-06-27-genericize-provenance-sweeper.md § C4 / AC11
               docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` for
    baseline consistency — this op is a pure read/grep gate (see module
    docstring), so it declares nothing and this conversion changes no
    observable behavior."""
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"check-registry-codename-leak.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(f"check-registry-codename-leak.sh: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.check_registry_codename_leak", sys.argv[1:])
    except ImportError as exc:
        print(f"check-registry-codename-leak.sh: coordinator_core.ops.check_registry_codename_leak not importable: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(code)


if __name__ == "__main__":
    main()
