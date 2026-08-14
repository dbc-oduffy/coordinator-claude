# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
learn-lessons-config-update.py — CLI trampoline over claude-klabauter
coordinator_core.ops.learn_lessons_config_update.

Ensures the cwd repo is discoverable by learn-lessons. Discovery roots are
derived PER-MACHINE from the machine-local [repos] registry (see
learn-lessons-roots.py) — this script does NOT append absolute paths to any
committed config file (that accretion baked one machine's paths into a
git-tracked file and did not survive a machine change; retired 2026-06-19).

Behavior: if the cwd repo is already a learn-lessons root (the meta-repo
$CLAUDE_HOME itself, or a registered [repos] entry), silent no-op. Otherwise
prints a one-line hint to stderr advising registration via machine-local.
NEVER mutates a tracked file. Always exits 0 (idempotent; safe as a Phase 0
call) -- including when the claude-klabauter link itself fails, per the FAIL-LOUD vs
NEVER-BLOCK split below.

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

Exit convention: this is a never-block advisory (matches the original bash
script's own `exit 0` always-convention, documented in its header as "Always
exits 0 (idempotent; safe as a Phase 0 call)"). A claude-klabauter-link failure
(CLAUDE_KLABAUTER_ROOT unresolvable, module not importable) is therefore ALSO reported
on stderr and exits 0, not 1 -- unlike a fail-loud gate/config-writer
trampoline, this script must never block whatever Phase-0 flow invokes it.

Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292
Prior bash implementation: see git log (learn-lessons-config-update.py, 49 lines)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_run_op_main():
    """Resolve CLAUDE_KLABAUTER_ROOT and import `run_op_main` (DR-276: routes the op
    in-process through `coordinator_core.cli_entry` rather than a plain
    `_import_main()` + `sys.exit(op_main(argv))` tail, so any path the op
    declares via `declare_write` becomes a session scope-touch claim instead
    of an unclaimed orphan at the `scoped_git_commit` sink)."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"learn-lessons-config-update.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print(
            f"learn-lessons-config-update.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    try:
        code = run_op_main("coordinator_core.ops.learn_lessons_config_update", sys.argv[1:])
    except ImportError as exc:
        print(
            f"learn-lessons-config-update.py: coordinator_core.ops.learn_lessons_config_update not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
