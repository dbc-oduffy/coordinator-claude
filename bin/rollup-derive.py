# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""rollup-derive.py — CLI trampoline over claude-klabauter coordinator_core.ops.rollup_derive.

Derives an artifact's roll-up ship-state on demand, with no cached or stored
state: finds every commit whose message carries a `Resolves: <artifact-id>`
trailer, then checks whether those commits are all on origin/main. Emits a
token (shipped / not-shipped / unknown-error / no-resolving-commits) plus the
resolving SHAs to stdout. Read-only — never stores, caches, or stamps a
roll-up result anywhere.
"""
from __future__ import annotations
# rollup-derive.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.rollup_derive.
#
# Derive an artifact's roll-up ship-state from its resolving commits, on
# demand, with no cached/stored state: finds every commit whose message
# carries a `Resolves: <artifact-id>` trailer, then checks whether those
# commits are all on origin/main.
#
# Usage:
#   rollup-derive.py <artifact-id>
#
# Output (stdout):
#   <token>
#   <resolving-sha> [<resolving-sha> ...]   (omitted if no-resolving-commits)
#
# Tokens:
#   shipped               all resolving commits are on origin/main
#   not-shipped            >=1 resolving commit is not on origin/main
#   unknown-error          repo/ref error (not a git repo, or origin/main unreachable)
#   no-resolving-commits   no commits found with a Resolves: <artifact-id> trailer
#
# Exit codes: 0 — normal completion (including the no-resolving-commits vacuous
# pass and the unknown-error/not-inside-a-git-repo case — the TOKEN carries the
# error signal, not the process exit code); 1 — CLI usage error (no arg passed,
# or an empty artifact-id).
#
# Spec backlink: DoE-claude:pln-lifecycle-vocab-c2-durable-cro-991bd4 § C5
# Port of: coordinator/bin/rollup-derive.py (bash body retired on cutover; see git log)
# Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
#
# Negative-spec: read-only. Never stores, caches, or stamps a roll-up result
# anywhere. Does NOT collapse "unknown" into "not-shipped" — that would let a
# promotion decision treat "could not determine" as "confirmed not shipped".

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402


def _import_runner():
    """Resolve the engine root, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so any paths it declares become
    a session scope-touch claim instead of an unclaimed orphan at the
    `scoped_git_commit` sink.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    # Matches the ported module's own token contract (see docstring above): a
    # "could not determine" outcome — including a claude-klabauter-link failure, which
    # is just another flavor of "could not determine" — is reported as the
    # `unknown-error` TOKEN on stdout with exit 0, never collapsed into the
    # CLI-usage-error exit-1 path (that's reserved for bad args, per the
    # ported module's own argv handling).
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print("unknown-error")
        print(f"rollup-derive: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(0)
    except ImportError as exc:
        print("unknown-error")
        print(
            f"rollup-derive: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        code = run_op_main("coordinator_core.ops.rollup_derive", sys.argv[1:])
    except ImportError as exc:
        print("unknown-error")
        print(
            f"rollup-derive: coordinator_core.ops.rollup_derive not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    sys.exit(code)


if __name__ == "__main__":
    main()
