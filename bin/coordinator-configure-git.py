"""
coordinator-configure-git — CLI trampoline over claude-klabauter
coordinator_core.ops.configure_git.

Applies coordinator's git-config hardening to a repo — two content-neutral,
idempotent local-config settings (`gc.autoDetach false`, `core.checkStat
minimal`) that mitigate concurrent-EM index.lock leaks and Git-for-Windows/
NTFS phantom-dirty-index churn. See the ported module's docstring
(coordinator_core/ops/configure_git.py) for the full per-setting rationale;
this file is now a thin DoE-side trampoline, the bash oracle having been
fully ported (landed claude-klabauter-side at f5aa81c6).

Usage:
  coordinator-configure-git            # configure the current repo
  coordinator-configure-git --global    # set the machine-wide default

Exit codes (parity-critical — matches coordinator_core.ops.configure_git.main
exactly):
  0 — configured (or already correct).
  1 — business failure: not a git repository (per-repo mode only), or a
      `git config` set call failed.
  2 — DEDICATED transport/config-failure code, distinct from both business
      codes above: CLAUDE_KLABAUTER_ROOT resolution failed, or
      coordinator_core.ops.configure_git was not importable.

Spec backlink: cross-repo/inbox/2026-05-30-index-lock-leak-concurrent-em.md
               (example-game-repo consult); docs/wiki/concurrent-em-hazards.md § H21.
Prior bash implementation: see git log (coordinator/bin/coordinator-configure-git,
                           81 lines, retired on this cutover).
"""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the DR-276 in-process
    runner.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather than
    calling the op's `main` directly, so any declared write becomes a session
    scope-touch claim instead of an orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"coordinator-configure-git: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"coordinator-configure-git: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.configure_git", sys.argv[1:])
    except ImportError as exc:
        print(
            f"coordinator-configure-git: coordinator_core.ops.configure_git not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
