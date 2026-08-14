"""
install-claude-klabauter-precommit-hook — CLI trampoline over claude-klabauter
coordinator_core.ops.install_claude_klabauter_precommit_hook.

Installs (or upgrades/appends onto an existing custom hook) claude-klabauter's
OWN `.git/hooks/pre-commit` gate chain — identity-gated to claude-klabauter
itself (a non-claude-klabauter target repo is a clean no-op skip). See that op
module's docstring for the gate registry, the fail-loud discipline, and the
exit-code clamping that guarantees this hook body only ever exits 0 or 1.

Exit convention: this is a config-writer/gate-installer, not a never-block
hook. A claude-klabauter-link failure (CLAUDE_KLABAUTER_ROOT unresolvable, module not
importable) means the installer literally could not run — silently exiting
0 would read as "hook installed" to a caller (`scripts/setup.py`,
`/coordinator:setup`) when it was not, so this trampoline exits 1 on
CLAUDE_KLABAUTER_ROOT resolution or import failure. The op's own internal skip paths
(not a git repo, not claude-klabauter, already installed) all still exit 0.

Usage:
    install-claude-klabauter-precommit-hook [target-repo-root]

    target-repo-root defaults to the current working directory.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT and import the in-process runner.

    DR-276: routes through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so the pre-commit hook file this
    op writes becomes a session scope-touch claim instead of an orphan at
    the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"install-claude-klabauter-precommit-hook: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except ImportError as exc:
        print(
            "install-claude-klabauter-precommit-hook: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        code = run_op_main("coordinator_core.ops.install_claude_klabauter_precommit_hook", sys.argv[1:])
    except ImportError as exc:
        print(
            "install-claude-klabauter-precommit-hook: "
            f"coordinator_core.ops.install_claude_klabauter_precommit_hook not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
