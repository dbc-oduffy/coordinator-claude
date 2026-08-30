"""list-orphaned-plans.py — CLI trampoline over the control-plane engine's
`coordinator_core.ops.draft_plan_aging.list_orphaned` compute core.

Purpose: docs/plans/2026-07-31-plan-orphan-ownership-resolver.md, chunk C4.
Renders the tiered orphan census (P1 authorized_orphan, P3 parked count,
legacy_unjoinable count, unrecognized_status) for a human running it
directly from a shell — the SAME compute core the `plan.list_orphaned`
JSON-RPC op and the `d-plan-orphan-tiers` orient-assemble directive both
call. This file does NOT re-walk docs/plans/ itself and does NOT
re-implement any part of the tier partition — see
`coordinator_core.ops.draft_plan_aging`'s own "Sibling op: plan.list_orphaned"
docstring section for the full tier/bucket contract this renders.

Usage:
    list-orphaned-plans [--threshold-days N] [<repo_root>]

    --threshold-days N   P3 age gate in days (default: the same
                         AGING_THRESHOLD_DAYS the draft-STALE predicate uses).
    <repo_root>          Optional positional; defaults to the CWD's own
                         `git rev-parse --show-toplevel`. This cwd-relative
                         resolution is acceptable for this one-shot CLI only
                         — the registered op and the orient-assemble reader
                         both keep the explicit-repo_root discipline (AC14)
                         and never fall back to cwd.

Output: one line per P1 `authorized_orphan` entry, one summary line each for
the P3 parked count, the legacy_unjoinable count, the non_plan_excluded
count, and any unrecognized_status entries. Read-only, advisory-only — same
"never blocks" posture as `plan.list_stale_executing` (see that op's own
docstring): this CLI never fails a ceremony or a commit, so it always exits 0.

Spec backlink: pln-plan-orphan-ownership-resolver-3e68bb, chunk C4

Negative-spec:
    - Does NOT scan docs/plans/ itself — calls
      `coordinator_core.ops.draft_plan_aging.list_orphaned` in-process, the
      identical compute core the registered op and the orient-assemble
      reader both call. A duplicated scan here would reproduce the exact
      drift `_read_stale_plans` already carries against
      `plan.list_stale_executing` (see that reader's own module docstring).
    - Does NOT expand P3 per-plan — the parked tier is rendered as a COUNT
      only (AC6), matching the op's own docstring and the orient-assemble
      directive's `detail` shape.
    - Does NOT gate/exit-nonzero on findings — advisory-only; a caller that
      wants to branch on the population reads the compute core's own return
      dict (or the `plan.list_orphaned` JSON-RPC op), not this CLI's exit
      code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_BOOTSTRAP_DONE = False

_BOOTSTRAPPED_NAMES = (
    "list_orphaned",
    "AGING_THRESHOLD_DAYS",
    "truncate_external_text",
    "show_toplevel",
)


def _bootstrap_engine() -> None:
    """Put the repo root on sys.path so `coordinator_core` imports resolve,
    and bind the deferred names (`list_orphaned`, `AGING_THRESHOLD_DAYS`,
    `truncate_external_text`, `show_toplevel`) every sibling function reads
    as a global -- `test_list_orphaned_plans.py` monkeypatches
    `cli.list_orphaned` before calling `main()`.

    Moved out of module scope: this used to mutate sys.path on every import
    of this file, a process global ~50 warm-server sessions share. Only the
    trigger moved.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    global list_orphaned, AGING_THRESHOLD_DAYS, truncate_external_text, show_toplevel
    from coordinator_core.ops.draft_plan_aging import AGING_THRESHOLD_DAYS, list_orphaned
    from coordinator_core.orient_assemble.reader_result import truncate_external_text
    from coordinator_core.git.repo_root import show_toplevel

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for a deferred name (a test
    monkeypatching `cli.list_orphaned` before `main()` has run, or any
    consumer importing rather than executing this module) triggers
    `_bootstrap_engine()` lazily instead of finding the name absent.

    NEGATIVE SPEC -- the forced re-run is not belt-and-braces.
    `_bootstrap_engine()` short-circuits on `_BOOTSTRAP_DONE`, so a name
    that leaves `__dict__` AFTER the bootstrap has run is never rebound by
    a plain call. `mock.patch.object` does exactly that: it reads the name
    through this hook (so the value is not in `__dict__` at enter), sets
    its mock, and on exit `delattr`s rather than restoring -- then probes
    `hasattr`, which lands here with the flag already set. Without the
    reset that probe raises KeyError instead of returning the name.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_USAGE_FAIL = 2

