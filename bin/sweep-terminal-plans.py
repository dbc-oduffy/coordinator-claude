# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-terminal-plans.py — archive terminal plans via fleet.archive_completed_plans.

Purpose: dispatches the two-call (dry-run preview,
then act) fleet.archive_completed_plans dance through
coordinator/bin/lib/cc_invoke.py's cc_invoke() — no shell, no bash re-exec,
no local mirror of the transport ladder.

Usage:
    python3 sweep-terminal-plans.py [<repo_root>]

    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.

Stdout contract: an INTEGER count of plans archived is printed to stdout —
len(.acted) from the fleet op's bare result object (Call 2). Consumed by
session-init's numeric guard.

Commit semantics: the fleet op self-commits (archive_and_commit) — this
trampoline MUST NOT stage/commit afterwards.

Two-call shape (KD-2 plans self-preview):
    Call 1: dry_run:true  — op selects repo-relative candidate IDs.
    Call 2: dry_run:false — op performs git-mv + self-commit for those IDs.
    Empty candidates -> print 0, skip Call 2, exit 0.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback. A seam-absent install is a genuine transport failure, caught
and logged (log-and-continue, best-effort ceremony op) — never silently
routes to the retired cs_sweep_terminal_plans bash body.

Exit codes:
    0 — always (best-effort; transport/op failures are logged to stderr,
        never propagated as a non-zero exit).

Spec backlink: DoE-claude:pln-wire-claude-klabauter-fleet-archive-prun-8fd552 § C3 / KD-2 / KD-3
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave F1 (facade collapse)

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess spawning
lives entirely inside cc_invoke.cc_invoke() (sys.executable argv list, never
a shell string). Does NOT fall back to a legacy bash sweep on seam-absent
(big-bang cutover — see module docstring above).

Liveness stamp (C2, 2026-07-23 wsc-tail-slim-down): a genuinely successful run (including
the empty-candidates fast path — "ran, nothing to do" is still a live run) stamps the shared
`archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`), mirroring
`sweep-boot.py`'s own `_stamp_archive_sweeps_liveness`. Multiple producers stamping the same
key is additive-safe (last-writer-wins liveness signal, not a counter) — this CLI is now one
of several detached-fire producers of that same stamp (plan § C2), not a competing one. A
transport failure never stamps — a dead sweep must not read as live.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from sweep_argv import parse_repo_root_argv  # noqa: E402

_USAGE = "usage: python3 sweep-terminal-plans.py [-h] [<repo_root>]"


def _import_housekeeping_seam():
    """Resolve CLAUDE_KLABAUTER_ROOT (self-location-first) and import
    `housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`.

    Mirrors `sweep-boot.py::_import_housekeeping_seam` verbatim (same resolve-then-import
    shape) — this trampoline's own `__file__` lives inside the claude-klabauter checkout, so
    self-location resolves it directly; `repo_root` here is a separate value (the
    CALLER's repo, which may be a consumer repo) and plays no part in this resolution.
    Returns None on any resolution/import failure — best-effort forensics, never a
    reason to fail the sweep itself louder.
    """
    try:
        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return None
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return stamp_liveness, ARCHIVE_SWEEPS


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the success path only (never on a transport failure) — see module
    docstring "Liveness stamp" section.
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
            **cc_invoke._no_console_kw(cc_invoke.resolve_engine_root(__file__)),  # popup-safe-env-suppressed
        )
    except (OSError, RuntimeError):
        return None
    resolved = (proc.stdout or "").strip()
    if proc.returncode != 0 or not resolved:
        return None
    return resolved


def _no_fallback() -> None:
    raise RuntimeError(
        "sweep-terminal-plans: native seam required (no bash fallback -- big-bang cutover)"
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    positional, _flags, early_exit = parse_repo_root_argv(
        argv, prog="sweep-terminal-plans.py", usage=_USAGE
    )
    if early_exit is not None:
        return early_exit
    repo_root = _resolve_repo_root(positional)
    if repo_root is None:
        print("sweep-terminal-plans: cannot resolve git repo root", file=sys.stderr)
        print(0)
        return 0

    # --- Call 1: dry-run to preview candidates ---
    dry_params = {"mode": "already-terminal", "dry_run": True, "candidate_ids": []}
    try:
        dry_result = cc_invoke.route("fleet.archive_completed_plans", dry_params, repo_root, _no_fallback)
    # Review: the Staff Engineer — route() never raises RouteMutationError (only route_mutation
    # does); the broader arm was a dead catch, reduced to RuntimeError.
    except RuntimeError as exc:
        print(
            f"sweep-terminal-plans: fleet.archive_completed_plans dry-run failed (transport error) -- skipping: {exc}",
            file=sys.stderr,
        )
        print(0)
        return 0

    candidates = dry_result.get("candidates", []) if isinstance(dry_result, dict) else []
    ids = [c["id"] for c in candidates if isinstance(c, dict) and isinstance(c.get("id"), str)]

    dry_exit = dry_result.get("exit_code", 0) if isinstance(dry_result, dict) else 0
    if dry_exit not in (0, None):
        print(
            f"sweep-terminal-plans: WARN: fleet.archive_completed_plans dry-run exit_code={dry_exit} -- proceeding with candidates as-is",
            file=sys.stderr,
        )

    if not ids:
        _stamp_archive_sweeps_liveness(repo_root)
        print(0)
        return 0

    # Dirty-tree + claim-liveness guards are applied INTERNALLY by the op
    # (claude-klabauter c418a2c8, T1 preview AND T3 act) — candidates from the dry-run
    # are already filtered; pass them through to Call 2 unfiltered.
    # Spec backlink: claude-klabauter coordinator_core/ops/fleet/archive_plans.py
    # module docstring "Dirty-tree skip guard" / "Claim-liveness skip guard".

    # --- Call 2: act on candidates ---
    act_params = {"mode": "already-terminal", "dry_run": False, "candidate_ids": ids}
    try:
        act_result = cc_invoke.route("fleet.archive_completed_plans", act_params, repo_root, _no_fallback)
    # Review: the Staff Engineer — route() never raises RouteMutationError (only route_mutation
    # does); the broader arm was a dead catch, reduced to RuntimeError.
    except RuntimeError as exc:
        print(
            f"sweep-terminal-plans: fleet.archive_completed_plans act call failed (transport error) -- skipping: {exc}",
            file=sys.stderr,
        )
        print(0)
        return 0

    acted = act_result.get("acted", []) if isinstance(act_result, dict) else []
    count = len(acted) if isinstance(acted, list) else 0

    act_exit = act_result.get("exit_code", 0) if isinstance(act_result, dict) else 0
    if act_exit == 2:
        print(
            f"sweep-terminal-plans: WARN: fleet.archive_completed_plans partial (exit_code=2, acted={count}) -- check claude-klabauter logs",
            file=sys.stderr,
        )

    _stamp_archive_sweeps_liveness(repo_root)
    print(count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
