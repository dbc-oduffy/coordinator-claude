# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-ps51-clean.py — CLI trampoline over claude-klabauter coordinator_core.ops.verify_ps51_clean.

Repo-agnostic smoke check asserting Windows PowerShell .ps1 setup/install
legs are PS-5.1-clean: they parse under the Windows PowerShell 5.1 console
host (not pwsh 7) and contain no pwsh-7-only syntax. Four-way per-file
classification (OK / FAIL / EXPECTED-PS7 / WARN); shared home in coordinator
bin/ — each consuming repo (coordinator, example-game-workbench-repo) calls it
pointing at its own .ps1 set.
"""
# syntax patterns. Four-way per-file classification (OK / FAIL / EXPECTED-PS7 /
# its CREATE_NO_WINDOW popup guard, lives entirely in the claude-klabauter module — this
# Exit:  0 if all files parse-clean under PS 5.1 (WARN/EXPECTED-PS7 are still 0),
#          failure or the op module is not importable) — a DEDICATED code so a
#          PORTER-BRIEF-ADDENDUM § 3b.
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (BIG_PORT wave A)

import os
import sys

def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here (template-variant #1, direct-import trampoline;
    this op has no @register_op — it is a plain module, not a JSON-RPC op).

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"verify-ps51-clean.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"verify-ps51-clean.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    try:
        code = run_op_main("coordinator_core.ops.verify_ps51_clean", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"verify-ps51-clean.py: coordinator_core.ops.verify_ps51_clean not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())
