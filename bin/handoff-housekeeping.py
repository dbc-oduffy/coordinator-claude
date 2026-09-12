"""handoff-housekeeping.py — the warm door onto `housekeeping.cycle`.

Purpose: one CLI for the ONE handoff-housekeeping job — close finished
handoffs, file them into `archive/handoffs/`, sweep up consumed ones — so a
ceremony reaches all three through a single name instead of three separately
dispatchable legs. Governing plan:
`docs/plans/2026-08-27-one-corpus-read-or-the-housekeeping-job-dies-a-fourth-time.md`.

SECOND JOB (C6, `docs/plans/2026-09-11-memo-deliveries-survive-the-receiver-s-
o.md`): this is also the `/workday-start` door that runs `memo.heal_inbox`
against the invoking repo, before `housekeeping.cycle`. It lives here, on this
CLI, rather than on the memo surfacer or inside `housekeeping.cycle` itself,
because neither of those can do it: the surfacer
(`coordinator_core/ops/workday_start_cross_repo_memo_outbox_surface.py`) is
READ-ONLY by its own negative-spec, and `housekeeping.cycle` forbids a second
commit route through it — a heal is a commit (a restore lands a file and a
commit; retire/rekey/adopt land ref writes). This door already IS the
committing entrypoint `/workday-start` calls, so the heal rides here instead
of minting a third call site. A heal failure never stops the handoff cycle —
see `main`'s own docstring for the exit-code rule.

WARM-SERVE IS THE POINT OF THIS FILE, not an incidental property of it. Every
timing figure in the governing plan is a WARM figure. Reached cold, this job
pays ~109ms of interpreter-plus-engine import before reading a single handoff,
or ~163ms through the `.cmd` forwarder (two interpreter starts) — against a
200ms process-time bar, leaving 37ms for a job measured at 65-95ms. The `.exe`
warm door is 23.5ms. So the cold/warm difference is not a tuning detail; it
decides whether this job is over the bar before it starts.

Warm serving is EARNED per bin name, and
`coordinator_core/warm/serve_classifier.py :: classify_entrypoint` decides it on
three structural conditions, all of which this file must keep satisfying:

  1. `coordinator/bin/<name>.py` exists.
  2. `main` is callable as `main(argv) -> int`. **Arity is checked
     independently** — a zero-arity `def main():` passes a naive has-a-main
     check and then raises TypeError the first time the warm door calls it with
     one argument. ~160 claude-klabauter names were once miscounted as warm-serving on
     exactly that basis.
  3. The module body is INERT — no work at import time.

Condition 3 is why every import below the stdlib set is deferred into `main()`.
Do not hoist them for tidiness: an import that reaches `coordinator_core` at
module scope makes this door fail the classifier, and the failure is silent —
the job keeps working and simply costs 163ms forever.

Guard: `coordinator_core/warm/tests/test_handoff_housekeeping_warm_serves.py`.

Usage:
    handoff-housekeeping [--cap N] [--no-close] [--dry-run]

    --cap N      move cap for this invocation (default 150). Positive int; the
                 op refuses absent/non-positive rather than defaulting to
                 unbounded.
    --no-close   sweep only; skip the close pass. For a caller that has just
                 closed records itself.
    --dry-run    plan and report, mutate nothing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Default move cap. The OP itself requires a positive cap and has no default —
#: this is the CLI's own recommended value, mirroring `sweep-terminal-handoffs.py`
#: citing `_RECOMMENDED_CAP_CHOICE` rather than re-deriving a rationale.
_DEFAULT_CAP = 150


def _ensure_claude_klabauter_on_path() -> str:
    """Put the claude-klabauter root on `sys.path` and return it.

    Resolved from this file's own location (`<root>/coordinator/bin/<name>.py`),
    never from cwd — this door is invoked from arbitrary worktrees.
    """
    root = str(Path(__file__).resolve().parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    The key names the ARCHIVAL JOB, not one script. `sweep-terminal-handoffs.py`
    was its only writer, so a monitor reading it saw the manual drain's cadence
    and nothing about the ceremony path that does the same work on the
    `/workday-complete` spine — a repo whose archival was healthy read as 24h
    stale, and a repo whose ceremony path was dead read as fresh after one
    manual run. Stamped from the mutating tail only: `--dry-run` mutates
    nothing and a plan is not a sweep (same reading the sibling CLI gives its
    census mode).
    """
    try:
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )

        stamp_liveness(repo_root, ARCHIVE_SWEEPS)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass


