# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-terminal-handoffs.py — on-demand CLI fire for the terminal-handoff sweep.

Purpose: the manual human-invoked surface over the sweep primitives now
shared with the ceremony tail (`coordinator_core.ops.fleet.
archive_terminal_handoffs.plan_sweep` + `coordinator_core.ops.fleet._common.
archive_and_commit`). Unlike its predecessor (`sweep-shipped-handoffs.py`,
deleted 2026-08-25 C1b when the op it fired, `fleet.archive_shipped_handoffs`,
was SUBSUMED into this op), this script does NOT re-implement any
scanning/frontmatter/terminality logic of its own — `plan_sweep` does its
own Branch A/B classification, DR-324-narrowed childlessness check, and
live-claim check internally (see that module's `_scan_terminal`). This
script calls `plan_sweep` then `archive_and_commit` directly, in-process —
it no longer reaches `fleet.archive_completed_handoffs` through the op
handler's dispatch route. It used to be the on-disk target `fire_archive_
sweeps_detached` spawned detached; that caller was deleted (2026-08-25 C4)
and this script's only remaining reason to exist is as the manual on-demand
drain a human runs directly.

Cap: this op takes a REQUIRED per-invocation move cap (absent/non-positive
is a setup error — no unbounded default, per the plan's C0 cap-axis
decision, state/audits/2026-08-25-the-handoff-archive-op-earns-its-way-
back.md § C0). This script passes the op module's own recommended value,
`_RECOMMENDED_CAP_CHOICE` (150 as of this writing) — see
coordinator_core/ops/fleet/archive_terminal_handoffs.py for the live value
and its own rationale; this script does not re-derive or duplicate that
rationale, only cites the constant by name so the two never silently drift
apart unnoticed (a future bump there is expected to be echoed here).

Usage:
    python3 sweep-terminal-handoffs.py

Exit codes:
    0 — normal (including zero-candidates, all-retained, and a fully
        successful sweep).
    1 — the sweep failed: either a caught exception from `plan_sweep`/
        `archive_and_commit` or a partial `archive_and_commit` result
        (some moves failed). Candidates are retained for the next sweep
        either way.
    2 — internal error (not inside a git repo).

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback — a genuinely seam-absent install surfaces as a transport
failure (RuntimeError), caught below and logged (best-effort ceremony).

Liveness stamp: mirrors the retired predecessor's own liveness contract --
every completion that reaches the sweep-processing tail (exit 0, including
zero-candidates/all-retained, AND exit 1, dispatch failure) stamps the
shared `archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`).
The internal-error path (exit 2 -- not a git repo) returns before reaching
the tail and never stamps.

Index-lock disposition (staff-eng F3, C4): this script's `archive_and_commit`
call is the ONLY tracked-worktree-mutating call this CLI makes -- it never
runs `git add`/`git commit` itself. `archive_and_commit`
(coordinator_core/ops/fleet/_common.py) already carries a bounded
exponential-backoff retry against transient `.git/index.lock` contention
(`_update_index_with_retry` / `_INDEX_RETRY_*`, sized against an empirical
repro) -- this script adds no second retry layer of its own, it reuses the
shared helper's. What CAN still happen on a ~50-concurrent-session box is
this call's commit racing an UNRELATED peer's own git operation on the same
worktree, which is exactly the transient contention
`_update_index_with_retry`'s backoff is sized to absorb.

Spec backlink: docs/plans/2026-08-25-the-terminal-handoff-sweep-stops-being-an-op.md § C6
Wraps: coordinator_core.ops.fleet.archive_terminal_handoffs.plan_sweep +
coordinator_core.ops.fleet._common.archive_and_commit (the shared sweep
primitives, called directly — not the `fleet.archive_completed_handoffs`
op's dispatch route).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402  # pyright: ignore[reportMissingImports] — added to sys.path at runtime by the _LIB_DIR injection above, not statically resolvable
from repo_identity import resolve_checked_repo_root  # noqa: E402  # pyright: ignore[reportMissingImports] — same runtime _LIB_DIR sys.path injection as cc_invoke above

# Mirrors coordinator_core/ops/fleet/archive_terminal_handoffs.py's own
# `_RECOMMENDED_CAP_CHOICE` -- see module docstring "Cap" section for why
# this is a cited literal, not an import.
_CAP = 150


def _ensure_claude_klabauter_on_path() -> str:
    """Idempotently put the engine root on sys.path; returns it.

    The file's ONE claude-klabauter-root path-resolution site, mirroring the retired
    predecessor's own `_ensure_claude_klabauter_on_path` helper.
    """
    return cc_invoke.require_engine_on_path(__file__)


def _import_housekeeping_seam():
    """Resolve the engine root and import `housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`.

    Best-effort; returns None on any resolution/import failure -- mirrors
    the retired predecessor's own seam import.
    """
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return stamp_liveness, ARCHIVE_SWEEPS


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the sweep-processing tail only (never on the internal-error exit).
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    stamp_liveness, archive_sweeps = seam
    try:
        stamp_liveness(repo_root, archive_sweeps)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass


def _print_refusal_census(scan_skipped, planned_skipped) -> None:
    """Print one line per refusal FAMILY, plus every id refused after the scan.

    A sweep that archives nothing and says only "no terminal handoffs
    archived" is indistinguishable from a sweep whose every rail silently
    dropped everything -- that ambiguity is what let a false-green AC-2
    stand. The scan's own refusals are grouped by reason prefix (the
    non-terminal population is the whole live corpus and would drown the
    output enumerated); post-scan refusals are few and named individually,
    since those are the records that WERE terminal and still did not move.
    """
    if isinstance(scan_skipped, list) and scan_skipped:
        families: "dict[str, int]" = {}
        for item in scan_skipped:
            reason = str(item.get("reason", "unknown"))
            families[reason.split(":", 1)[0]] = families.get(reason.split(":", 1)[0], 0) + 1
        print(f"scan refused {len(scan_skipped)} record(s):")
        for family, count in sorted(families.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>4}  {family}")

    if isinstance(planned_skipped, list) and planned_skipped:
        print(f"terminal but not moved -- {len(planned_skipped)} record(s):")
        for item in planned_skipped:
            print(f"  {item.get('id')} -- {item.get('reason')}")


def _no_fallback() -> None:
    raise RuntimeError(
        "fleet.archive_completed_handoffs: native seam required (no bash fallback -- big-bang cutover)"
    )


def main(_argv: "list[str] | None" = None) -> int:
    """`_argv` is unused: this script owns no argv-parsed options and delegates
    everything to `plan_sweep` + `archive_and_commit`, called directly
    in-process. Kept for call signature conformance with the sibling
    sweep-script test harnesses, which call `mod.main(argv if argv is not
    None else [])` uniformly."""
    git_repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if git_repo_root is None:
        print("sweep-terminal-handoffs.py: not inside a git repo", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)

    repo_root = git_repo_root
    dispatch_failed = False
    archived = 0

    # ONE process, ONE pass, straight against the shared sweep primitives --
    # no op-handler dispatch route, no cc_invoke.route() round trip. This
    # script used to reach the op through two cc_invoke.route() round trips
    # (T1 preview, then T3 act), each spawning a fresh cold interpreter for
    # `-m coordinator_core.invoke`. Measured through that shape the sweep
    # cost 1046.875ms process time across 30 processes (state/audits/
    # 2026-08-25-the-handoff-archive-op-earns-its-way-back.md section C5b)
    # against DR-344's 500ms brightline -- and the cost was the round trips,
    # not the work.
    _ensure_claude_klabauter_on_path()
    import asyncio
    from coordinator_core.ops.fleet.archive_terminal_handoffs import plan_sweep
    from coordinator_core.ops.fleet._common import archive_and_commit, main_worktree_root
    from coordinator_core.git.repo_root import git_common_dir

    try:
        common_dir = Path(git_common_dir(cwd=str(repo_root)))
    except Exception as exc:
        print(f"sweep-terminal-handoffs.py: git_common_dir failed: {exc}", file=sys.stderr)
        return 1

    worktree_root = main_worktree_root(common_dir)

    async def _sweep() -> dict:
        scan_skipped: "list[dict]" = []
        moves, skipped = await plan_sweep(
            worktree_root, common_dir, _CAP, scan_skipped=scan_skipped,
        )
        if not moves:
            return {"acted": [], "failed": [], "skipped": skipped, "scan_skipped": scan_skipped}
        n = len(moves)
        subject = (
            f"fleet: archive {n} terminal handoff(s)\n\n"
            f"Archived via sweep-terminal-handoffs.py (on-demand CLI)."
        )
        acted, failed = await archive_and_commit(
            worktree_root=worktree_root,
            moves=moves,
            subject=subject,
        )
        return {"acted": acted, "failed": failed, "skipped": skipped, "scan_skipped": scan_skipped}

    try:
        result = asyncio.run(_sweep())
    except Exception as exc:
        print(f"sweep-terminal-handoffs.py: sweep failed: {exc}", file=sys.stderr)
        dispatch_failed = True
        result = {}

    if isinstance(result, dict):
        acted = result.get("acted", [])
        archived = len(acted) if isinstance(acted, list) else 0
        failed = result.get("failed", [])
        if isinstance(failed, list) and failed:
            print(
                f"sweep-terminal-handoffs.py: WARN: {len(failed)} move(s) failed "
                f"(acted={archived}) -- check claude-klabauter logs",
                file=sys.stderr,
            )
            dispatch_failed = True

    if archived == 0:
        print("no terminal handoffs archived")
    else:
        print(f"{archived} terminal handoffs archived")

    if isinstance(result, dict):
        _print_refusal_census(result.get("scan_skipped"), result.get("skipped"))

    _stamp_archive_sweeps_liveness(repo_root)
    if dispatch_failed:
        return 1
    return 0


if __name__ == "__main__":
    _ensure_claude_klabauter_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        _exit_code = main()
    sys.exit(_exit_code)
