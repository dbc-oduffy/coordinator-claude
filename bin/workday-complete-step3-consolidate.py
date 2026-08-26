"""workday-complete-step3-consolidate.py — Step 3 Branch Consolidation for /workday-complete.

Encapsulates the deterministic branch-consolidation procedure from
commands/workday-complete.md § Step 3 so it is independently invokable, testable, and
not skippable by EM discretion.

Spec backlink: commands/workday-complete.md § Step 3

Stdout: one-line-per-action summary (machine-readable prefix [step3])
Stderr: detailed git command output and warnings

Exit codes:
  0 — full success
  1 — sync-main aborted; OR detached HEAD / running on main/master branch (guard)
  2 — merge conflict during sibling merge (halt; PM resolves)
  3 — reconcile with origin/main hit a conflict
  4 — push rejected twice (PM surface)
  5 — cs_compute_machine unavailable (lib missing)

Negative-spec: does NOT touch feature/* branches (intentionally long-lived).
Does NOT modify sync-main.py or coordinator-current-branch.py.

History-rewrite safety (F4): before the reconcile/push steps, consults
coordinator_core.session.worktree_safety.history_rewrite_verdict() for a live
local-peer-session check (a rebase or force-push mutates the local HEAD every live
peer's uncommitted diff is anchored to — --force-with-lease alone only protects the
remote). A non-"ok" verdict ("refused" or "unknown" — treated identically) degrades
reconcile to a fast-forward-only merge (never a rebase) and push to a plain
`git push` (never --force-with-lease, never a rebase retry); this is a SAFE, non-error
outcome and does not change the exit code by itself. The verdict is a point-in-time
read, so it is re-resolved immediately before EACH destructive site — once at 3.2b
for the up-front operator-visible line, again immediately before the reconcile
step's rebase/ff-only decision, and again immediately before the push step's
force-with-lease/plain decision — rather than one snapshot reused across the whole
script body, since sibling discovery/merging (3.3-3.4) between the first read and
the destructive sites can take arbitrarily long (conflict-laden, PM-attended) and a
peer session going live in that window must not be invisible to the gate.

Port of: workday-complete-step3-consolidate.sh (DoE 091c0f3e, 2026-07-19).
`today` is natively imported from coordinator_core.daily_day.local_day (de-bash campaign,
2026-07-21 — Port of: coordinator-daily-day.sh, DoE c6d97219, 2026-07-22).
cs_compute_machine / cs_parse_branch_span are natively imported from
coordinator_core.machine_resolver / coordinator_core.daily_branch (de-bash campaign,
unit "daily-branch" — Port of: coordinator-daily-branch.sh, DoE 2fbe0e77, 2026-07-19, see
cc_invoke._resolve_claude_klabauter_root for the engine-root ladder this import rides). sync-main.py
is invoked as a subprocess.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Locate the shared module via realpath (always the true bin/lib, survives symlinked
# invocation) but compute PLUGIN_ROOT from the non-resolved __file__ so the lib-discovery
# path is fakeable by a symlinked entrypoint (test9 relies on this to force exit 5).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import workday_ceremony_lib as wc  # noqa: E402
from cc_invoke import _resolve_claude_klabauter_root, require_dispatch_engine_on_path, child_env  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_SYNC_MAIN = os.environ.get("STEP3_SYNC_MAIN") or os.path.join(PLUGIN_ROOT, "bin", "sync-main.py")
_BIN_CURRENT_BRANCH = os.path.join(PLUGIN_ROOT, "bin", "coordinator-current-branch.py")

_HELP = """Usage: workday-complete-step3-consolidate.py [--no-push] [--dry-run]

  --no-push   Perform local consolidation; skip push step.
  --dry-run   Print what would happen; perform no git mutations.