def _report_heal_inbox(result: dict) -> None:
    """Print `memo.heal_inbox`'s outcome per this door's own output contract:
    one line per restored memo, adopt/retire counts only when non-zero, and
    (to stderr) one line naming a per-item failure count. Never raises —
    a malformed result prints nothing rather than crashing the cycle it must
    not stop.

    Dry-run and act share this reporter but not an action-name vocabulary:
    `memo_heal.py`'s dry-run candidates are named in the not-yet-acted
    singular (`"restore"`, `"adopt"`, `"retire"`), the act path in the
    past-tense (`"restored"`, `"adopted"`, `"retired"`) — a dry run must
    report candidates in candidate voice and never claim a completed
    action."""
    try:
        dry_run = bool(result.get("dry_run"))
        items = (result.get("candidates") if dry_run else result.get("acted")) or []
        restore_action = "restore" if dry_run else "restored"
        adopt_action = "adopt" if dry_run else "adopted"
        retire_action = "retire" if dry_run else "retired"
        for item in items:
            if item.get("action") == restore_action:
                verb = "would restore" if dry_run else "restored"
                print(f"{verb} from anchor: {item.get('id')}")
        adopted = sum(1 for it in items if it.get("action") == adopt_action)
        retired = sum(1 for it in items if it.get("action") == retire_action)
        if adopted:
            verb = "would adopt" if dry_run else "adopted"
            print(f"heal: {verb} {adopted} memo(s)")
        if retired:
            verb = "would retire" if dry_run else "retired"
            print(f"heal: {verb} {retired} anchor(s)")
        failed = result.get("failed") or []
        if failed:
            print(
                f"handoff-housekeeping: heal: {len(failed)} memo(s) failed to heal — "
                f"check claude-klabauter logs",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001 -- reporting a heal must never crash the cycle
        print(f"handoff-housekeeping: heal report failed: {exc}", file=sys.stderr)


def _run_heal_inbox(common_dir: Path, dry_run: bool) -> bool:
    """Runs `memo.heal_inbox` against the invoking repo (`common_dir`) ahead
    of `housekeeping.cycle`, `dry_run` passed straight through from this
    CLI's own `--dry-run`. Returns True iff the heal itself failed (raised,
    or returned a non-zero `exit_code`) — the caller folds that into its own
    exit code only where its own path would otherwise have exited zero; a
    heal failure never skips or stops the handoff cycle that follows."""
    try:
        from coordinator_core.ops.fleet.memo_heal import _memo_heal_inbox

        result = _memo_heal_inbox({"dry_run": dry_run}, repo_root=str(common_dir))
    except Exception as exc:  # noqa: BLE001 -- a heal failure must never stop the cycle
        print(f"handoff-housekeeping: heal_inbox raised: {exc}", file=sys.stderr)
        return True

    _report_heal_inbox(result)
    return result.get("exit_code") not in (0, None)


def main(argv: "list[str] | None" = None) -> int:
    """Close finished handoffs, file them, sweep consumed. One call.

    `argv` is accepted and defaulted so the warm door can call `main(argv)` and
    a `__main__` block can call `main()` — see this module's docstring on why
    the arity is load-bearing rather than stylistic.

    Also runs `memo.heal_inbox` against the invoking repo before the handoff
    cycle (see module docstring, C6). A heal failure is printed, never
    silent, and never stops the cycle; it flips this call's own exit code to
    non-zero only where the cycle's own outcome would otherwise have been
    zero — a cycle that already fails on its own terms is not further
    distinguished by an unrelated heal failure.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    cap = _DEFAULT_CAP
    close = True
    dry_run = False
    while args:
        arg = args.pop(0)
        if arg == "--cap":
            if not args:
                print("handoff-housekeeping: --cap needs a value", file=sys.stderr)
                return 2
            try:
                cap = int(args.pop(0))
            except ValueError:
                print("handoff-housekeeping: --cap must be an integer", file=sys.stderr)
                return 2
        elif arg.startswith("--cap="):
            try:
                cap = int(arg.split("=", 1)[1])
            except ValueError:
                print("handoff-housekeeping: --cap must be an integer", file=sys.stderr)
                return 2
        elif arg == "--no-close":
            close = False
        elif arg == "--dry-run":
            dry_run = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"handoff-housekeeping: unknown argument {arg!r}", file=sys.stderr)
            return 2

    if cap <= 0:
        print(
            f"handoff-housekeeping: --cap must be positive, got {cap} — there is "
            f"no unbounded default",
            file=sys.stderr,
        )
        return 2

    _ensure_claude_klabauter_on_path()

    from coordinator_core.lifecycle import git_common_dir
    from coordinator_core.ops.fleet._common import main_worktree_root

    common_dir = git_common_dir(Path(os.getcwd()))
    if common_dir is None:
        print("handoff-housekeeping: not inside a git worktree", file=sys.stderr)
        return 1

    heal_failed = _run_heal_inbox(common_dir, dry_run)

    if dry_run:
        from coordinator_core.ops.fleet.archive_terminal_handoffs import plan_sweep

        worktree = main_worktree_root(common_dir)
        moves, skipped = plan_sweep(worktree, common_dir, cap)
        print(f"would archive {len(moves)} handoff(s); {len(skipped)} refused")
        for move in moves:
            print(f"  {getattr(move, 'candidate_id', move)}")
        return 1 if heal_failed else 0

    from coordinator_core.housekeeping.cycle import _handler

    result = _handler({"cap": cap, "close": close}, common_dir)

    if result.get("exit_code") != 0:
        print(f"handoff-housekeeping: {result.get('error')}", file=sys.stderr)
        return 1

    _stamp_archive_sweeps_liveness(str(main_worktree_root(common_dir)))

    archived = result.get("archived") or []
    # `closed` is an INT from `housekeeping.cycle` (a count), where the
    # retired `handoff.housekeeping` returned the list of cleared gates.
    # `len()` on the int raises -- and `or []` hid it exactly when the corpus
    # had nothing to close, so this read looked correct on a quiet run and
    # crashed on the first run that actually cleared a gate.
    closed = result.get("closed") or 0
    failed = result.get("failed") or []
    conflicts = result.get("conflicts") or []
    print(f"closed {closed}, archived {len(archived)}")
    if conflicts:
        print(
            f"handoff-housekeeping: {len(conflicts)} gate-clear(s) lost a race and were "
            f"left for the next cycle",
            file=sys.stderr,
        )
    if result.get("close_error"):
        # A failed close pass reports zero closed handoffs, which reads exactly
        # like a corpus with nothing to close. Say which one it was.
        print(
            f"handoff-housekeeping: close pass failed: {result['close_error']} — "
            f"the sweep still ran",
            file=sys.stderr,
        )
    if failed:
        print(
            f"handoff-housekeeping: WARN: {len(failed)} move(s) failed — check claude-klabauter logs",
            file=sys.stderr,
        )
        return 1
    return 1 if heal_failed else 0


if __name__ == "__main__":
    _ensure_claude_klabauter_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        _exit_code = main()
    sys.exit(_exit_code)
