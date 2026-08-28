"""
cmd-autorun-guard.py — CLI trampoline over the engine-repo's
coordinator_core.ops.cmd_autorun_guard.

Closes the cmd.exe leg of the coordinator `claude` interception coverage
gap — see coordinator_core/ops/cmd_autorun_guard.py's own module docstring
for the full design rationale, negative-spec, and what this deliberately
does NOT close (`-NoProfile`/non-interactive PowerShell).

Usage:
    cmd-autorun-guard.py detect               # read-only; no mutation ever
    cmd-autorun-guard.py apply [--check-only]  # write the AutoRun guard
    cmd-autorun-guard.py strip [--check-only]  # uninstall leg — reverse it

`apply`/`strip` without `--check-only` mutate the operator's own HKCU
registry hive (`Software\\Microsoft\\Command Processor\\AutoRun`) — this is
a deliberate, explicit act; this trampoline does not run either verb on its
own on import or at install time.

No engine-root resolution is needed here beyond `cc_invoke`'s own helper —
mirrors this directory's other `install-*-wrapper.py` trampoline shape.

DR-276: the op runs through `coordinator_core.cli_entry.run_op_main` rather
than by calling its `main` directly, so any path it declares becomes a session
scope-touch claim. Calling `main` in-process without that leaves every write
unclaimed in `orphans` at the `scoped_git_commit` sink.
"""

from __future__ import annotations

import os
import sys


def main(argv: "list[str] | None" = None) -> int:
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        claude_klabauter_root = require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"cmd-autorun-guard.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1


    try:
        from coordinator_core.cli_entry import run_op_main
    except ImportError as exc:
        print(
            f"cmd-autorun-guard.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main("coordinator_core.ops.cmd_autorun_guard", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"cmd-autorun-guard.py: coordinator_core.ops.cmd_autorun_guard not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