Exit codes: 0=ok 1=sync-main-abort 2=merge-conflict 3=reconcile-conflict
            4=push-rejected-twice 5=lib-missing"""


def _out(msg: str) -> None:
    print(msg)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _git_stream(*args: str) -> int:
    """Run `git <args>`, forwarding stdout+stderr to our stderr; return exit code."""
    proc = wc.git(*args)
    if proc.stdout:
        sys.stderr.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.stderr.flush()
    return proc.returncode


def _compute_machine() -> str:
    """Native cs_compute_machine equivalent — coordinator_core.machine_resolver.compute_machine."""
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.machine_resolver import compute_machine
    return compute_machine()


def _parse_branch_span(branch: str) -> str | None:
    """cs_parse_branch_span equivalent — coordinator_core.daily_branch.parse_branch_span.

    Returns 'start end' (space-joined) or None on parse failure, matching the retired
    bash bridge's stdout shape so downstream .split() call sites are unchanged.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.daily_branch import parse_branch_span
    span = parse_branch_span(branch)
    if span is None:
        return None
    return f"{span[0]} {span[1]}"


def _branch_covers_today(branch: str, today: str) -> bool:
    span = _parse_branch_span(branch)
    if span is None:
        return False
    parts = span.split()
    start_date = parts[0]
    end_date = parts[-1]
    return not (today < start_date) and not (end_date < today)


def _matching_work_branches(list_args: list[str], machine: str) -> list[str]:
    """Run `git branch <list_args>`, filter to work/<machine>/ lines (case-insensitive),
    return the stripped branch names."""
    proc = wc.git(*(["branch"] + list_args))
    if proc.returncode != 0:
        return []
    prefix_re = re.compile(r'^\*? *work/' + re.escape(machine) + r'/', re.IGNORECASE)
    names = []
    for raw in proc.stdout.splitlines():
        if not prefix_re.match(raw):
            continue
        name = raw.strip().lstrip('*').strip()
        if name:
            names.append(name)
    return names


