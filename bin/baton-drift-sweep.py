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
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

require_dispatch_engine_on_path()
# LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
# what BINDS coordinator_core, and binding it HERE is the whole fix.
# require_dispatch_engine_on_path() above only mutates sys.path -- it imports
# nothing. Without this line the next module-level import below (a binder module
# that resolves on the LOCATOR axis) wins the race and binds coordinator_core off
# the working tree instead of the dispatch root, and no later sys.path insert can
# rebind an already-imported package. Removing it restores a silent wrong-tree
# divergence that require_dispatch_engine_on_path now raises on.
# Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
# docs/research/engine-provenance-carrier-dependence.md
import coordinator_core  # noqa: E402,F401

from repo_identity import resolve_checked_repo_root  # noqa: E402

_USAGE = "Usage: baton-drift-sweep.py (no arguments)"


def _import_baton_drift_sweep():
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.baton_drift_sweep import baton_drift_sweep as _sweep
    return _sweep


def main(argv: list[str]) -> int:
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
