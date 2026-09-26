# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
#   verify-dist-publish-repo-sync.py          Check all pairs; exit non-zero on any MISMATCH or MISSING.
#   MISMATCH  <rel-path>   — content differs
#   1 — one or more MISMATCH or MISSING files detected, OR publish-repo-root
#       OR CLAUDE_PLUGIN_ROOT could not be resolved

import os
import sys

def _plugin_root() -> str:
    """Resolve the plugin root (coordinator/) that owns dist/publish-repo-{toplevel,docs}/.

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via doe_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <doe_root()>/coordinator.

    This does NOT derive from this script's own __file__ location. That
    used to be correct when this executable lived in DoE-claude
    (coordinator/bin/.. IS the plugin root there), but this file has since
    migrated to claude-klabauter (b644d5a9 there, 8a28a6ca here) while
    coordinator/dist/publish-repo-{toplevel,docs}/ stayed put in
    DoE-claude — self-location now resolves to <claude-klabauter>/coordinator, which
    has no dist/ at all, silently producing spurious MISSING/ERROR lines
    over a tree that never existed instead of a loud failure. doe_root()
    is the correct authority for "where is the DoE-claude repo,"
    independent of where THIS script happens to run from. A future reader
    must not "restore" __file__-based resolution to regain the old bash
    oracle's SCRIPT_DIR/.. shape — that is precisely what caused this
    break. The claude-klabauter op cannot derive this itself — it does not live in
    the DoE tree — so the trampoline resolves and forwards it via the
    environment.

    Fails loud (sys.exit(3)) if doe_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to an exit-0 no-op. Exit code 3 (not 1 or 2) keeps this failure
    distinct from the op's own 0/1/2 business codes, matching this
    trampoline's existing engine-root-resolution-failure convention below.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import content_root_or_private
    from coordinator_registry import _DoeUnresolvable, doe_root

    env_val = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_val:
        return env_val
    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-dist-publish-repo-sync.py: cannot resolve the DoE-claude repo root "
            f"({exc}). Set repos.doe_claude in the machine-local registry, or set "
            "the DOE_ROOT env var, or set CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(3)
    return content_root_or_private(root)


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", _plugin_root())
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"verify-dist-publish-repo-sync.py: engine-root resolution failed: {exc}",
            file=sys.stderr,
        )
        return 3
    except ImportError as exc:
        print(
            f"verify-dist-publish-repo-sync.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    try:
        code = run_op_main("coordinator_core.ops.verify_dist_publish_repo_sync", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            "verify-dist-publish-repo-sync.py: "
            f"coordinator_core.ops.verify_dist_publish_repo_sync not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())
