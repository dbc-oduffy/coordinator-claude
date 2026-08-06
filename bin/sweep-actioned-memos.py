#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-actioned-memos.py — archive actioned cross-repo memos via fleet.archive_actioned_memos.

Purpose: dispatches the
two-call (dry-run preview, then act) fleet.archive_actioned_memos dance
through coordinator/bin/lib/cc_invoke.py's cc_invoke() — no shell, no bash
re-exec, no local mirror of the transport ladder. Sibling of
sweep-terminal-plans.py (same two-call shape, same fleet.* param contract).

Usage:
    python3 sweep-actioned-memos.py [<repo_root>]

    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.

Stdout contract: an INTEGER count of memos archived is printed to stdout —
len(.acted) from the fleet op's bare result object (Call 2). Consumed by
/workstream-complete Step 2.65's numeric guard.

Commit semantics: the fleet op self-commits (archive_and_commit) — this
trampoline MUST NOT stage/commit afterward.

Two-call shape (mirrors fleet.archive_completed_plans):
    Call 1: dry_run:true  — op selects repo-relative candidate ids (actioned,
            unclaimed memos in cross-repo/inbox/).
    Call 2: dry_run:false — op performs git-mv + self-commit for those ids.
    Empty candidates -> print 0, skip Call 2, exit 0.

Big-bang cutover (2026-07-21 retire-cs_sweep_actioned_memos campaign): no
legacy bash fallback. A seam-absent install is a genuine transport failure,
caught and logged (log-and-continue, best-effort ceremony op) — never
silently routes to the retired cs_sweep_actioned_memos bash body.

Exit codes:
    0 — always (best-effort; transport/op failures are logged to stderr,
        never propagated as a non-zero exit).

Spec backlink: state/handoffs/2026-06-22_232810_unified-terminal-artifact-archival-sweep.md
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Pinned pattern

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess spawning
lives entirely inside cc_invoke.cc_invoke() (sys.executable argv list, never
a shell string). Does NOT fall back to a legacy bash sweep on seam-absent
(big-bang cutover — see module docstring above).

