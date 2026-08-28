"""
install-doe-claude-precommit-hook — CLI trampoline over claude-klabauter
coordinator_core.ops.install_doe_claude_precommit_hook.

Installs (or upgrades/appends onto an existing custom hook) DoE-claude's OWN
`.git/hooks/pre-commit` gate chain — identity-gated via the canonical
DoE-root resolver (`coordinator_core.doe_root_pointer`, registry-first over
`repos.doe_claude`); an unresolved or non-matching target is a clean no-op
skip. See that op module's docstring for the gate registry, the fail-loud
discipline, and the exit-code clamping that guarantees this hook body only
ever exits 0 or 1.

Naming note: `doe_claude` is an explicitly KEPT slug in
`coordinator_core.ops.check_registry_codename_leak` (`KEEPSET`, with the
reason recorded at its definition — the OSS clone resolver already reads
`repos.doe_claude`). Naming the repo here is therefore sanctioned, not a
leak, and a generic paraphrase would conceal nothing while this file's own
name, module path, and identifiers all carry the slug regardless.

Exit convention: this is a config-writer/gate-installer, not a never-block
hook. A claude-klabauter-link failure (the engine root unresolvable, module not
importable) means the installer literally could not run — silently exiting
0 would read as "hook installed" to a caller (`scripts/setup.py`,
`/coordinator:setup`) when it was not, so this trampoline exits 1 on
engine-root resolution or import failure. The op's own internal skip paths
(not a git repo, not DoE-claude, unresolved root, already
installed) all still exit 0.

Usage:
    install-doe-claude-precommit-hook [target-repo-root]

    target-repo-root defaults to the current working directory.
"""

from __future__ import annotations

import os
import sys

def _import_runner():
    """Resolve the engine root and import the in-process runner.

    DR-276: routes through `coordinator_core.cli_entry.run_op_main` rather
    than calling the op's `main` directly, so the pre-commit hook file this
    op writes becomes a session scope-touch claim instead of an orphan at
    the `scoped_git_commit` sink.
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
        print(
            f"install-doe-claude-precommit-hook: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ImportError as exc:
        print(
            "install-doe-claude-precommit-hook: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        code = run_op_main(
            "coordinator_core.ops.install_doe_claude_precommit_hook", (sys.argv[1:] if argv is None else argv)
        )
    except ImportError as exc:
        print(
            "install-doe-claude-precommit-hook: "
            f"coordinator_core.ops.install_doe_claude_precommit_hook not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
