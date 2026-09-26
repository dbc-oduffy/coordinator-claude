# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations
# Exit codes: 0 clean/no-mismatch, 1 on any MISMATCH/LIVE_MISSING/TMPL_MISSING
# module) because it is DoE-repo topology knowledge (CLAUDE_PLUGIN_ROOT env

import os
import sys


def _resolve_plugin_root() -> str:
    """Resolve the plugin root (coordinator/) that owns templates/bin/.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. That
    used to be correct when this executable lived in DoE-claude
    (coordinator/bin/.. IS the plugin root there), but this file has since
    migrated to the engine repo while coordinator/templates/bin/ stayed put
    in DoE-claude — self-location now resolves to a directory with no
    templates/ at all, silently producing five TMPL_MISSING lines instead
    of a loud failure. doe_root() is the correct authority for "where is
    the DoE-claude repo," independent of where THIS script happens to run
    from. A future reader must not "restore" __file__-based resolution to
    regain oracle parity — that is precisely what caused this break.

    Fails loud (sys.exit(1)) if doe_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to an exit-0 no-op.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import content_root_or_private
    from coordinator_registry import _DoeUnresolvable, doe_root

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-templates-bin-sync.py: cannot resolve the coordinator doctrine repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(1)
    return content_root_or_private(root)


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
            print(f"verify-templates-bin-sync.sh: engine-root resolution failed: {exc}", file=sys.stderr)
            return 1
        except ImportError as exc:
            print(
                f"verify-templates-bin-sync.sh: coordinator_core.cli_entry not importable: {exc}",
                file=sys.stderr,
            )
            return 1
    
        plugin_root = _resolve_plugin_root()
        mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    
        try:
            code = run_op_main("coordinator_core.ops.verify_templates_bin_sync", [plugin_root, mode])
        except ImportError as exc:
            print(
                f"verify-templates-bin-sync.sh: coordinator_core.ops.verify_templates_bin_sync not importable: {exc}",
                file=sys.stderr,
            )
            return 1
    
        return code
    finally:
        sys.argv = _prev_argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
