# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""install-sandbox-check.py — CLI trampoline validating a sandbox clean-install shape.

Runs Tier 1 filesystem checks, the Tier 1b maximalist-install-shape regression
net, and Tier 1c publish-repo clean-install parameterization checks against a
fresh-machine ~/.claude + cloned-DoE + wired-wrapper install. Tier 2
(running-in-Claude-Code) cannot execute inside a subagent, so it is printed
as a DEFERRED manual gate. The validator logic lives claude-klabauter-side in
coordinator_core.install.sandbox_check; this file resolves COORDINATOR_ROOT
and hands it to that module.
"""
# install-sandbox-check — CLI trampoline over claude-klabauter
# coordinator_core.install.sandbox_check.
#
# Finish-strangler port (BIG_PORT Wave C): the bash implementation (sandbox
# clean-install shape validator — Tier 1 filesystem checks, Tier 1b
# maximalist-install-shape regression net, Tier 1c publish-repo clean-install
# parameterization contract) has been fully ported to
# coordinator_core/install/sandbox_check.py (claude-klabauter repo) with a co-located
# pytest (test_sandbox_check.py). This file is now a thin DoE-side (contract)
# trampoline over that claude-klabauter (engine) module, per DR-047 (DoE owns
# contract/generator, claude-klabauter owns engine).
#
# This validator drives several dependency scripts (claude-doe and
# DoE-claude's generator/resolver set) via subprocess, mirroring the
# original bash oracle's invocation shape. This trampoline's only job is
# to resolve the default
# COORDINATOR_ROOT and hand it to the claude-klabauter module, which cannot self-locate
# inside the DoE clone.
#
# COORDINATOR_ROOT resolution is NOT self-location (dirname(script_dir)).
# b644d5a9 migrated THIS FILE into claude-klabauter's coordinator/bin/ while
# coordinator/templates/ (which COORDINATOR_ROOT must point at — see
# sandbox_check.py's claude-doe-shim.sh.tmpl read) stayed behind in
# DoE-claude. The old bash oracle's `SCRIPT_DIR="$(cd "$(dirname
# "${BASH_SOURCE[0]}")" && pwd)"` self-location was correct only while this
# executable and coordinator/templates/ lived in the same repo; that
# assumption no longer holds post-migration. The default now resolves via
# `_resolve_coordinator_root()` -> the shared `doe_root()` registry helper
# (env var -> machine-local `repos.doe_claude` -> fail loud), never a
# hardcoded or __file__-derived path. An explicit --coordinator-root on argv
# still wins verbatim and skips this resolution entirely.
#
# Purpose (Tier 2 doc): Tier 2 (running-in-Claude-Code) cannot run inside a
# subagent/this process — it is printed as a DEFERRED manual gate at the end
# of every run, unchanged from the bash oracle.
# Spec backlink: DoE-claude:pln-doe-maximalist-execution-plugi-6d808d § W4.1
#   AC-W4.1: "Sandbox clean-install produces thin ~/.claude + cloned DoE + wired wrapper"
# Doctrine: docs/wiki/install-surface-completeness.md § Running-in-Claude-Code
#
# Exit codes (unchanged contract from the bash oracle, PLUS a new dedicated
# transport code — addendum rule 3b): 0 all assertions passed/skipped;
# 1 one or more assertions FAILed (business outcome); 3 TRANSPORT/
# ORCHESTRATION failure — the engine root unresolvable, the default
# COORDINATOR_ROOT unresolvable (doe_root() raised _DoeUnresolvable),
# coordinator_core not importable, or an unhandled exception inside the
# claude-klabauter module. The bash oracle had no dedicated transport code (an
# unhandled `set -euo pipefail` abort just propagated whatever exit status
# the failing builtin produced); this is a flagged behavioral improvement,
# not a silent one — a caller can now tell "checks ran, some failed" (1)
# apart from "checks could not run at all, e.g. cold machine with
# the engine root/DoE root unresolvable" (3).
from __future__ import annotations
import os
import sys

_TRANSPORT_FAILURE_RC = 3


def _resolve_coordinator_root() -> str:
    """Resolve the default --coordinator-root (the DoE-owned coordinator/
    tree holding templates/, e.g. templates/shell/claude-doe-shim.sh.tmpl).

    This does NOT derive from this script's own __file__ location. b644d5a9
    migrated this trampoline into claude-klabauter while coordinator/templates/
    stayed in DoE-claude — self-location (dirname(script_dir)) now resolves
    to <claude-klabauter>/coordinator, which has no templates/ tree at all, and the
    downstream sandbox_check module would silently read from a directory
    that never existed. doe_root() is the correct authority for "where is
    the DoE-claude repo," independent of where THIS script happens to run
    from. A future reader must not "restore" __file__-based resolution to
    regain oracle parity with the retired bash script — that is precisely
    what caused this break.

    Fails loud (sys.exit(_TRANSPORT_FAILURE_RC)) if doe_root() cannot
    resolve — this is a gate script, not a never-block hook, so an
    unresolvable DoE root must not degrade to a silent no-op default.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_registry import _DoeUnresolvable, doe_root

    try:
        root = doe_root()
    except _DoeUnresolvable as exc:
        print(
            f"install-sandbox-check: cannot resolve the coordinator doctrine repo root ({exc}). "
            "Set repos.doe_claude in the machine-local registry, or set the "
            "REPO_DOE_CLAUDE (or legacy DOE_ROOT) env var, or pass --coordinator-root "
            "explicitly.",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_RC)
    return os.path.join(root, "coordinator")


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.sandbox_check import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"install-sandbox-check: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        print(
            "  Remediation: this is a FAMILY-I (fresh-install) surface — on a cold machine "
            "COORDINATOR_ENGINE_ROOT may not yet be resolvable. Set COORDINATOR_ENGINE_ROOT explicitly, or seed the "
            "repos.claude_klabauter machine-local registry key, then re-run.",
            file=sys.stderr,
        )
        return _TRANSPORT_FAILURE_RC
    except ImportError as exc:
        print(f"install-sandbox-check: coordinator_core.install.sandbox_check not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAILURE_RC

    # Resolve the default COORDINATOR_ROOT via doe_root() (see
    # _resolve_coordinator_root() docstring) — the claude-klabauter module cannot do
    # this itself since it does not live inside the DoE clone. This is NOT
    # self-location: this file lives in claude-klabauter (coordinator/bin/),
    # not inside the DoE clone, so dirname(script_dir) no longer points at
    # the tree that owns templates/. An explicit --coordinator-root on argv
    # still wins verbatim and skips this resolution entirely.
    argv = list((sys.argv[1:] if argv is None else argv))
    # Review: code-reviewer (nit, Finding 8) — startswith("--coordinator-root")
    # also matched an unrelated future flag such as --coordinator-root-verbose
    # or --coordinator-rootfoo, wrongly treating it as an already-supplied
    # --coordinator-root and skipping default resolution. Tightened to an
    # exact match or the `=`-joined form.
    if not any(a == "--coordinator-root" or a.startswith("--coordinator-root=") for a in argv):
        coordinator_root = _resolve_coordinator_root()
        argv = ["--coordinator-root", coordinator_root] + argv

    return op_main(argv)


if __name__ == "__main__":
    sys.exit(main())
