# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""verify-templates-bin-sync.py — byte-identity gate between live install helpers and their templates mirror.

Thin contract-plane trampoline over the engine plane's
coordinator_core.ops.verify_templates_bin_sync. Verifies (and, with --fix,
repairs) that every live ~/.claude/bin helper matches its mirror under
coordinator/templates/bin/ byte-for-byte, so the install templates never
silently drift from what's actually running.
"""
from __future__ import annotations
# verify-templates-bin-sync.sh — CLI trampoline over the engine plane's
# coordinator_core.ops.verify_templates_bin_sync.
#
# Finish-strangler port: the bash implementation (byte-identity check/fix
# between live ~/.claude/bin helpers and their coordinator/templates/bin/
# mirrors) has been fully ported to
# coordinator_core/ops/verify_templates_bin_sync.py (co-located test:
# coordinator_core/tests/test_verify_templates_bin_sync.py). This file is now
# a thin contract-plane trampoline over that engine-plane module, per DR-047
# (DoE owns contract/generator, the engine plane owns it). The filename KEEPS
# its `.sh` extension (unlike `coordinator-auto-push`/`handoff-gate-aging`,
# which dropped it) so `coordinator/bin/tests/test-claude-home-contract.sh`
# and any other caller that hardcodes the `.sh` suffix needs zero edits — the
# polyglot shebang mechanism does not require dropping the extension.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
# owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
# Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked
# as a bareword, so the shebang is never read there; on macOS/Linux `python3`
# is the right interpreter. Caution: callers must invoke via the extensionless
# name or a resolved-interpreter prefix, never a bareword `.py` through git-
# bash — git-bash DOES honor the shebang and would exec-127 with no `python3`
# present. See the carve-out in DoE-claude's coordinator/docs/wiki/bash-on-
# windows-gotchas.md § Carve-out (cross-repo — this wiki lives in the
# DoE-claude repo, not here).
#
# CLI contract:
#     verify-templates-bin-sync.sh          # verify mode (default)
#     verify-templates-bin-sync.sh --fix    # copy template -> live on mismatch
#                                            # (template is canonical; live is the
#                                            # repaired install — reversed from the
#                                            # retired bash oracle's live -> template
#                                            # direction, see the engine module's
#                                            # docstring for why)
#
# Exit codes: 0 clean/no-mismatch, 1 on any MISMATCH/LIVE_MISSING/TMPL_MISSING
# pair (fail-loud — this is a gate script, not a never-block hook, so a
# engine-link failure below also exits 1, not 0).
#
# Plugin-root resolution is reproduced HERE (not delegated to the engine
# module) because it is DoE-repo topology knowledge (CLAUDE_PLUGIN_ROOT env
# var, else the DoE repo root's coordinator/ subdir, resolved via the shared
# doe_root() registry helper) — NOT this script's own parent directory (see
# _resolve_plugin_root() docstring below for why self-location broke when
# this executable migrated to the engine repo), then passed to the module as
# its first positional argument (see verify_no_powershell_flash.py's
# bin_dir-as-argv[0] precedent for the same caller-resolves-topology split).
#
# Spec backlink: docs/plans/2026-05-20-eager-agent-calibration.md § Chunk 1
#                docs/plans/2026-07-16-bash-clean-slate-residual-migration.md

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
    return os.path.join(root, "coordinator")


def _import_runner():
    """In-process import, not an RPC invoke — this is a plain local file
    mutation, same rationale as edit-live-hook.py's own trampoline.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes (the --fix template->live copy) is an orphan at the
    `scoped_git_commit` sink.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    # argv threading: this CLI reads sys.argv at depth (argparse and helpers),
    # so the warm-call path swaps it for the duration rather than rewriting every read.
    # NOT re-entrant: a threaded server must serialise calls into this entrypoint.
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
