# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""day-coverage-sweep.py — CLI trampoline for completion_ops.day_coverage_sweep.

Purpose: the push-side READ half of completion-entry coverage. Every existing
completion-log writer (reconcile-completion-commits.py / the
completion.reconcile_commits op) is PULL-side: it starts from a completion
entry that already exists and walks outward for commits to fold in. Nothing
resolves the reverse direction — starting from a commit and asking which
entry (if any) already claims it. This trampoline exposes that reverse sweep
as a day-scoped, read-only diagnostic: for a given calendar day, how many of
that day's commits are claimed by an existing archive/completed/**/*.md
``commits:`` list, and for the unclaimed remainder, which are
FOREIGN-AUTHORED (a sibling repo's engine committed it here while delivering
a cross-repo memo — no claude-klabauter session behind it, so no entry is ever
expected), RECOVERABLE (a known entry's authored_by/chain matches the
commit's Session-Id trailer), IN-FLIGHT (an open handoff's
claimed_by/consumed_by matches instead), SIBLING-HOMED (the trailer's session
is homed in another fleet repo that committed into this tree, and completion
entries are single-repo, so no entry is owed here either), or GENUINELY
ORPHANED (none of those). ``claimed`` plus the five partitions reconcile
against ``total_commits``.

Direct-import, no IPC dispatch: unlike reconcile-completion-commits.py (which
routes through cc_invoke.route_mutation() to the registered
``completion.reconcile_commits`` op), this trampoline imports and calls
``coordinator_core.ops.completion_ops.day_coverage_sweep`` directly — the
same shape query-completions.py already uses for
``coordinator_core.ops.query_completions.main``. day_coverage_sweep is a
pure read-only function, not wired through @register_op / the JSON-RPC
op-classification quad (op_scopes.py / authz/classification.py /
ops/_registry_map.py / authz/registration_quad.py) — see that function's own
module-level comment in completion_ops.py for why.

Usage:
    python coordinator/bin/day-coverage-sweep.py <YYYY-MM-DD>

Exit codes:
  0 — swept successfully (regardless of how many commits are unclaimed —
      this is a diagnostic, not a pass/fail gate).
  1 — argument / validation error (missing or malformed day, wrong arg count).
  2 — repo-root unresolvable, or CLAUDE_KLABAUTER_ROOT / completion_ops not importable.

NEVER writes anything — read-only diagnostic. See day_coverage_sweep's own
docstring for the full negative-spec.

Spec backlink: DoE-claude:pln-push-side-write-discipline-for-05c30d § C2
"""
from __future__ import annotations

import os
import re
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_USAGE = "Usage: day-coverage-sweep.py <YYYY-MM-DD>"


def _import_day_coverage_sweep():
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.ops.completion_ops import day_coverage_sweep as _sweep
    return _sweep


def main(argv: list[str]) -> int:
    args = argv[1:]
    if len(args) != 1:
        print("day-coverage-sweep.py: expected exactly one <YYYY-MM-DD> argument", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 1

    day = args[0]
    if not _DAY_RE.match(day):
        print(f"day-coverage-sweep.py: day must be YYYY-MM-DD: {day!r}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 1

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is None:
        print(f"day-coverage-sweep.py: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn and
        # proceed rather than refuse. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    try:
        sweep = _import_day_coverage_sweep()
    except RuntimeError as exc:
        print(f"day-coverage-sweep.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"day-coverage-sweep.py: coordinator_core.ops.completion_ops not importable: {exc}", file=sys.stderr)
        return 2

    from pathlib import Path

    try:
        result = sweep(Path(repo_root), day)
    except ValueError as exc:
        print(f"day-coverage-sweep.py: {exc}", file=sys.stderr)
        return 1

    print(f"day={result['day']}")
    print(f"total_commits={result['total_commits']}")
    print(f"claimed={result['claimed_count']}")
    print(f"unclaimed={result['unclaimed_count']}")
    print(f"foreign={result['foreign_count']}")
    for sha in result["foreign"]:
        print(f"  foreign {sha}")
    print(f"recoverable={result['recoverable_count']}")
    for sha in result["recoverable"]:
        print(f"  recoverable {sha}")
    print(f"in_flight={result['in_flight_count']}")
    for sha in result["in_flight"]:
        print(f"  in_flight {sha}")
    print(f"sibling_homed={result['sibling_homed_count']}")
    for sha in result["sibling_homed"]:
        print(f"  sibling_homed {sha}")
    print(f"orphaned={result['orphaned_count']}")
    for sha in result["orphaned"]:
        print(f"  orphaned {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
