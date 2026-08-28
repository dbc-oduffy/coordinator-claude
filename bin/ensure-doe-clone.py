# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
ensure-doe-clone.py — CLI trampoline over claude-klabauter coordinator_core.ops.ensure_doe_clone.

Resolves the local DoE-claude clone path (REPO_DOE_CLAUDE env override, then
`machine-local get repos.doe_claude`) and clones it if the resolved directory
is not yet a git checkout. Collapses the two literal bash fences at
coordinator/commands/install.md lines 731 and 747 (DoE-claude repo) into one
call — see coordinator_core.ops.ensure_doe_clone's own docstring for the
full design rationale and negative-spec (this trampoline owns no logic of
its own beyond the standard engine-root resolve-and-import dance).

Spec backlink: DoE-claude:pln-extirpate-pasted-code-from-em--0f42e9 § M3/D9
"""

from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root and import `run_op_main`.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so the resolved DoE-clone path
    it declares (on an actual `git clone`) becomes a session scope-touch
    claim instead of an unclaimed orphan at the `scoped_git_commit` sink.
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
        print(f"ensure-doe-clone.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"ensure-doe-clone.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    try:
        code = run_op_main("coordinator_core.ops.ensure_doe_clone", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"ensure-doe-clone.py: coordinator_core.ops.ensure_doe_clone not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
