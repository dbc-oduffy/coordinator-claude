# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
probe-onboarding-currency.py — CLI trampoline over claude-klabauter
coordinator_core.ops.probe_onboarding_currency.

P-13 drift probe: compares a repo's onboarded COORDINATOR_SCHEMA_VERSION stamp
against the coordinator source's current schema version. The classification
logic (schema-version read, stamp read/compare, source_is_live detection, the
F14 CLAUDE_HOME-not-a-.claude-dir guard) is fully ported to
coordinator_core/ops/probe_onboarding_currency.py — this file's only remaining
job is: resolve CLAUDE_KLABAUTER_ROOT, resolve the DoE-claude coordinator plugin root
(coordinator-schema-version's home) and hand it to the engine module via
COORDINATOR_CURRENCY_PLUGIN_ROOT, tell the engine module where THIS file lives
on disk via COORDINATOR_CURRENCY_SCRIPT_DIR (a DoE-side/contract-only fact the
engine cannot derive itself — used ONLY for source_is_live auto-detect now,
see _resolve_plugin_root() below for why it is no longer the plugin-root
default too), and forward argv/exit code.

Plugin-root resolution note (b644d5a9 migration): this executable moved from
DoE-claude into claude-klabauter while coordinator-schema-version stayed behind
in DoE-claude's coordinator/ tree. The engine module's OWN dirname(SCRIPT_DIR)
default (coordinator_core/ops/probe_onboarding_currency.py main(), used only
when a caller sets SCRIPT_DIR but not PLUGIN_ROOT) assumed the script and the
plugin payload were co-located — true in DoE-claude, false here: it now lands
on <claude-klabauter>/coordinator, which has no coordinator-schema-version at all. This
trampoline no longer relies on that fallback: it always resolves
COORDINATOR_CURRENCY_PLUGIN_ROOT explicitly via _resolve_plugin_root() below
(env override wins verbatim, else doe_root() + "/coordinator") before
importing/calling the engine module.

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, generator-
owned by `gen-launcher-shim.py --ensure-unix`, and correct for this shape. On
Windows, this file's co-located `.cmd` twin wins via `PATHEXT` when invoked as
a bareword, so the shebang is never read there; on macOS/Linux `python3` is the
right interpreter. Caution: callers must invoke via the extensionless name or a
resolved-interpreter prefix, never a bareword `.py` through git-bash — git-bash
DOES honor the shebang and would exec-127 with no `python3` present. See the
carve-out in DoE-claude's coordinator/docs/wiki/bash-on-windows-gotchas.md §
Carve-out (cross-repo — this wiki lives in the DoE-claude repo, not
here).

Exit codes (never-block probe, per the ported module's own docstring): 0 in the
overwhelming common case (probe ran, printed one of
current|drift(...)|unstamped(legacy)|inconclusive(...)|source_is_live to stdout);
1 ONLY on the F14 fatal guard (CLAUDE_HOME already ends in /.claude). On a
Claude-klabauter-link failure (CLAUDE_KLABAUTER_ROOT unresolvable / module not importable), this
trampoline mirrors the probe's own "never silently fail a caller" ethos: it
prints an inconclusive(...) status line to stdout (so callers parsing the
status string via a case statement degrade to their `inconclusive*` branch,
same as any other soft-infra failure) and exits 0 — it does NOT sys.exit(1),
since every caller of this probe (lib/detect-onboarding-offer.py) treats a
non-'current'/'source_is_live' status as advisory, never fatal.

Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1.
Doctrine: docs/wiki/doctor-probe-design.md § inconclusive Is a First-Class Probe Status.
Port source: coordinator/bin/probe-onboarding-currency.py (this file; prior bash
body retired on cutover — see git log).
"""

from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402


def _resolve_plugin_root() -> str | None:
    """Resolve the DoE-claude coordinator plugin root (coordinator-schema-version's home).

    COORDINATOR_CURRENCY_PLUGIN_ROOT wins verbatim when the caller already set
    it (e.g. coordinator_core/plugin_health/sentinel.py's in-process P-13
    caller always does — see that module's _currency_plugin_root()). Otherwise
    resolves via doe_root() (coordinator/bin/lib/coordinator_registry.py:
    DOE_ROOT env -> REPO_DOE_CLAUDE env -> machine-local repos.doe_claude) and
    returns <doe_root()>/coordinator.

    Does NOT derive from this trampoline's own __file__ location (see module
    docstring's "Plugin-root resolution note" for why self-location broke).

    Returns None (never raises, never sys.exit) when doe_root() is
    unresolvable — this probe's contract (module docstring) is never-block:
    an unresolvable root must degrade to inconclusive(...)/exit 0 like every
    other soft-infra failure here, not fail loud the way a CI gate script
    would. Every real caller (lib/detect-onboarding-offer.py) treats a
    non-'current'/'source_is_live' status as advisory, never fatal.
    """
    override = os.environ.get("COORDINATOR_CURRENCY_PLUGIN_ROOT", "")
    if override:
        return override
    try:
        return os.path.join(doe_root(), "coordinator")
    except _DoeUnresolvable:
        return None


def _import_main():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.probe_onboarding_currency import main as _op_main
    return _op_main


def main() -> None:
    # Contract fact only the trampoline can supply — its own directory, used
    # by the engine module ONLY to auto-detect source_is_live (plugin_root is
    # resolved explicitly below, not defaulted from this).
    os.environ.setdefault("COORDINATOR_CURRENCY_SCRIPT_DIR", _SCRIPT_DIR)

    plugin_root = _resolve_plugin_root()
    if plugin_root is None:
        print(
            "probe-onboarding-currency: cannot resolve the coordinator doctrine repo's "
            "plugin root (doe_root() unresolvable). Set repos.doe_claude in the "
            "machine-local registry, or set DOE_ROOT / REPO_DOE_CLAUDE, or set "
            "COORDINATOR_CURRENCY_PLUGIN_ROOT directly.",
            file=sys.stderr,
        )
        print("inconclusive(probe-infra: DoE coordinator plugin root unresolvable)")
        sys.exit(0)
    os.environ["COORDINATOR_CURRENCY_PLUGIN_ROOT"] = plugin_root

    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(
            f"probe-onboarding-currency: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        print(f"inconclusive(probe-infra: CLAUDE_KLABAUTER_ROOT resolution failed: {exc})")
        sys.exit(0)
    except ImportError as exc:
        print(
            f"probe-onboarding-currency: coordinator_core.ops.probe_onboarding_currency "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        print(
            f"inconclusive(probe-infra: coordinator_core.ops.probe_onboarding_currency "
            f"not importable: {exc})"
        )
        sys.exit(0)
    sys.exit(op_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