#: Cap on `unrecognized_status` lines printed — mirrors
#: `readers_handoff_triage._UNRECOGNIZED_STATUS_LINE_CAP`; this diagnostic
#: bucket is not spec'd "loud, one line per plan" the way P1
#: `authorized_orphan` is, and grows with disk contents (Review:
#: code-reviewer — Finding 3).
_UNRECOGNIZED_STATUS_LINE_CAP = 10


def _resolve_repo_root(positional: str | None) -> str | None:
    """Repo root — accept as positional arg or resolve from the CWD's own
    git toplevel. cwd-relative resolution is acceptable for this one-shot
    CLI (see module docstring); the registered op and the orient-assemble
    reader both keep the explicit-repo_root discipline instead.
    """
    _bootstrap_engine()
    if positional:
        return positional
    return show_toplevel()


def _usage(prog: str) -> int:
    print(
        f"{prog}: usage: {prog} [--threshold-days N] [<repo_root>]",
        file=sys.stderr,
    )
    return _USAGE_FAIL


def main(argv: list[str] | None = None) -> int:
    _bootstrap_engine()
    argv = sys.argv[1:] if argv is None else argv
    prog = "list-orphaned-plans"

    threshold_days = AGING_THRESHOLD_DAYS
    positional: list[str] = []

    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--threshold-days" and i + 1 < len(argv):
            try:
                threshold_days = int(argv[i + 1])
            except ValueError:
                print(f"{prog}: --threshold-days must be an integer, got {argv[i + 1]!r}", file=sys.stderr)
                return _usage(prog)
            i += 2
        else:
            positional.append(tok)
            i += 1

    if len(positional) > 1:
        print(f"{prog}: unrecognized extra argument(s) {positional[1:]!r}", file=sys.stderr)
        return _usage(prog)

    repo_root = _resolve_repo_root(positional[0] if positional else None)
    if repo_root is None:
        print(f"{prog}: cannot resolve git repo root", file=sys.stderr)
        return _usage(prog)

    result = list_orphaned(Path(repo_root), threshold_days)

    lines: list[str] = []
    # P1 authorized_orphan is spec'd "loud, one line per plan, no age gate"
    # (list_orphaned's own docstring) — deliberately left uncapped/
    # untruncated-in-count here; P1 orphans are expected to stay rare, and
    # capping this tier would defeat its whole purpose (Review:
    # code-reviewer — Finding 3). Its external string field is still routed
    # through truncate_external_text() below (size bound only, not count).
    for entry in result["authorized_orphan"]:
        lines.append(
            f"P1 authorized_orphan: {entry['path']} "
            f"(execution_authorized_by={truncate_external_text(entry['execution_authorized_by'])})"
        )
    if result["parked_count"]:
        lines.append(
            f"P3 parked: {result['parked_count']} unowned plan(s), no authorization, "
            f"age >= {threshold_days}d"
        )
    if result["parked_below_threshold_count"]:
        lines.append(
            f"P3 parked (below threshold): {result['parked_below_threshold_count']} unowned "
            f"plan(s), no authorization, age < {threshold_days}d — counted, not alarmed"
        )
    if result["legacy_unjoinable_count"]:
        lines.append(
            f"legacy_unjoinable: {result['legacy_unjoinable_count']} plan(s) predate the "
            "carry-observability fix — unjoinable, excluded from P1/P3"
        )
    if result["non_plan_excluded_count"]:
        lines.append(
            f"non_plan_excluded: {result['non_plan_excluded_count']} file(s) in docs/plans/ "
            "carry no YAML frontmatter — not plans, excluded from the population"
        )
    unrecognized = result["unrecognized_status"]
    for entry in unrecognized[:_UNRECOGNIZED_STATUS_LINE_CAP]:
        lines.append(
            f"unrecognized_status: {entry['path']} "
            f"(status={truncate_external_text(str(entry['status']))!r})"
        )
    if len(unrecognized) > _UNRECOGNIZED_STATUS_LINE_CAP:
        lines.append(
            f"unrecognized_status: +{len(unrecognized) - _UNRECOGNIZED_STATUS_LINE_CAP} more"
        )

    if not lines:
        lines.append(
            f"no orphaned plans: {result['population_count']} non-terminal plan(s), "
            f"{result['owned_count']} owned"
        )

    for line in lines:
        print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
