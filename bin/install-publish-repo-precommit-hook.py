# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
install-publish-repo-precommit-hook.py — CLI trampoline over claude-klabauter
coordinator_core.ops.install_publish_repo_precommit_hook.

Installs the OSS publish-repo pre-commit exec-bit drift gate + illegal-path
gate. Idempotent, conditional on canonical-path identity match against the
caller-supplied EXPECTED_REPO_ROOT positional argument.

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

Usage:
  install-publish-repo-precommit-hook.py <EXPECTED_REPO_ROOT>

Exit codes: always 0 (fail-soft / never-block-install shape — this is an
install-time convenience installer, not a commit-time gate; a skip or a
foreign-hook offer is not an error state for the caller, e.g. install.sh).

Spec backlinks:
  docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 5
  docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D4
Port source: coordinator/bin/install-publish-repo-precommit-hook.py (DoE-claude, pre-port)
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md (residual)
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the in-process runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the pre-commit hook file
    this op writes becomes a session scope-touch claim instead of an orphan
    at the `scoped_git_commit` sink.
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
            f"install-publish-repo-precommit-hook.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)
    except ImportError as exc:
        print(
            "install-publish-repo-precommit-hook.py: "
            f"coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.install_publish_repo_precommit_hook", sys.argv[1:])
    except ImportError as exc:
        print(
            "install-publish-repo-precommit-hook.py: "
            f"coordinator_core.ops.install_publish_repo_precommit_hook not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
