# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""workweek-complete-reverse-drift-gate.py — CLI trampoline over claude-klabauter
coordinator_core.ops.workweek_reverse_drift_gate.

/workweek-complete Step 4g blocking merge gate for copy_install plugin
mirrors: discovers each registered `reverse_drift_cmd` (delegated to
list-reverse-drift-cmds' already-ported registry read), runs it from its
plugin's source_path, and folds the discovery reader's 3-way rc plus every
per-command pass/fail into one exit code.

CLI: [--scope-repo <repo-root>]   (default: `git rev-parse --show-toplevel`,
                                    falling back to cwd)

Exit codes: propagates coordinator_core.ops.workweek_reverse_drift_gate.main's
own 0/1 business contract verbatim (see that module's docstring for the full
rc semantics, incl. the COORDINATOR_OVERRIDE_REVERSE_DRIFT=1 escape hatch). A
missing/unresolvable engine root (this trampoline's OWN transport failure,
distinct from the ported module's business exit code) exits 1 — a fail-loud
gate feeder must never let a claude-klabauter-link outage silently pass a merge gate.

Port source: coordinator/commands/workweek-complete.md § Step 4g (DoE-claude),
the per-plugin execution loop with 3-way rc branching.
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
"""
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _prepare_claude_klabauter_root() -> None:
    """Resolve the engine root and put it on sys.path.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so any paths it
    declares via `declare_write()` become a session scope-touch claim instead
    of landing unclaimed as an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()


def main() -> None:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(
            f"workweek-complete-reverse-drift-gate: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.workweek_reverse_drift_gate", sys.argv[1:])
    except ImportError as exc:
        print(
            "workweek-complete-reverse-drift-gate: "
            f"coordinator_core.ops.workweek_reverse_drift_gate not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
