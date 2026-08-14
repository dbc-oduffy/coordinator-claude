"""
coordinator-ensure-post-commit-hook — idempotent install/repair of the
crash-insurance post-commit auto-push hook in the current git repo.

Native-Python port (DR-059 de-bash, Windows-first). Logic lives in
lib/git_hook_install.py; this is the thin entrypoint. The INSTALLED
.git/hooks/post-commit body it writes is bash-free (probes python, invokes the
polyglot coordinator-auto-push directly) so it fires on a Windows box that has
sh + python but no bash — the case the bash predecessor silently no-op'd on.

Runs from session-init on every session boot inside any coordinator-aware repo,
and from /repo-setup § 3f.5. Idempotent and near-zero cost. Always exits 0 —
must never block a session start.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § git-hook-installers-port
Prior bash implementation: see git log (coordinator-ensure-post-commit-hook, retired on this cutover)
"""
from __future__ import annotations

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
# git_hook_install.py imports from the coordinator_core package (win_portability,
# py_probe_sh) at module level -- that package is resolvable only from the repo
# root, not from _LIB_DIR, so it must be on sys.path too or the import below
# raises ModuleNotFoundError every time this entrypoint runs as a subprocess
# (which is how it is invoked from session-init and from the test suite).
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from git_hook_install import ensure_post_commit_hook  # noqa: E402


def main() -> int:
    try:
        return ensure_post_commit_hook(_BIN_DIR)
    except Exception as exc:  # never block a session start
        print(f"coordinator-ensure-post-commit-hook: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
