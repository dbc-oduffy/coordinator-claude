# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-subagent-sandbox-preamble-sync.py — sentinel-block sync gate for scoped subagent prompts.

Thin DoE-side (contract) trampoline over claude-klabauter's
coordinator_core.ops.verify_subagent_sandbox_preamble_sync. Checks (and, with
--fix, repairs) the `subagent-sandbox-preamble` sentinel block across the
scoped-agent CONSUMERS array — scouts/specialists/workers/checkers/auditors
only, never Opus personas or executor/review-integrator/enricher/docs-checker.
--list enumerates one consumer path per line.
"""
from __future__ import annotations
# block across the scoped-agent CONSUMERS array (scouts/specialists/workers/
#   1 — drift found (MISSING/MISMATCH/MISSING_END/MISSING_FILE — see the
#       (CLAUDE_PLUGIN_ROOT unset and doe_root() raised _DoeUnresolvable) —
# claude-klabauter module) because it is DoE-repo topology knowledge (CLAUDE_PLUGIN_ROOT

import os
import sys


def _resolve_plugin_root() -> str:
    """Resolve the plugin root (coordinator/) that owns agents/*.md.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. That
    used to be correct when this executable lived in DoE-claude
    (coordinator/bin/.. IS the plugin root there), but this file has since
    migrated to claude-klabauter (b644d5a9/8a28a6ca) while coordinator/agents/
    stayed put in DoE-claude — self-location now resolves to a directory
    with no agents/ at all, silently producing MISSING_FILE rows over a
    tree that never existed instead of a loud failure. doe_root() is the
    correct authority for "where is the DoE-claude repo," independent of
    where THIS script happens to run from. A future reader must not
    "restore" __file__-based resolution to regain oracle parity — that is
    precisely what caused this break.

    Fails loud (sys.exit(1)) if doe_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to an exit-0 no-op.
    """
    from coordinator_data_root import content_root_or_private
    from coordinator_registry import _DoeUnresolvable, doe_root

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-subagent-sandbox-preamble-sync.py: cannot resolve the coordinator doctrine repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(1)
    return content_root_or_private(root)


def _resolve_script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _import_runner():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    _prev_argv = sys.argv
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        try:
            run_op_main = _import_runner()
        except RuntimeError as exc:
            print(
                f"verify-subagent-sandbox-preamble-sync.py: engine-root resolution failed: {exc}",
                file=sys.stderr,
            )
            return 3
        except ImportError as exc:
            print(
                "verify-subagent-sandbox-preamble-sync.py: "
                f"coordinator_core.cli_entry not importable: {exc}",
                file=sys.stderr,
            )
            return 3
    
        plugin_root = _resolve_plugin_root()
        script_dir = _resolve_script_dir()
        mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    
        try:
            code = run_op_main(
                "coordinator_core.ops.verify_subagent_sandbox_preamble_sync",
                [plugin_root, script_dir, mode],
            )
        except ImportError as exc:
            print(
                "verify-subagent-sandbox-preamble-sync.py: "
                f"coordinator_core.ops.verify_subagent_sandbox_preamble_sync not importable: {exc}",
                file=sys.stderr,
            )
            return 3
    
        return code
    finally:
        sys.argv = _prev_argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
