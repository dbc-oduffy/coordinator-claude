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
# verify-subagent-sandbox-preamble-sync.py — CLI trampoline over claude-klabauter
# coordinator_core.ops.verify_subagent_sandbox_preamble_sync.
#
# Finish-strangler port: check/fix/list the `subagent-sandbox-preamble` sentinel
# block across the scoped-agent CONSUMERS array (scouts/specialists/workers/
# checkers/auditors only — NOT Opus personas, NOT executor/review-integrator/
# enricher/docs-checker) has been fully ported to
# coordinator_core/ops/verify_subagent_sandbox_preamble_sync.py (co-located
# test: coordinator_core/tests/test_verify_subagent_sandbox_preamble_sync.py).
# This file is now a thin DoE-side (contract) trampoline over that claude-klabauter
# (engine) module, per DR-047 (DoE owns contract/generator, claude-klabauter owns
# engine).
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
# CLI contract preserved verbatim from the bash original:
#     verify-subagent-sandbox-preamble-sync.py          verify (default) — non-zero on drift.
#     verify-subagent-sandbox-preamble-sync.py --check  alias for default mode (explicit).
#     verify-subagent-sandbox-preamble-sync.py --fix    insert/rewrite sentinel blocks to canon.
#     verify-subagent-sandbox-preamble-sync.py --list   print one consumer path per line, exit 0.
#
# Sentinel pair (exact strings):
#   <!-- BEGIN subagent-sandbox-preamble (synced from snippets/subagent-sandbox-preamble.md) -->
#   <!-- END subagent-sandbox-preamble -->
#
# Exit codes (fail-loud drift-gate script — this is a gate script, not a
# never-block hook, so a claude-klabauter-link/transport failure below is NOT mapped to
# exit 0 or reused onto a business code; it gets its OWN dedicated code, 3,
# per the porter-brief's exit-code-contract hard rule):
#   0 — clean (no drift) / --list mode.
#   1 — drift found (MISSING/MISMATCH/MISSING_END/MISSING_FILE — see the
#       claude-klabauter module's own exit-code table for the full per-row mapping), OR
#       _resolve_plugin_root() could not resolve the DoE-claude repo root
#       (CLAUDE_PLUGIN_ROOT unset and doe_root() raised _DoeUnresolvable) —
#       mirrors verify-templates-bin-sync.py's own reuse of the drift exit
#       code for an unresolvable plugin root.
#   2 — CLI-usage / environment error (unknown mode, `node` not on PATH, or
#       the canonical snippet file is missing) — raised by the claude-klabauter module.
#   3 — claude-klabauter-link failure: engine-root resolution failed, or
#       coordinator_core.ops.verify_subagent_sandbox_preamble_sync was not
#       importable. Distinct from every code above so a caller can never
#       mistake "claude-klabauter engine unreachable" for "sentinel drift found" (1)
#       or "bad CLI usage" (2).
#
# Plugin-root/script-dir resolution is reproduced HERE (not delegated to the
# claude-klabauter module) because it is DoE-repo topology knowledge (CLAUDE_PLUGIN_ROOT
# env var, else resolved via the shared doe_root() registry helper) — this
# executable migrated to claude-klabauter (b644d5a9/8a28a6ca) while
# coordinator/agents/ (the DoE-owned consumer files this module reads) stayed
# in DoE-claude, so this script's own parent directory no longer resolves to
# a directory containing agents/ at all. doe_root() is the correct authority
# for "where is the DoE-claude repo," independent of where THIS script
# happens to run from — mirrors verify-templates-bin-sync.py's
# _resolve_plugin_root() fix exactly (see that script's own docstring for
# the same self-location break and why it must not be restored). Both
# plugin_root and script_dir are passed to the module as its first two
# positional arguments (see verify_templates_bin_sync.py's
# plugin_root-as-argv[0] precedent, extended here with a second positional
# for script_dir since this module also needs it to locate
# lib/sentinel-blocks-cli.js).
#
# Spec backlink: DoE-claude:pln-bash-polyglot-clean-slate-full-5c71ee

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
    return os.path.join(root, "coordinator")


def _resolve_script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _import_runner():
    """In-process import, not an RPC invoke — this is a plain local file
    mutation, same rationale as edit-live-hook.py's own trampoline.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares
    become a session scope-touch claim. Without that, everything this CLI
    writes (the --fix sentinel-block insert/rewrite) is an orphan at the
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
