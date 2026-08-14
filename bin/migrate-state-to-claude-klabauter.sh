# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""migrate-state-to-claude-klabauter.sh — idempotent migration of ~/.claude working data to the engine repo.

Two-phase cross-repo excision: `--populate` copies (never removes) state/,
docs/{plans,research,problems}/, and archive/ into the engine repo; `--finalize`
delta re-syncs, guards per-path, then removes the ~/.claude originals only
after the C3/C4/C12 repoint and C11 dogfood consistency gate. Copy/guard/
remove logic lives claude-klabauter-side in coordinator_core.ops.migrate_state_to_claude_klabauter
(DR-047: DoE owns contract, claude-klabauter owns engine); this file is a thin argv
passthrough.

Two subcommands:
    --populate (C6a) — COPY (do NOT remove) source trees into claude-klabauter.
                        Idempotent; safe to re-run. Originals stay UNTOUCHED.
    --finalize (C6b) — delta re-sync, then per-path guard, then remove
                        ~/.claude originals. DO NOT RUN until after:
                        C3/C4/C12 repoint + C11 dogfood consistency gate.

Environment overrides:
    CLAUDE_KLABAUTER_ROOT  — override the claude-klabauter repo path (skips machine-local lookup).
    CLAUDE_HOME  — override the ~/.claude meta-repo path.

Exit codes (parity-critical):
    0 — success (populate complete, or finalize complete)
    1 — business error: no subcommand / unknown subcommand, CLAUDE_HOME not
        found, or (--finalize only) the pre-removal guard found source files
        with no confirmed claude-klabauter copy (fail-closed; nothing was removed)
    2 — transport failure: CLAUDE_KLABAUTER_ROOT could not be resolved, or
        coordinator_core.ops.migrate_state_to_claude_klabauter is not importable. This
        is a fail-loud script (a partial/unverified migration is worse than a
        loud abort) — a claude-klabauter-link failure gets this DEDICATED code rather
        than colliding with either business code above (porter addendum §3/3b).

Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787
               § Phase 2 / C6 / AC5 / § Execution Notes (C6a/C6b split)
               docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
Port of: migrate-state-to-claude-klabauter.sh (DoE b5a4192c, 2026-07-20)
"""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import `run_op_main`.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: routed through `coordinator_core.cli_entry.run_op_main` rather
    than importing the op's `main` directly, so every file it copies (and,
    on `--finalize`, the destination it verified before removing sources)
    becomes a session scope-touch claim instead of an unclaimed orphan at
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
        print(f"migrate-state-to-claude-klabauter.sh: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(2)
    except ImportError as exc:
        print(
            f"migrate-state-to-claude-klabauter.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        code = run_op_main("coordinator_core.ops.migrate_state_to_claude_klabauter", sys.argv[1:])
    except ImportError as exc:
        print(
            f"migrate-state-to-claude-klabauter.sh: coordinator_core.ops.migrate_state_to_claude_klabauter not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(code)


if __name__ == "__main__":
    main()
