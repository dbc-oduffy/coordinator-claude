"""
coordinator-ensure-prepare-commit-msg-hook — idempotent install/repair of the
Session-Id trailer prepare-commit-msg hook in the current git repo.

Native-Python port (DR-059 de-bash, Windows-first). Logic lives in
lib/git_hook_install.py; this is the thin entrypoint. The INSTALLED
.git/hooks/prepare-commit-msg body it writes is bash-free (probes python, invokes
the polyglot coordinator-prepare-commit-msg directly) so it fires on a Windows box
that has sh + python but no bash — the case the bash predecessor silently no-op'd on.

Runs from session-init on every session boot, and from /repo-setup § 3f.5.6.
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
    """Put the repo root on ``sys.path`` before ``git_hook_install`` is
    imported.

    git_hook_install.py imports from the coordinator_core package
    (win_portability, py_probe_sh) at module level -- that package is
    resolvable only from the repo root, not from _LIB_DIR, so it must be on
    sys.path too or the import below raises ModuleNotFoundError every time
    this entrypoint runs as a subprocess (which is how it is invoked from
    session-init and from the test suite).

    Idempotent; safe to call more than once. Moved out of module scope
    (2026-08-28) -- unconditionally mutating `sys.path` at import time made
    every import of this file mutate the `sys.path` of a warm server ~50
    sessions share. Only the trigger moved; the effect is byte-for-byte the
    same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    _BOOTSTRAP_DONE = True


def main(argv: "list[str] | None" = None) -> int:
    # argv threading: this CLI reads sys.argv at depth (argparse and helpers),
    # so the warm-call path swaps it for the duration rather than rewriting every read.
    # NOT re-entrant: a threaded server must serialise calls into this entrypoint.
    _bootstrap_engine()
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from git_hook_install import ensure_prepare_commit_msg_hook

    _prev_argv = sys.argv
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        # `--fleet` was hand-parsed here between 2026-08-08 (b66dec143) and
        # 2026-08-11; fleet-wide healing now has its own named entrypoint,
        # `coordinator-ensure-hooks-fleet`. The flag is answered rather than
        # ignored: a caller that still passes it would otherwise get a
        # single-repo heal reported as a fleet heal -- the accepted-and-ignored
        # shape doe-claude-em refused to write into /workday-start Step -0.45
        # (cross-repo/inbox/2026-08-11-doe-claude-em-fleet-flag-request-is-not-
        # actionable-entrypoints-read-no-argv.md). Redirect is stderr-only and
        # still exits 0 via the cwd heal below: this runs on the session-boot
        # path and must never block a session start.
        if "--fleet" in sys.argv[1:]:
            print(
                "coordinator-ensure-prepare-commit-msg-hook: --fleet is no longer "
                "handled here -- run `coordinator-ensure-hooks-fleet` for every "
                "registered repo. Healing this repo only.",
                file=sys.stderr,
            )
        try:
            return ensure_prepare_commit_msg_hook(_BIN_DIR)
        except Exception as exc:  # never block a session start
            print(f"coordinator-ensure-prepare-commit-msg-hook: {exc}", file=sys.stderr)
            return 0
    finally:
        sys.argv = _prev_argv


if __name__ == "__main__":
    sys.exit(main())
