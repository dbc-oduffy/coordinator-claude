"""
coordinator/bin/doctor.py — the WS-9 out-of-harness health/repair command.

Run this from a plain terminal with NO Claude Code process involved:

    python3 <this-repo>/coordinator/bin/doctor.py [--fix]

(Windows: the paired `doctor.cmd` resolves an interpreter and runs this file
directly — no bash re-exec.) That out-of-harness invocation is the whole
point: five occurrences of the same incident class in two days (2026-07-28/
29) were a hook registration or synced config file going bad, with the
tools needed to repair it (Write, Edit, Bash) being exactly the tools the
break disabled. A guard that runs through the tool it guards can detect a
break but never repair it — see
docs/plans/2026-07-29-windows-viability-stop-the-spawn-storms.md WS-9 / AC-28
and DoE-claude state/2026-07-29-deleted-hook-scripts-bricked-every-write.md.

Layers checked, what's auto-repairable vs. detect-only, and the reasoning
behind the split all live in the actual implementation's module docstring:
coordinator_core.ops.doctor. This file is a thin CLI wrapper (per the R1
DOE-PORT template every coordinator/bin/ trampoline follows) — it resolves
the engine root via cc_invoke's resolve_colocated_claude_klabauter_root ladder (this
file's own coordinator/bin/ parent-of-parent location, tried first, zero
external dependency, cannot be unset) and calls straight into the op.

Exit code: 0 if every layer reports OK, 1 if any layer is BROKEN or UNKNOWN
(so a CI/pre-flight caller can gate on it if it wants to; this script itself
never gates anything — it only reports and, with --fix, repairs the one
safe class).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        return 1

    # DR-276: routed through coordinator_core.cli_entry.run_op_main rather than a
    # plain `from coordinator_core.ops.doctor import main` + direct call, so the
    # paths the op declares (--fix's hooks.json rewrite) become a session
    # scope-touch claim. Without that, everything this CLI writes is an orphan
    # at the `scoped_git_commit` sink.
    from coordinator_core.cli_entry import run_op_main

    try:
        return run_op_main("coordinator_core.ops.doctor", argv[1:])
    except ImportError as _exc:
        print(f"{Path(__file__).name}: coordinator_core.ops.doctor not importable: {_exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
