# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
verify-templates-setup-sync.py — CLI trampoline over claude-klabauter
coordinator_core.ops.verify_templates_setup_sync.

Drift oracle over the setup/ tracked set: template<->live byte parity,
template<->repo-root byte parity, and (for publish_sync.py) the claude-klabauter
dispatch contract. Inspect-only: reports drift per tracked relpath, exits
non-zero on any leg's failure. There is no
--fix flag — recovery is manual and template-as-authoritative (`cp
coordinator/templates/setup/<file> ~/.claude/setup/<file>`); a prior
live->template --fix path was removed because it directly contradicted
the outward-only publish doctrine (state/lessons/2026-07-06-verify-
templates-setup-sync-sh-fix-is-ba.yaml).

Spec backlink: docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md § Step 3 [DEAD-CITATION: plan file never committed to this repo]
Port target: claude-klabauter coordinator_core/ops/verify_templates_setup_sync.py
"""

from __future__ import annotations

INSTALL_CLASS = False

import os
import sys


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main
    return run_op_main


def _resolve_plugin_root() -> str:
    """Resolve the plugin root (coordinator/templates/setup/'s parent).

    Env var CLAUDE_PLUGIN_ROOT wins if set, returned verbatim. Otherwise
    resolves via content_root() (see that function's own docstring for its
    env-var/machine-local resolution chain) and returns
    <content_root()>/coordinator.

    This does NOT derive from this script's own __file__ location: this
    executable lives in claude-klabauter while coordinator/templates/
    stayed in coordinator-content-repo per DR-047, so self-location no longer resolves
    to a directory containing templates/ (see
    verify-templates-bin-sync.py's _resolve_plugin_root() for the same fix
    on the sibling script — this function mirrors its shape).

    Fails loud (sys.exit(1)) if content_root() cannot resolve: this is a gate
    script, not a never-block hook, so an unresolvable DoE root must not
    degrade to an exit-0 no-op.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_data_root import content_root_or_private
    from coordinator_registry import _DoeUnresolvable, content_root

    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        root = content_root()
    except _DoeUnresolvable as exc:
        print(
            "verify-templates-setup-sync.py: cannot resolve the coordinator doctrine "
            f"repo root ({exc}). Set repos.content_root in the machine-local "
            "registry, or set the CONTENT_ROOT env var, or set "
            "CLAUDE_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        sys.exit(1)
    return content_root_or_private(root)


def main(argv: "list[str] | None" = None) -> int:
    # Set CLAUDE_PLUGIN_ROOT (if unset) so the ported op — which cannot
    # locate the DoE coordinator/ tree via its own __file__ or a cwd()
    # fallback (see coordinator_core.ops.verify_templates_setup_sync's
    # _resolve_plugin_root()) — resolves the same templates/setup/
    # directory this trampoline resolves. The op module reads the env var
    # rather than taking an explicit argument, so mutating os.environ here
    # is the seam, not a workaround; other callers (e.g.
    # coordinator_core.plugin_health.sentinel's in-process probe P-11) set
    # the same env var directly before invoking the op's main().
    if not os.environ.get("CLAUDE_PLUGIN_ROOT"):
        os.environ["CLAUDE_PLUGIN_ROOT"] = _resolve_plugin_root()

    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(f"verify-templates-setup-sync.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"verify-templates-setup-sync.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        return 1
    try:
        code = run_op_main("coordinator_core.ops.verify_templates_setup_sync", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(f"verify-templates-setup-sync.py: coordinator_core.ops.verify_templates_setup_sync not importable: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