def main(argv: list[str]) -> int:
    no_push = False
    dry_run = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-push":
            no_push = True
        elif a == "--dry-run":
            dry_run = True
        elif a in ("--help", "-h"):
            print(_HELP)
            return 0
        else:
            _err(f"[step3] ERROR: unknown argument: {a}")
            return 1
        i += 1

    # Native-module availability guard.
    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
        from coordinator_core.daily_day import local_day
    except RuntimeError as exc:
        _err(f"[step3] ERROR: lib not found — engine-root resolution failed: {exc}")
        return 5

    from coordinator_core.win_portability import no_console_creationflags, run_forwarding

    # Step 3.0 — sync-main
    if dry_run:
        _err("[step3] DRY-RUN: would run sync-main.py")
        _out("[step3] sync-main: ok")
    else:
        # run_forwarding, not subprocess.run: this directive is reachable
        # in-process through coordinator_core.workday_complete.apply's
        # capture-buffer dispatch, where sys.stderr is an io.StringIO with
        # no fileno() — see run_forwarding's own docstring.
        sm = run_forwarding(
            [sys.executable, _BIN_SYNC_MAIN], stdout=sys.stderr, stderr=sys.stderr,
            env=child_env(),
            **no_console_creationflags(),
        )
        if sm.returncode != 0:
            _err("[step3] sync-main: FAILED")
            return 1
        _out("[step3] sync-main: ok")

    # Step 3.1 — machine and today
    machine = _compute_machine()
    today = local_day()
    _out(f"[step3] machine: {machine}")
    _out(f"[step3] today: {today}")

    # Step 3.2 — current branch
    current_branch = ""
    if os.path.isfile(_BIN_CURRENT_BRANCH):
        try:
            cb = subprocess.run(
                [sys.executable, _BIN_CURRENT_BRANCH], capture_output=True, text=True,
                timeout=15, env=child_env(), **no_console_creationflags(),
            )
            current_branch = cb.stdout.strip() if cb.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            # Review: code-reviewer — parity with step9's _get_branch fail-open
            # guard; falls through to the existing git-show-current fallback below.
            current_branch = ""
    if not current_branch:
        current_branch = wc.git_out("branch", "--show-current")

    if not current_branch:
        _err("[step3] ERROR: cannot determine current branch (detached HEAD?)")
        return 1
    if current_branch in ("main", "master"):
        _err(f"[step3] ERROR: current branch is '{current_branch}' — Step 3 must run on a workstream branch")
        return 1

    # Step 3.2b — history-rewrite safety verdict (F4). A rebase or force-push
    # mutates the local HEAD that every live peer session's uncommitted diff is
    # anchored to; this gate is about local shared-worktree peers, not the
    # remote (--force-with-lease already covers the remote). "unknown" is
    # treated identically to "refused" everywhere below — see
    # coordinator_core.session.worktree_safety's module docstring. The verdict
    # is a point-in-time read (see that module's negative-spec on not
    # memoizing live_session_ids), so this early call is for the up-front
    # operator line only; the reconcile and push steps below each re-resolve
    # it immediately before their own destructive git call, since sibling
    # discovery/merging (3.3-3.4) between here and there can take arbitrarily
    # long and a peer session going live in that window must not be invisible
    # to the gate.
    from coordinator_core.session.worktree_safety import history_rewrite_verdict

    def _resolve_rewrite_verdict():
        verdict = history_rewrite_verdict()
        if verdict.outcome != "ok":
            _out(f"[step3] REFUSED-HISTORY-REWRITE: {verdict.reason}")
        return verdict, verdict.outcome == "ok"

    rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()

    # Step 3.3 — discover sibling workstream branches
    sibling_branches = []
    for name in _matching_work_branches(["--list"], machine):
        if name == current_branch:
            continue
        if not _branch_covers_today(name, today):
            continue
        sibling_branches.append(name)
    siblings_display = ",".join(sibling_branches) if sibling_branches else "none"
    _out(f"[step3] siblings discovered: {siblings_display}")

    # Step 3.4 — merge siblings into current branch
    merged_count = 0
    for sibling in sibling_branches:
        if dry_run:
            _err(f"[step3] DRY-RUN: would merge {sibling}")
            merged_count += 1
            continue
        _err(f"[step3] merging sibling: {sibling}")
        if _git_stream("merge", "--no-edit", sibling) != 0:
            _err(f"[step3] CONFLICT merging sibling branch: {sibling}")
            _err("[step3] Aborting merge. Resolve conflicts, then re-run.")
            _git_stream("merge", "--abort")
            return 2
        merged_count += 1
    _out(f"[step3] siblings merged: {merged_count}")

    # Step 3.5 — reconcile with origin/main
    reconcile_status = "no-op (origin/main missing)"
    if dry_run:
        _err("[step3] DRY-RUN: would reconcile with origin/main")
        reconcile_status = "no-op (dry-run)"
    elif not wc.git_ok("rev-parse", "--verify", "origin/main"):
        _err("[step3] origin/main not present locally — skipping reconcile")
        reconcile_status = "no-op (origin/main missing)"
    else:
        behind = wc.git_out("rev-list", "--count", "HEAD..origin/main") or "0"
        if behind == "0":
            ahead = wc.git_out("rev-list", "--count", "origin/main..HEAD") or "0"
            if ahead == "0":
                _err("[step3] branch is at origin/main — no rebase needed")
                reconcile_status = "no-op (at origin/main)"
            else:
                _err("[step3] branch already contains origin/main — no rebase needed")
                reconcile_status = "no-op (ahead-only)"
        else:
            # Re-resolve immediately before the rebase-vs-ff-only decision —
            # sibling merging (3.3-3.4) may have taken arbitrarily long since
            # the 3.2b read, and a peer session going live in that window must
            # not be invisible to the gate.
            rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
            if not rewrite_ok:
                _err(
                    f"[step3] {behind} commit(s) behind origin/main — history rewrite refused "
                    f"({rewrite_verdict.reason}); attempting fast-forward-only merge instead of rebase..."
                )
                if _git_stream("merge", "--ff-only", "origin/main") == 0:
                    reconcile_status = f"fast-forward (rewrite refused: {rewrite_verdict.reason})"
                else:
                    _err("[step3] fast-forward-only merge not possible — leaving branch unreconciled")
                    reconcile_status = f"refused ({rewrite_verdict.reason}) — branch left unreconciled"
            else:
                _err(f"[step3] {behind} commit(s) behind origin/main — rebasing...")
                if _git_stream("rebase", "origin/main") == 0:
                    reconcile_status = "rebased"
                else:
                    _err("[step3] rebase had conflicts; falling back to merge...")
                    _git_stream("rebase", "--abort")
                    if _git_stream("merge", "origin/main") == 0:
                        reconcile_status = "merged (fallback)"
                    else:
                        _err("[step3] CONFLICT reconciling with origin/main")
                        _git_stream("merge", "--abort")
                        return 3
    _out(f"[step3] reconcile: {reconcile_status}")

    # Step 3.6 — push current branch, via push_outstanding() (C4b, AC8): the
    # canonical primitive the C4-registered `push.outstanding` op wraps for
    # every cadence surface (coordinator_core.ops.ceremony.push_outstanding).
    # The plan's own anti-scope forbids new hand-rolled `git push` call
    # sites, so this delegates entirely to `push_outstanding()` rather than
    # re-implementing push-with-retry/branch_gate here the way the prior
    # hand-rolled `_git_stream("push", "--force-with-lease", ...)` retry
    # ladder did. `push_summary` (not `push_status`) is this script's own
    # local variable name deliberately -- `push_status` is
    # `commit_pipeline.py`'s canonical vocabulary
    # (pushed/push-failed/declined/no-remote/not-attempted/unconfirmed) and
    # this script's own strings ("ok"/"skipped (--no-push)"/etc.) are not
    # that vocabulary, so a later name-based sweep must not mistake this for
    # a fourth spelling of it (F8).
    push_summary = ""
    if no_push:
        push_summary = "skipped (--no-push)"
    elif dry_run:
        rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
        if rewrite_ok:
            _err(
                f"[step3] DRY-RUN: would push origin/{current_branch} "
                "with --force-with-lease (reconcile rewrote history)"
            )
        else:
            _err(
                f"[step3] DRY-RUN: would push origin/{current_branch} "
                f"via push_outstanding() (rewrite refused: {rewrite_verdict.reason})"
            )
        push_summary = "skipped (--dry-run)"
    else:
        rewrite_verdict, rewrite_ok = _resolve_rewrite_verdict()
        if rewrite_ok:
            _err(
                f"[step3] reconcile rewrote history -- pushing to "
                f"origin/{current_branch} with --force-with-lease"
            )
            if _git_stream("push", "--force-with-lease", "origin", current_branch) != 0:
                _err(
                    "[step3] force-with-lease push failed -- the remote moved since the "
                    "last fetch, or the push was refused. PM must resolve before continuing."
                )
                return 4
            push_summary = "ok (force-with-lease, after history rewrite)"
        else:
            _err(f"[step3] pushing to origin/{current_branch} via push_outstanding()...")
            from coordinator_core.ops.ceremony.push_outstanding import push_outstanding

            outcome = push_outstanding(Path(os.getcwd()))
            for note in (
                list(outcome.skipped) + list(outcome.failed) + list(outcome.unconfirmed)
            ):
                _err(f"[step3] push_outstanding: {note}")

            if outcome.failed or outcome.unconfirmed:
                _err(
                    "[step3] push failed via push_outstanding(). "
                    "PM must resolve before continuing."
                )
                return 4
            if "push:nothing-outstanding" in outcome.skipped:
                push_summary = "ok (nothing outstanding)"
            elif "push" in outcome.acted:
                push_summary = "ok"
            elif "push:no-remote" in outcome.skipped:
                push_summary = "ok (no-remote)"
            elif (
                "push:branch-policy" in outcome.skipped
                or "push:branch-unresolvable" in outcome.skipped
            ):
                push_summary = "ok (declined by branch policy)"
            else:
                push_summary = "ok"
    _out(f"[step3] push: {push_summary}")

    # Step 3.7 — delete merged sibling branches
    deleted_count = 0
    if dry_run:
        _err("[step3] DRY-RUN: would delete merged sibling branches")
    else:
        for name in _matching_work_branches(["--merged"], machine):
            if name == current_branch:
                continue
            if not _branch_covers_today(name, today):
                continue
            _err(f"[step3] deleting merged sibling: {name}")
            if _git_stream("branch", "-d", name) == 0:
                deleted_count += 1
            else:
                _err(f"[step3] WARN: could not delete {name} — may not be fully merged")
    _out(f"[step3] siblings deleted: {deleted_count}")

    _out("[step3] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
