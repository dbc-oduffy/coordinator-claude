"""
coordinator-reap-stale-locks — CLI trampoline over claude-klabauter
coordinator_core.ops.reap_stale_locks.

Purpose: conservative self-heal for the orphaned-`.git/index.lock` failure mode under
concurrent-EM on Git-for-Windows. The root cause is NOT coordinator code (auto-push
only pushes; safe-commit's lock is `.overlap-gate.lock`, never `index.lock`). It is a
Windows file-sharing artifact: a foreground `git add`/`git commit` writes a full index
copy to `index.lock`, and the final `rename(index.lock -> index)`/unlink can fail with
a sharing violation when another process (a concurrent session's git, antivirus, the
search indexer, or git's *detached* auto-maintenance child) holds a handle. The
commit's objects+ref are already durable (commit "succeeds") but the orphan lock
survives and blocks every subsequent commit in that worktree with:
  fatal: Unable to create '.../.git/index.lock': File exists.

`.git/index.lock` carries NO holder PID, so liveness cannot be read from the lock
itself. The reaper gates on TWO conservative conditions, both of which must hold
before any removal: AGE (far beyond any legitimate commit; maintenance gets a larger
floor) and STABLE (mtime+size unchanged across a short re-sample window). A fresh or
actively-mutating lock is NEVER reaped — fail-safe, the caller proceeds (or fails
loud) rather than risk corrupting a genuinely in-flight commit's index.

Finish-strangler port: the bash implementation (age/stability gate, index.lock +
next-index-*.lock + maintenance.lock coverage, reap-log emission) has been fully
ported to coordinator_core/ops/reap_stale_locks.py (claude-klabauter), with its
coordinator/lib/coordinator-session.sh sourcing severed entirely — that port needed
none of that library's session/liveness/claim machinery, only portable stat helpers,
which the port replaces with os.stat. This file is now a thin DoE-side trampoline over
that claude-klabauter (engine) module, per DR-047 (DoE owns contract, claude-klabauter owns engine).

This op is pure engine logic — no DoE-side input/output paths to resolve or hand over
via env var (unlike emit-artifact-shape-contract's schemas/ dependency); it operates
entirely on the CALLER's git worktree via `git rev-parse`, resolved from cwd. No
sys.argv is consumed — the bash oracle never inspected `$@` either (see the claude-klabauter
module's own docstring, Review: code-reviewer Finding 1).

Exit codes (parity-critical — matches coordinator_core.ops.reap_stale_locks.main
exactly; see that module's docstring for the full contract):
  0 — clean: nothing to reap, or all stale locks reaped successfully.
  2 — a FRESH index.lock is present (a live commit may be in progress); not reaped.
      Informational for the caller — distinct from a hard error.
  1 — hard error (not in a git repo, or a reap was attempted and unlink failed).
  2 (also, transport code) — engine-root resolution failed or
      coordinator_core.ops.reap_stale_locks not importable. Shares the numeral with
      the business "fresh index.lock" code above (both were already 2 under the bash
      oracle's own contract — nothing new collides here) but is printed with a
      distinct, greppable stderr remediation line so the two are never confused in
      practice.

Always safe to call repeatedly (idempotent) and from a hot path (commit pre-flight).
coordinator-safe-commit:1146 subprocess-execs this file by co-located path, fail-open;
this trampoline stays directly executable at the same path so that caller is unaffected.

Spec backlink: cross-repo/inbox/2026-05-30-index-lock-leak-concurrent-em.md (example-game-repo
    consult); docs/wiki/concurrent-em-hazards.md § H21.
"""

import os
import sys


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import the shared in-process
    runner.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is deliberately
    NOT used here (variant-#1 direct-import trampoline).

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by importing and calling its `main` directly, so the reap-log
    write it declares becomes a session scope-touch claim. Without that, the
    reap log this reaper appends is an orphan at the `scoped_git_commit` sink.
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
        print(f"coordinator-reap-stale-locks: engine-root resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"coordinator-reap-stale-locks: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main("coordinator_core.ops.reap_stale_locks", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"coordinator-reap-stale-locks: coordinator_core.ops.reap_stale_locks not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
