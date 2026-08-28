# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""baton-drift-sweep.py — CLI trampoline for coordinator_core.ops.baton_drift_sweep.

Purpose: /workday-complete's non-blocking baton-drift coverage line. Splits open
batons (state/handoffs/*.md) into held (successor still live — expected, roughly one
per live chain), stranded (successor terminal/archived, baton itself ever claimed or
shipped — the chain broke after work started; a bug, must be zero and is drained
automatically by boot), never_started (same successor shape, but the baton was NEVER
claimed or shipped — nobody picked it up; DR-242 correctly refuses to auto-supersede
these, so this bucket is NOT "must be zero" and has no automated drain — retiring one
is a human/session `abandoned` call), and reconciled_no_successor (a qualifying
*-baton-reconciled-closed.md audit record names this baton but it has no successor
at all — also a bug, must be zero; see baton_drift_sweep's own module docstring
"SECOND LEG" section). See baton_drift_sweep's own module docstring for the full
classification (including the STRANDED/NEVER_STARTED split, § C5) and why
held/stranded/never_started/reconciled_no_successor, not a single count.

Direct-import, no IPC dispatch — same shape as day-coverage-sweep.py (which this
mirrors): imports and calls coordinator_core.ops.baton_drift_sweep.baton_drift_sweep
directly rather than routing through cc_invoke.route()/route_mutation().

Usage:
    python coordinator/bin/baton-drift-sweep.py

Exit codes:
  0 — swept successfully (regardless of the stranded count — this is a diagnostic,
      not a pass/fail gate; /workday-complete reports it, never fails on it).
  1 — argument error (this CLI takes no arguments).
  2 — repo-root unresolvable, or engine root / baton_drift_sweep not importable.

NEVER writes anything — read-only diagnostic.

Spec backlink: DoE-claude:pln-push-side-write-discipline-for-05c30d § D2d
"""
from __future__ import annotations

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_USAGE = "Usage: baton-drift-sweep.py (no arguments)"


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Bind `coordinator_core` on the DISPATCH axis, then the LOCATOR-axis
    binder that depends on it. Idempotent; safe to call more than once.

    ORDER INSIDE THIS FUNCTION IS LOAD-BEARING and is the whole reason it is one
    function rather than four deferred imports at their use sites.
    `require_dispatch_engine_on_path()` only mutates `sys.path` -- it imports
    nothing -- so `import coordinator_core` must follow it and must precede
    `repo_identity`, which resolves and imports `coordinator_core` at ITS own
    module level on the LOCATOR axis. On a conformant box the two axes can return
    different roots, and once a package is bound in `sys.modules` no later
    `sys.path` insert can rebind it: get this order wrong and `coordinator_core`
    silently binds off the working tree instead of the dispatch root.
    Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
    docs/research/engine-provenance-carrier-dependence.md

    What moved, and what did NOT: this sequence used to run at MODULE scope,
    which made every import of this file mutate the `sys.path` of a warm server
    ~50 sessions share. The order is preserved exactly; only the trigger moved.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    global require_dispatch_engine_on_path, resolve_checked_repo_root
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path as _require

    _require()
    import coordinator_core  # noqa: F401 — LOAD-BEARING: binds the package, see above

    from repo_identity import resolve_checked_repo_root as _resolve

    require_dispatch_engine_on_path = _require
    resolve_checked_repo_root = _resolve

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for a bootstrapped name BEFORE `main()`
    has run -- a test monkeypatching this module, or any consumer importing it
    rather than executing it -- triggers `_bootstrap_engine()` lazily instead of
    finding the name absent.

    This is the piece whose absence made the first repair pass hoist these
    imports back to module scope: deferring them alone leaves the module's own
    API missing until `main()` runs, and a `global`-bound name is module-visible
    only after its binder has been called. Only fires for names not already in
    `__dict__`, so once the bootstrap has run the plain global wins.
    """
    if name in ("require_dispatch_engine_on_path", "resolve_checked_repo_root"):
        _bootstrap_engine()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _import_baton_drift_sweep():
    _bootstrap_engine()
    require_dispatch_engine_on_path()
    from coordinator_core.ops.baton_drift_sweep import baton_drift_sweep as _sweep
    return _sweep


def main(argv: list[str]) -> int:
    _bootstrap_engine()

    args = argv[1:]
    if args:
        print("baton-drift-sweep.py: expected no arguments", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 1

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        print(f"baton-drift-sweep.py: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn and
        # proceed rather than refuse. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    try:
        sweep = _import_baton_drift_sweep()
    except RuntimeError as exc:
        print(f"baton-drift-sweep.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"baton-drift-sweep.py: coordinator_core.ops.baton_drift_sweep not importable: {exc}", file=sys.stderr)
        return 2

    from pathlib import Path

    result = sweep(Path(repo_root))

    print(f"total_live={result['total_live']}")
    print(f"terminal_not_archived={result['terminal_not_archived']}")
    print(f"non_terminal={result['non_terminal']}")
    print(f"held={result['held']}")
    print(f"stranded={result['stranded']}")
    for path in result["stranded_paths"]:
        print(f"  stranded {path}")
    print(f"never_started={result['never_started']}")
    for path in result["never_started_paths"]:
        print(f"  never_started {path}")
    print(f"reconciled_no_successor={result['reconciled_no_successor']}")
    for path in result["reconciled_no_successor_paths"]:
        print(f"  reconciled_no_successor {path}")
    print(f"tips={result['tips']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
