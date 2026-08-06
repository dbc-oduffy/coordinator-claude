#!/usr/bin/env python3
"""
install-substrate.py — CLI trampoline over claude-klabauter coordinator_core.install.substrate.

coordinator-setup Phase 3 mechanical work: lays down <settings-home>/machine-local/
substrate, installs bin/ resolvers (machine-local + claude-home families), and runs
Windows PATH/AppX health checks. Called by coordinator/commands/install.md Phase 3
via `"$PYTHON_BIN" "${PYTHON_ARGS[@]}" "$_cc_root/lib/install-substrate.py"` (guarded
trusted-root resolve + `lib/resolve-python.sh`; see
coordinator/snippets/cc-root-source-guard.md).

MUST be executed as a subprocess, never sourced (uses `sys.exit`, not `return`;
sourcing semantics don't apply to a Python entrypoint either way). Idempotent:
re-runs preserve operator-customized files, emit notices instead of overwriting.
Fail-loud on missing templates (hard precondition for downstream skills) and on
CLAUDE_KLABAUTER_ROOT / claude-klabauter-module resolution failure — this is an install/config-writer
script (fail-loud convention), not a never-block hook.

RETIRED (2026-07-28): this trampoline used to also drive `bin/gen-launcher-shim.py
--ensure-unix` over every `bin/*.py` entrypoint with a co-located `.cmd` launcher,
establishing bare-name Unix invocability (shebang + exec bit) on every install. PM
ruling 2026-07-28 (Windows is the P0 primary platform) reclassified that exact shape
as a POSIX-only-execution portability defect
(`coordinator_core.ops.check_posix_exec_assumptions`) — running it on every install
was actively manufacturing new guard violations, not fixing a gap. The pass is gone;
`gen-launcher-shim.py --ensure-unix` no longer exists either (see that module's own
§ RETIRED note). Existing shebang+exec-bit entrypoints remain frozen, shrink-only
debt in `state/posix-exec-baseline.json`.

Env:
    CLAUDE_PLUGIN_ROOT — required; the coordinator plugin install root. Derived from
                          this file's own on-disk location when unset (D2-15 parity —
                          this file lives at <root>/lib/install-substrate.py).
    CLAUDE_HOME        — optional; $HOME substitute (see lib/claude-home).
    COORDINATOR_NON_INTERACTIVE — optional; "1" suppresses the AppX stub deletion
                          consent prompt. Any other value is treated as unset.
    CHECK_ONLY         — optional; "1" reports would-do, writes nothing (also
                          accepted as --check-only).

CLI flags (passed through to the claude-klabauter module's argparse):
    --setup-only  — machine-local substrate seeding only; skip machine-environment
                    ops (percolation setup/, claude-CLI PATH, fnm binary, Windows
                    health).
    --check-only  — report would-do, write nothing.

Ported to: coordinator_core.install.substrate [claude-klabauter repo] (T4a-g3b chunk).
Spec backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md;
    coordinator/commands/install.md § Phase 3.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_BIN_LIB_DIR = os.path.join(os.path.dirname(_LIB_DIR), "bin", "lib")
if _BIN_LIB_DIR not in sys.path:
    sys.path.insert(0, _BIN_LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _derive_plugin_root() -> str:
    """D2-15 parity: derive CLAUDE_PLUGIN_ROOT from this file's own location
    when not set in env. This file lives at <root>/lib/install-substrate.py,
    so the root is the parent of lib/. Env var takes precedence when set
    (allows test overrides) — matches the retired bash original's
    BASH_SOURCE-relative derivation exactly.
    """
    existing = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if existing:
        return existing
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(here))


def _import_main():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.install.substrate import main as _op_main

    return _op_main


def main() -> None:
    # Replicates the bash original's own pre-flight (lines 24-46): derive
    # CLAUDE_PLUGIN_ROOT from this file's location when unset, then validate
    # the resolved root has the expected layout BEFORE touching claude-klabauter at all
    # — a silently bad root is worse than no root, and the claude-klabauter module's own
    # `run()` guard (which requires the env var pre-set, no BASH_SOURCE
    # analogue) is not a substitute for this file-location-relative derivation.
    plugin_root = _derive_plugin_root()
    if not os.path.isdir(os.path.join(plugin_root, "lib")) or not os.path.isdir(
        os.path.join(plugin_root, "templates")
    ):
        print(
            "install-substrate: CLAUDE_PLUGIN_ROOT does not have expected layout "
            "(lib/ and templates/ must exist)",
            file=sys.stderr,
        )
        print(f"  Resolved root: {plugin_root}", file=sys.stderr)
        print(
            "  Set CLAUDE_PLUGIN_ROOT explicitly to override the BASH_SOURCE derivation.",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_root

    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"install-substrate: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"install-substrate: coordinator_core.install.substrate not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    argv = sys.argv[1:]
    rc = op_main(argv)
    sys.exit(rc)


if __name__ == "__main__":
    main()