Liveness stamp (C2, 2026-07-23 wsc-tail-slim-down): a genuinely successful run (including
the empty-candidates fast path) stamps the shared `archive_sweeps` housekeeping-liveness
key (`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`), mirroring
`sweep-boot.py`'s own `_stamp_archive_sweeps_liveness`. Multiple producers stamping the same
key is additive-safe (last-writer-wins liveness signal). A transport failure never stamps.
"""
from __future__ import annotations

import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from sweep_argv import parse_repo_root_argv  # noqa: E402

_USAGE = "usage: python3 sweep-actioned-memos.py [-h] [<repo_root>]"

#: Cap on per-item reasons echoed from a partial (exit_code=2) sweep. Bounded because
#: this runs at ceremony cadence against an inbox that can hold ~90 memos: an
#: unbounded dump would bury the summary line it is meant to explain.
_MAX_REPORTED_FAILURES = 10


def _import_housekeeping_seam():
    """Resolve CLAUDE_KLABAUTER_ROOT and import `housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`.

    Mirrors `sweep-boot.py::_import_housekeeping_seam` / `sweep-terminal-plans.py`'s copy —
    best-effort; returns None on any resolution/import failure.
    """
    try:
        claude_klabauter_root = cc_invoke._resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return stamp_liveness, ARCHIVE_SWEEPS


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the success path only (never on a transport failure).
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    stamp_liveness, archive_sweeps = seam
    try:
        stamp_liveness(repo_root, archive_sweeps)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass


def _resolve_repo_root(positional: list[str]) -> str | None:
    """Repo root — accept as positional arg (already vetted by
    `parse_repo_root_argv`, so `positional` never contains a leading-dash
    token here) or resolve from git.

    Returns None (never raises) on resolution failure, mirroring the bash
    oracle's "cannot resolve git repo root -> print 0, exit 0" posture.
    """
    if positional:
        return positional[0]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    resolved = (proc.stdout or "").strip()
    if proc.returncode != 0 or not resolved:
        return None
    return resolved


def _no_fallback() -> None:
    raise RuntimeError(
        "sweep-actioned-memos: native seam required (no bash fallback -- big-bang cutover)"
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    positional, _flags, early_exit = parse_repo_root_argv(
        argv, prog="sweep-actioned-memos.py", usage=_USAGE
    )
    if early_exit is not None:
        return early_exit
    repo_root = _resolve_repo_root(positional)
    if repo_root is None:
        print("sweep-actioned-memos: cannot resolve git repo root", file=sys.stderr)
        print(0)
        return 0

    # --- Call 1: dry-run to preview candidates ---
    dry_params = {"mode": "already-terminal", "dry_run": True, "candidate_ids": []}
    try:
        dry_result = cc_invoke.route("fleet.archive_actioned_memos", dry_params, repo_root, _no_fallback)
    # Review: the Staff Engineer — route() never raises RouteMutationError (only route_mutation
    # does); the broader arm was a dead catch, reduced to RuntimeError.
    except RuntimeError as exc:
        print(
            f"sweep-actioned-memos: fleet.archive_actioned_memos dry-run failed (transport error) -- skipping: {exc}",
            file=sys.stderr,
        )
        print(0)
        return 0

    candidates = dry_result.get("candidates", []) if isinstance(dry_result, dict) else []
    ids = [c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)]

    dry_exit = dry_result.get("exit_code", 0) if isinstance(dry_result, dict) else 0
    if dry_exit not in (0, None):
        print(
            f"sweep-actioned-memos: WARN: fleet.archive_actioned_memos dry-run exit_code={dry_exit} -- proceeding with candidates as-is",
            file=sys.stderr,
        )

    if not ids:
        _stamp_archive_sweeps_liveness(repo_root)
        print(0)
        return 0

    # Dirty-tree + claim-liveness guards are applied INTERNALLY by the op
    # (status + live-claim re-verify at both preview and act) — candidates
    # from the dry-run are already filtered; pass them through to Call 2
    # unfiltered.
    # Spec backlink: claude-klabauter coordinator_core/ops/fleet/archive_actioned_memos.py
    # module docstring / `_is_terminal`.

    # --- Call 2: act on candidates ---
    act_params = {"mode": "already-terminal", "dry_run": False, "candidate_ids": ids}
    try:
        act_result = cc_invoke.route("fleet.archive_actioned_memos", act_params, repo_root, _no_fallback)
    # Review: the Staff Engineer — route() never raises RouteMutationError (only route_mutation
    # does); the broader arm was a dead catch, reduced to RuntimeError.
    except RuntimeError as exc:
        print(
            f"sweep-actioned-memos: fleet.archive_actioned_memos act call failed (transport error) -- skipping: {exc}",
            file=sys.stderr,
        )
        print(0)
        return 0

    acted = act_result.get("acted", []) if isinstance(act_result, dict) else []
    count = len(acted) if isinstance(acted, list) else 0

    act_exit = act_result.get("exit_code", 0) if isinstance(act_result, dict) else 0
    if act_exit == 2:
        print(
            f"sweep-actioned-memos: WARN: fleet.archive_actioned_memos partial (exit_code=2, acted={count})",
            file=sys.stderr,
        )
        # The op's own per-item reasons are already in the envelope. Printing them
        # here is not a convenience: "check claude-klabauter logs" sent a 2026-07-30 caller
        # into reverse-engineering _is_terminal and archive_and_commit by hand to
        # learn that its two memos were untracked (git mv has no index entry to
        # re-key, so a hand-delivered memo is un-sweepable until committed) --
        # a fact this envelope already carried.
        failed = act_result.get("failed") if isinstance(act_result, dict) else None
        if isinstance(failed, list):
            for item in failed[:_MAX_REPORTED_FAILURES]:
                if not isinstance(item, dict):
                    continue
                print(
                    f"sweep-actioned-memos:   FAILED {item.get('id')}: {item.get('reason')}",
                    file=sys.stderr,
                )
            if len(failed) > _MAX_REPORTED_FAILURES:
                print(
                    f"sweep-actioned-memos:   ... and {len(failed) - _MAX_REPORTED_FAILURES} "
                    "more failure(s) -- see claude-klabauter logs for the full set",
                    file=sys.stderr,
                )
        if not failed:
            # exit_code=2 with an empty failed[] means every candidate was
            # deferred rather than errored; the skip reasons carry the WHY.
            skipped = act_result.get("skipped") if isinstance(act_result, dict) else None
            if isinstance(skipped, list):
                for item in skipped[:_MAX_REPORTED_FAILURES]:
                    if not isinstance(item, dict):
                        continue
                    print(
                        f"sweep-actioned-memos:   skipped {item.get('id')}: {item.get('reason')}",
                        file=sys.stderr,
                    )

    _stamp_archive_sweeps_liveness(repo_root)
    print(count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
