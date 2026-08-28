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
    python3 sweep-terminal-handoffs.py [--dry-run]

`--dry-run` is the operator's CENSUS surface: it runs the same `plan_sweep`
classification the acting path runs and prints the records that WOULD move,
then returns without calling `archive_and_commit`. It exists because the only
other census route is the op's `dry_run:true` preview, whose setup-error
envelope (`fleet/_common.py :: _setup_error`) carries `candidates: []` under
`exit_code:1` — so a caller that branches on the candidate list instead of
the exit code reads a refused invocation as "nothing to sweep". That
mis-read is what 2026-08-27's zero-vs-25 disagreement actually was
(state/improvement-queue/2026-08-27-fleet-archive-completed-handoffs-has-no-
00d6c9ec1a7d.yaml). A dry run mutates nothing, spawns no commit, and does
NOT stamp the `archive_sweeps` housekeeping-liveness key — a census is not
a sweep, and stamping one would let a run of censuses hold the cadence gate
open while nothing was ever archived.

Exit codes:
    0 — normal (including zero-candidates, all-retained, a completed
        `--dry-run` census, and a fully successful sweep).
    1 — the sweep failed: either a caught exception from `plan_sweep`/
        `archive_and_commit` or a partial `archive_and_commit` result
        (some moves failed). Candidates are retained for the next sweep
        either way. A `--dry-run` census that raises out of `plan_sweep`
        returns 1 the same way.
    2 — internal error (not inside a git repo), or a malformed argv.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback — a genuinely seam-absent install surfaces as a transport
failure (RuntimeError), caught below and logged (best-effort ceremony).

Liveness stamp: mirrors the retired predecessor's own liveness contract --
every ACT-path completion that reaches the sweep-processing tail (exit 0,
including zero-candidates/all-retained, AND exit 1, dispatch failure) stamps
the shared `archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`).
The internal-error path (exit 2 -- not a git repo) returns before reaching
the tail and never stamps. A `--dry-run` census also never stamps -- it
returns from its own early branch before the ACT-only tail below, for the
reason given in the Usage section above (a census is not a sweep).
[Review: coordinator:code-reviewer, 07cbe322f slice, P3 -- this section
predated --dry-run and read as if only the exit-2 path skipped the stamp;
--dry-run skips it too, for a different reason, now stated here.]

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

_USAGE = "usage: python sweep-terminal-handoffs.py [-h] [--dry-run]"
_DRY_RUN_FLAG = "--dry-run"

# Mirrors coordinator_core/ops/fleet/archive_terminal_handoffs.py's own
# `_RECOMMENDED_CAP_CHOICE` -- see module docstring "Cap" section for why
# this is a cited literal, not an import.
_CAP = 150


def _ensure_claude_klabauter_on_path() -> str:
    """Idempotently put the engine root on sys.path; returns it.

    The file's ONE claude-klabauter-root path-resolution site, mirroring the retired
    predecessor's own `_ensure_claude_klabauter_on_path` helper.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke  # pyright: ignore[reportMissingImports] — added to sys.path at runtime by the _LIB_DIR injection above, not statically resolvable

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


def _print_planned_moves(moves) -> None:
    """Print the records a `--dry-run` census would move, oldest-first.

    Deliberately prints the id AND the destination: "what would move" is only
    half the operator's question, and a destination already occupied by a
    different file is refused later by `plan_sweep` under
    `archive-dest-conflict` rather than moved.
    """
    if not moves:
        print("dry run: no terminal handoffs would be archived")
        return
    print(f"dry run: {len(moves)} terminal handoff(s) would be archived:")
    for move in moves:
        print(f"  {move.candidate_id}  ->  {move.dst}")


def main(argv: "list[str] | None" = None) -> int:
    """`argv` carries one flag, `--dry-run` (see the module docstring's Usage
    section); everything else is delegated to `plan_sweep` +
    `archive_and_commit`, called directly in-process. The sibling
    sweep-script test harnesses call `mod.main(argv if argv is not None else
    [])` uniformly, so the default must stay `None`-meaning-`sys.argv[1:]`.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from repo_identity import resolve_checked_repo_root  # pyright: ignore[reportMissingImports] — same runtime lib-bootstrap sys.path injection as above
    from sweep_argv import parse_repo_root_argv  # pyright: ignore[reportMissingImports] — same runtime lib-bootstrap sys.path injection as above

    argv = sys.argv[1:] if argv is None else argv
    _positional, flags, early_exit = parse_repo_root_argv(
        argv,
        prog="sweep-terminal-handoffs.py",
        usage=_USAGE,
        known_flags=frozenset({_DRY_RUN_FLAG}),
        max_positional=0,
    )
    if early_exit is not None:
        return early_exit
    dry_run = _DRY_RUN_FLAG in flags

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
    from coordinator_core.ops.fleet.archive_terminal_handoffs import plan_sweep
    from coordinator_core.ops.fleet._common import main_worktree_root
    from coordinator_core.git.repo_root import git_common_dir

    # `plan_sweep` is now SYNCHRONOUS (C2, docs/plans/2026-08-26-the-sweep-
    # stops-paying-for-a-room-it-nev.md); `archive_and_commit` (a separate,
    # out-of-scope module under active rewrite elsewhere -- staff-eng
    # Finding 9) remains a coroutine, so `asyncio` is imported below on the
    # ACT path only, for the single `asyncio.run(...)` boundary that still
    # drives it. A `--dry-run` census reaches neither, so it must not pay the
    # ~31ms `import asyncio` (which drags ssl/socket) to classify records —
    # the same cost C2 deleted from the op module's classification path.

    try:
        common_dir = Path(git_common_dir(cwd=str(repo_root)))
    except Exception as exc:
        print(f"sweep-terminal-handoffs.py: git_common_dir failed: {exc}", file=sys.stderr)
        return 1

    worktree_root = main_worktree_root(common_dir)

    if dry_run:
        scan_skipped: "list[dict]" = []
        try:
            moves, skipped = plan_sweep(
                worktree_root, common_dir, _CAP, scan_skipped=scan_skipped,
            )
        except Exception as exc:  # noqa: BLE001 -- mirrors the act path's own catch
            print(f"sweep-terminal-handoffs.py: dry run failed: {exc}", file=sys.stderr)
            return 1
        _print_planned_moves(moves)
        _print_refusal_census(scan_skipped, skipped)
        return 0

    import asyncio

    from coordinator_core.ops.fleet._common import archive_and_commit

    async def _sweep() -> dict:
        scan_skipped: "list[dict]" = []
        moves, skipped = plan_sweep(
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
