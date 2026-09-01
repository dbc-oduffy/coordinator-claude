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
engine-root / claude-klabauter-module resolution failure — this is an install/config-writer
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
    CLAUDE_PLUGIN_ROOT — required; the coordinator plugin install root (the DoE-owned
                          coordinator/ tree holding lib/ AND templates/). Resolved via
                          doe_root() when unset — NOT from this file's own location.
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
Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292;
    coordinator/commands/install.md § Phase 3.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_BIN_LIB_DIR = os.path.join(os.path.dirname(_LIB_DIR), "bin", "lib")
if _BIN_LIB_DIR not in sys.path:
    sys.path.insert(0, _BIN_LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402


def _derive_plugin_root() -> str:
    """Resolve CLAUDE_PLUGIN_ROOT — the DoE-owned coordinator/ tree that holds
    both lib/ and templates/. An explicit env var wins verbatim.

    This does NOT derive from this file's own __file__ location. The retired
    bash original was BASH_SOURCE-relative and that was correct while it lived
    inside the DoE clone; this trampoline was migrated into claude-klabauter,
    whose coordinator/ has lib/ but no templates/ at all. Self-location
    therefore resolved to <claude-klabauter>/coordinator and the layout precondition
    below rejected it on every run — `python <claude-klabauter>/coordinator/lib/
    install-substrate.py` could not execute from its own documented fence.
    A script whose required root is always a DIFFERENT repo's tree must not
    infer it from its own path; doe_root() is the authority for "where is the
    DoE-claude clone." A future reader must not "restore" __file__-based
    derivation to regain oracle parity — that is exactly what broke it. Same
    reasoning, same fix as install-sandbox-check.py::_resolve_coordinator_root.
    """
    existing = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if existing:
        return existing
    try:
        return os.path.join(doe_root(), "coordinator")
    except _DoeUnresolvable as exc:
        print(
            f"install-substrate: cannot resolve the coordinator plugin root ({exc}).",
            file=sys.stderr,
        )
        print(
            "  Set CLAUDE_PLUGIN_ROOT explicitly (the remedy that works for an OSS "
            "installer, which has no repos.doe_claude to resolve), or set "
            "repos.doe_claude in the machine-local registry, or set REPO_DOE_CLAUDE "
            "(or legacy DOE_ROOT).",
            file=sys.stderr,
        )
        sys.exit(1)


def _import_main():
    """Resolve the engine root, put it on sys.path, and import the ported entrypoint.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it -- this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.substrate import main as _op_main

    return _op_main


def main() -> None:
    # Resolve CLAUDE_PLUGIN_ROOT, then validate the resolved root has the
    # expected layout BEFORE touching claude-klabauter at all — a silently bad root is
    # worse than no root, and the claude-klabauter module's own `run()` guard (which
    # requires the env var pre-set) is not a substitute for this pre-flight.
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
            "  Set CLAUDE_PLUGIN_ROOT explicitly to override the doe_root() resolution.",
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
