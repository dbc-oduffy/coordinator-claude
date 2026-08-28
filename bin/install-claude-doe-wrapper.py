# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
install-claude-doe-wrapper.py — CLI trampoline over claude-klabauter
coordinator_core.ops.install_claude_doe_wrapper.

Installs the co-located `coordinator/bin/claude-doe.py` wrapper onto
`${CLAUDE_HOME:-$HOME}/.local/bin/claude-doe`. Collapses the bash fence at
coordinator/commands/install.md line 892 (DoE-claude repo) into one call —
see coordinator_core.ops.install_claude_doe_wrapper's own docstring for the
full design rationale and negative-spec.

`--wrapper-src` defaults to this trampoline's own sibling `claude-doe.py` file
(this script and the wrapper it installs both live under
`<engine_root>/coordinator/bin/`) — no engine-root resolution is needed for
that default, since it is always co-located.

Spec backlink: docs/plans/2026-07-23-skills-carry-no-code-extirpation.md § M3/D9
"""

from __future__ import annotations

import os
import sys

def _default_wrapper_src() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-doe.py")


def _resolve_run_op_main():
    """DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than a bare `main` import, so any paths the op declares become a session
    scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _resolve_run_op_main()
    except RuntimeError as exc:
        print(f"install-claude-doe-wrapper.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"install-claude-doe-wrapper.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    argv = (sys.argv[1:] if argv is None else argv)
    if "--wrapper-src" not in argv:
        argv = argv + ["--wrapper-src", _default_wrapper_src()]

    try:
        code = run_op_main("coordinator_core.ops.install_claude_doe_wrapper", argv)
    except ImportError as exc:
        print(
            f"install-claude-doe-wrapper.py: coordinator_core.ops.install_claude_doe_wrapper "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    return code


if __name__ == "__main__":
    sys.exit(main())
