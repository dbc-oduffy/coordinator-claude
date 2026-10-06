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
                          read_content_root() when unset — NOT from this file's own location.
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
Spec backlink: coordinator-content-repo:pln-bash-to-naked-python-engine-mi-c09292;
    coordinator/commands/install.md § Phase 3.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import NoReturn

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_BIN_LIB_DIR = os.path.join(os.path.dirname(_LIB_DIR), "bin", "lib")
if _BIN_LIB_DIR not in sys.path:
    sys.path.insert(0, _BIN_LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from coordinator_data_root import content_root_or_private  # noqa: E402


_CLAUDE_KLABAUTER_URL = "https://github.com/dbc-oduffy/claude-klabauter"


def _engine_unavailable(cause: str, resolved_root: str | None) -> NoReturn:
    """Fail loud on a missing/unreachable engine: name the hard dependency, say
    access is manual, say how to ask — never a raw exception or traceback.

    A consumer of the published coordinator-claude bundle has no claude-klabauter
    access by default; the bare exception text states a symptom, not that
    claude-klabauter is a hard dependency. Anti-scope (PM-ruled): no fallback install
    path and no vendored coordinator_core — this changes the error only.
    """
    first_line = (cause.strip().splitlines() or ["unknown cause"])[0]
    print(
        f"install-substrate: claude-klabauter engine unavailable: {first_line}",
        file=sys.stderr,
    )
    print(
        "  claude-klabauter (resolved through its published claude-klabauter mirror) "
        "is a HARD dependency of coordinator-claude; the installer cannot run without it.",
        file=sys.stderr,
    )
    print(
        "  Access is granted manually, not self-service. Request it from the "
        f"repository owner (dbc-oduffy) at {_CLAUDE_KLABAUTER_URL}.",
        file=sys.stderr,
    )
    print(
        "  Once you have access, clone claude-klabauter and point the resolver at it: "
        "set COORDINATOR_ENGINE_ROOT, write <settings-home>/machine-local/"
        ".claude-klabauter-root, or run `machine-local set repos.claude_klabauter "
        "/path/to/claude-klabauter`, then re-run.",
        file=sys.stderr,
    )
    print(f"  Resolved root: {resolved_root or '(none)'}", file=sys.stderr)
    sys.exit(1)


def _engine_root_or_exit() -> str:
    try:
        return require_dispatch_engine_on_path()
    except RuntimeError as exc:
        _engine_unavailable(f"engine root resolution failed: {exc}", None)


def _import_from_engine(root: str, module: str, attr: str):
    try:
        return getattr(importlib.import_module(module), attr)
    except ImportError as exc:
        _engine_unavailable(f"{module} not importable: {exc}", root)


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
    infer it from its own path; read_content_root() is the authority for "where
    is the content clone." A future reader must not "restore" __file__-based
    derivation to regain oracle parity — that is exactly what broke it. Same
    reasoning, same fix as install-sandbox-check.py::_resolve_coordinator_root.
    """
    existing = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if existing:
        return existing
    engine_root = _engine_root_or_exit()
    read_content_root = _import_from_engine(
        engine_root, "coordinator_core.content_root", "read_content_root"
    )

    resolved = read_content_root()
    if not resolved:
        print(
            "install-substrate: cannot resolve the coordinator plugin root.",
            file=sys.stderr,
        )
        print(
            "  Set CLAUDE_PLUGIN_ROOT explicitly (the remedy that works for an OSS "
            "installer, which has no content root to resolve), or set "
            "repos.content_root in the machine-local registry.",
            file=sys.stderr,
        )
        sys.exit(1)
    return content_root_or_private(resolved)


def _import_main():
    claude_klabauter_root = _engine_root_or_exit()
    return _import_from_engine(claude_klabauter_root, "coordinator_core.install.substrate", "main")


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
            "  Set CLAUDE_PLUGIN_ROOT explicitly to override the read_content_root() resolution.",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_root

    op_main = _import_main()
    argv = sys.argv[1:]
    rc = op_main(argv)
    sys.exit(rc)


if __name__ == "__main__":
    main()
