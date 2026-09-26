"""
coordinator-ensure-prepare-commit-msg-hook — idempotent install/repair of the
Session-Id trailer prepare-commit-msg hook in the current git repo.

Native-Python port (DR-059 de-bash, Windows-first). Logic lives in
lib/git_hook_install.py; this is the thin entrypoint. The INSTALLED
.git/hooks/prepare-commit-msg body it writes is bash-free (probes python, invokes
the polyglot coordinator-prepare-commit-msg directly) so it fires on a Windows box
that has sh + python but no bash — the case the bash predecessor silently no-op'd on.

Invoked fleet-wide by `coordinator-ensure-hooks-fleet` at /workday-start Step -0.45
and by scripts/cloud_setup.py's cloud pre-boot install, and directly from
/repo-setup § 3f.5.6.
Idempotent; always exits 0 — must never block a session start.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § git-hook-installers-port
Prior bash implementation: see git log (coordinator-ensure-prepare-commit-msg-hook, retired on this cutover)
"""
from __future__ import annotations

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
_REPO_ROOT = os.path.dirname(os.path.dirname(_BIN_DIR))

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True


def main(argv: "list[str] | None" = None) -> int:
    _bootstrap_engine()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from git_hook_install import ensure_prepare_commit_msg_hook

    _prev_argv = sys.argv
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        if "--fleet" in sys.argv[1:]:
            print(
                "coordinator-ensure-prepare-commit-msg-hook: --fleet is no longer "
                "handled here -- run `coordinator-ensure-hooks-fleet` for every "
                "registered repo. Healing this repo only.",
                file=sys.stderr,
            )
        try:
            return ensure_prepare_commit_msg_hook(_BIN_DIR)
        except Exception as exc:
            print(f"coordinator-ensure-prepare-commit-msg-hook: {exc}", file=sys.stderr)
            return 0
    finally:
        sys.argv = _prev_argv


if __name__ == "__main__":
    sys.exit(main())
