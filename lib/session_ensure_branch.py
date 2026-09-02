"""lib/session_ensure_branch.py — shared gate: cut work/{machine}/{today} when the
session opens on main, detached HEAD, or a zero-ahead non-span branch.

Native port of the retired bash gate (de-bash campaign, chunk E3-f). The
bash oracle's own `cs_parse_branch_span` was already a bridge shelling out to
`coordinator_core.daily_branch.parse_branch_span`; this port imports that
function directly instead — a straight Python import, not a subprocess spawn.

Source this module and call `session_ensure_branch`, or run the git-mutating
branch-cut logic ad hoc — this is an importable library, not a bin/ trampoline
(mirrors lib/release_currency.py — no .cmd launcher).

Spec backlink: state/handoffs/2026-07-04_220004_roadmap-strang-04.md § Phase 1
Port: docs/plans/2026-07-19-debash-coordinator-windows.md (chunk E3-f)

Soft seam — claude-klabauter action layer: a future `session.ensure_branch` op
(pcore-06/10) may eventually own the git-mutation half of this gate; until
that op exists, this module performs the git checkout/push subprocess calls
directly (matching the bash oracle's behavior — the bash oracle was never
gated on that future op either, it always did the git ops itself).
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# COORDINATOR_OVERRIDE_BRANCH pattern: every git mutation carries this env pair
# so the off-daily-branch PreToolUse guard does not deny it. Do NOT remove —
# the guard denies git checkout/push on non-daily branches without it.
# ---------------------------------------------------------------------------
_OVERRIDE_ENV = {
    "COORDINATOR_OVERRIDE_BRANCH": "1",
    "COORDINATOR_OVERRIDE_BRANCH_REASON": "session-ensure-branch: create/push workstream branch",
}


class SuffixCollisionError(RuntimeError):
    """Raised when no unused work/{machine}/{today}[-N] suffix is found (tried -2..-9)."""


@dataclass
class EnsureResult:
    result: str  # see the negative-spec in session_ensure_branch's docstring
    new_branch: str  # branch name when FRESH-CUT/ADOPTED-EXISTING/INHERITED; "" otherwise


#: The tree already sits on today's branch's tip and it merely had to be
#: checked out — content-neutral, no new ref minted.
ADOPTED_EXISTING = "ADOPTED-EXISTING"
#: Another session won the cut lock and this one inherited its branch. NOT
#: "FRESH-CUT" (this session did not cut) and NOT "REFUSED-LIVE-PEERS" (the
#: invariant now holds) — callers branching on the result MUST carry an arm
#: for it rather than folding it into either.
INHERITED = "INHERITED"

#: Today's branch existed but lagged HEAD -- every commit it carried was
#: already reachable from HEAD (the ordinary post-/merging-to-main state), so
#: its ref was advanced to HEAD and checked out. Content-neutral in exactly
#: the sense a fresh cut is: HEAD's commit does not move, no file is touched,
#: no index entry changes, and no commit is discarded (the ancestor test
#: below is what proves the last of those). NOT "FRESH-CUT" (no new ref was
#: minted) and NOT "ADOPTED-EXISTING" (a ref DID move); callers branching on
#: the result MUST carry an arm for it.
ADVANCED_TO_HEAD = "ADVANCED-TO-HEAD"

#: Bounded window a lock-loser polls for the winner's branch before falling
#: through to the timeout arm.
_INHERIT_POLL_SECONDS = 2.0
_INHERIT_POLL_INTERVAL = 0.05


def _branch_ref_exists(name: str) -> bool:
    proc = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        capture_output=True,
    )
    return proc.returncode == 0


def _branch_mutation_verdict():
    """Import indirection mirroring `_parses_as_branch_span` — native
    import, no subprocess spawn. Isolated so a missing/broken
    coordinator_core install degrades loudly via ImportError at call time
    rather than silently at module load."""
    from coordinator_core.session.worktree_safety import branch_mutation_verdict

    return branch_mutation_verdict


def _cut_lock():
    """Import indirection mirroring `_branch_mutation_verdict`."""
    from coordinator_core.session import day_branch_cut_lock

    return day_branch_cut_lock


def _git_capture(argv: list[str]) -> str:
    from coordinator_core.win_portability import no_console_creationflags

    proc = subprocess.run(argv, capture_output=True, **no_console_creationflags())
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _current_branch_now() -> str:
    return _git_capture(["git", "branch", "--show-current"])


def _head_sha(rev: str = "HEAD") -> str:
    return _git_capture(["git", "rev-parse", rev])


def _is_ancestor_of_head(rev: str) -> bool:
    """True iff every commit reachable from *rev* is already reachable from
    HEAD -- i.e. advancing *rev* to HEAD discards nothing.

    The whole safety argument for the ADVANCED_TO_HEAD arm rests on this
    one predicate, so it fails CLOSED: `git merge-base --is-ancestor` exits
    1 for "not an ancestor" and 128 for an unresolvable rev, and only exit 0
    is accepted. A missing git, an unreadable object, a broken ref -- every
    one of them reads as "not an ancestor" and routes to the unchanged
    refusal, never to a ref move.
    """
    from coordinator_core.win_portability import no_console_creationflags

    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", rev, "HEAD"],
        capture_output=True,
        **no_console_creationflags(),
    )
    return proc.returncode == 0


def _parses_as_branch_span(name: str) -> bool:
    """cs_parse_branch_span drop-in — native import, no subprocess spawn."""
    try:
        from coordinator_core.daily_branch import parse_branch_span
    except ImportError:
        return False
    try:
        return parse_branch_span(name) is not None
    except Exception:
        return False


def session_ensure_branch(
    machine: str,
    today: str,
    current: str,
    head_detached: str,
    commits_ahead,
    env: Optional[dict] = None,
    stderr=None,
    *,
    caller: str = "ceremony",
) -> EnsureResult:
    """Gate: on main, detached HEAD, or zero-ahead non-span branch → cut
    work/{machine}/{today} (collision-safe suffix loop), push it, return
    EnsureResult("FRESH-CUT", branch). Silent no-op (EnsureResult("", "")) when
    the gate condition is not met.

    Before cutting, consults
    coordinator_core.session.worktree_safety.branch_mutation_verdict — a
    branch is a property of the shared TREE, not of a session, so cutting
    one switches every live peer session's checkout out from under it. A
    non-"ok" verdict (both "refused" and "unknown" — the latter is FAIL
    CLOSED per that module's contract and MUST be treated the same as
    "refused") aborts the cut without touching git, prints
    "REFUSED-LIVE-PEERS branch=... reason=..." naming the peer detail, and
    returns EnsureResult("REFUSED-LIVE-PEERS", ""). This value is
    deliberately distinguishable from both "" (nothing-to-do) and
    "FRESH-CUT" (cut succeeded) — callers must not conflate it with either.

    ``caller`` selects one of two paths and defaults to the CEREMONY's
    pre-existing synchronous behaviour, so no existing caller changes:

      "ceremony" — /workday-start and friends, an EM present, no shared
        boot budget to protect. Wider admission set (main / detached /
        zero-ahead non-span), the -N collision suffix loop, and a
        SYNCHRONOUS ``git push -u``.
      "boot" — the SessionStart invariant (see
        ``coordinator_core/hooks/day_branch_assert.py``). ``main`` ONLY,
        the adopt-existing / advance-to-HEAD arms instead of the -N loop,
        and NO network call.

        Correction of record (2026-09-02): this used to say the boot path's
        push "is left to ``auto_push.push_once``, which already pushes with
        ``--set-upstream``." That has been false since C6/C7 of
        ``docs/plans/2026-08-30-who-pushes-and-when.md`` deleted the
        per-commit detached push; the cadence that replaced it
        (``warm.push_cadence``) reaches ``git_native.push``, a BARE
        ``git push``, which a branch with no upstream refuses outright. A
        boot-cut day branch therefore got an upstream from no path at all.
        The publish now belongs to the CEREMONY leg
        (``coordinator/bin/workday-start-day-branch-resolve.py``'s
        ``day-branch-assert`` subcommand, via
        ``ops.ceremony.push.publish_day_branch``), with
        ``push_with_retry``'s no-upstream arm as the backstop. Do not
        re-add a network call here.

    Two axes (admission width and push synchrony) always move together, so
    they are one parameter rather than two booleans that could be combined
    incoherently — e.g. a boot-width admission set with a synchronous push
    inside the fan-in's 10s budget, which is exactly the shape being
    avoided.

    Negative-spec — the result vocabulary now has SIX values and callers
    that branch on it MUST carry an arm for each. In particular:
      - ``ADVANCED-TO-HEAD`` means today's branch existed but lagged HEAD
        (the ordinary post-``/merging-to-main`` state) and its ref was
        advanced to HEAD and checked out. NOT ``ADOPTED-EXISTING`` (a ref
        moved) and NOT ``FRESH-CUT`` (no ref was minted). Reached ONLY when
        the old ref is an ancestor of HEAD, so nothing is discarded.
      - ``INHERITED`` is NOT ``FRESH-CUT`` (this session did not cut) and
        NOT ``REFUSED-LIVE-PEERS`` (the invariant HOLDS — some session cut
        and this one is on the branch). Folding it into either misreports a
        healthy tree.
      - ``ADOPTED-EXISTING`` means today's branch already existed and HEAD
        was already at its tip, so it was merely checked out. No new ref was
        minted; this is the routine every-boot answer once the day's first
        session has cut.

    Parameters mirror the bash oracle's positional contract:
      machine       — coordinator machine slug (from cs_compute_machine)
      today         — today's date YYYY-MM-DD (local day)
      current       — current branch name (git branch --show-current)
      head_detached — "yes" if HEAD is detached, "no" otherwise
      commits_ahead — commits ahead of origin/main (0 when on main or detached);
                       accepts int or str.

    Raises SuffixCollisionError when work/{machine}/{today}-2..-9 are all taken.

    Ceremony/oracle incoherence on -N collision suffixes (deliberate, not a
    bug): the -N branches this function mints are NOT accepted by
    daily_branch.is_canonical_branch (or parse_branch_span) — collision names
    are structurally non-canonical and stay that way. This is not a bug on
    either side: branch creation here runs via in-process subprocess.run with
    argv lists, never through the PreToolUse Bash seam, so the branch-
    creation deny guard structurally cannot see or reject a -N suffix —
    verified against HEAD, all nine ceremony-side creation/rename sites in
    the repo are in-process with no shell-visible path. Because the guard
    never judges these names, the oracle is not required to accept a shape
    it never has to judge at that seam. Widening parse_branch_span to accept
    -N was evaluated and rejected: it has four live tool-time callers
    (workday-start-step0.py Checks 2/3.5/4, workday-start-day-branch-
    resolve.py's _span_assert, workday-complete-step3-consolidate.py's
    _parse_branch_span, and this module's _parses_as_branch_span), and
    widening would move Step 0's Check 3.5 named-workstream precedence
    boundary for -N branches — a real ceremony-path behavior change with no
    guard-side benefit. See coordinator_core/daily_branch.py's module
    docstring for the full record.
    """
    err = stderr if stderr is not None else sys.stderr
    try:
        commits_ahead_int = int(commits_ahead)
    except (TypeError, ValueError):
        commits_ahead_int = 0

    is_main = current == "main"
    is_detached = head_detached == "yes"
    is_zero_ahead_non_span = (
        bool(current)
        and current != "main"
        and commits_ahead_int == 0
        and not _parses_as_branch_span(current)
    )

    if not (is_main or is_detached or is_zero_ahead_non_span):
        return EnsureResult(result="", new_branch="")

    is_boot = caller == "boot"
    if is_boot and not is_main:
        # Case (B) -- a detached HEAD and a zero-ahead non-span branch are not
        # "on main" in the PM's own words and take C10's warn, never a cut. The
        # CEREMONY caller keeps the wider admission set; inheriting it here
        # would silently extend the authorised reversal on a path that fires
        # on every boot.
        return EnsureResult(result="", new_branch="")

    from coordinator_core.session import worktree_safety as _ws

    branch_mutation_verdict = _branch_mutation_verdict()
    verdict = branch_mutation_verdict(operation=_ws.FRESH_CUT_AT_HEAD, current_branch=current)
    if verdict.outcome != "ok":
        print(
            f"REFUSED-LIVE-PEERS branch=work/{machine}/{today} reason={verdict.reason}",
            file=err,
        )
        return EnsureResult(result="REFUSED-LIVE-PEERS", new_branch="")

    target = f"work/{machine}/{today}"
    lock = _cut_lock()
    acquired = lock.acquire(".", session_id=_self_session_id())
    if not acquired.acquired:
        return _inherit(target, acquired, is_boot, env, err)

    try:
        return _cut_or_adopt(target=target, is_boot=is_boot, env=env, err=err)
    finally:
        lock.release(".")


def _self_session_id() -> str:
    try:
        from coordinator_core.session.core import resolve_session_id

        return resolve_session_id(None) or ""
    except Exception:
        return ""


def _inherit(target: str, acquired, is_boot: bool, env, err) -> EnsureResult:
    """Lock-loser path: poll for the winner's branch and INHERIT it.

    Losers do NOT queue for the cut -- the tree is shared, so the winner's
    checkout already IS the loser's checkout and inheriting needs no work from
    it. At poll timeout the lock record is re-read: a CONFIRMED-DEAD holder is
    taken over and cut; a LIVE holder is never raced, and the loser falls
    through to the genuine-failure banner naming the holder and the elapsed
    wait. A loser must never attempt an unserialised cut of its own.
    """
    import time as _time

    lock = _cut_lock()
    deadline = _time.monotonic() + _INHERIT_POLL_SECONDS
    while _time.monotonic() < deadline:
        branch = _current_branch_now()
        if branch and branch != "main":
            print(f"INHERITED branch={branch}")
            return EnsureResult(result=INHERITED, new_branch=branch)
        _time.sleep(_INHERIT_POLL_INTERVAL)

    record = lock.read_record(".")
    if record is not None and lock.record_is_stale(record):
        retry = lock.acquire(".", session_id=_self_session_id())
        if retry.acquired:
            try:
                return _cut_or_adopt(target=target, is_boot=is_boot, env=env, err=err)
            finally:
                lock.release(".")

    branch = _current_branch_now()
    if branch and branch != "main":
        print(f"INHERITED branch={branch}")
        return EnsureResult(result=INHERITED, new_branch=branch)

    print(
        f"REFUSED-LIVE-PEERS branch={target} reason=cut lock held by live "
        f"pid={acquired.holder_pid} sid={acquired.holder_sid or 'unknown'}; "
        f"waited {_INHERIT_POLL_SECONDS:.0f}s and the tree is still on main",
        file=err,
    )
    return EnsureResult(result="REFUSED-LIVE-PEERS", new_branch="")


def _cut_or_adopt(*, target: str, is_boot: bool, env, err) -> EnsureResult:
    from coordinator_core.win_portability import no_console_creationflags, run_forwarding

    new_branch = target

    if _branch_ref_exists(new_branch):
        if is_boot:
            # Every-boot invariant: the tree returns to main routinely
            # (/merging-to-main ends there), so re-entering the -N suffix loop
            # on every subsequent boot would mint a new branch each time and
            # raise SuffixCollisionError INSIDE a SessionStart hook on the
            # 10th. The cut mutex does not help -- it serialises CONCURRENT
            # boots, not sequential ones hours apart.
            head_sha = _head_sha()
            if head_sha and head_sha == _head_sha(new_branch):
                run_forwarding(
                    ["git", "checkout", new_branch],
                    env=_checkout_env(env),
                    stdout=err,
                    stderr=err,
                    check=True,
                    **no_console_creationflags(),
                )
                print(f"ADOPTED-EXISTING branch={new_branch}")
                return EnsureResult(result=ADOPTED_EXISTING, new_branch=new_branch)

            # The post-/merging-to-main state, and the reason this whole arm
            # exists. On 2026-09-02 today's branch was merged to `main` and
            # the tree returned to `main`, which left the local day-branch ref
            # BEHIND HEAD. Every subsequent boot found the branch existing,
            # found HEAD not at its tip, refused, printed the banner, and left
            # the tree on `main` -- for forty minutes and fifteen commits,
            # because nothing in the system ever repaired it. A detector that
            # reports the same true fact on every boot and changes nothing is
            # not a guard; the repair is the guard.
            #
            # Advancing the ref is content-neutral in exactly the sense the
            # fresh cut this function otherwise performs is: `checkout -B` at
            # HEAD leaves HEAD's commit where it is, touches no file and no
            # index entry, and -- given the ancestor test -- discards no
            # commit, because every commit the old ref named is already
            # reachable from HEAD. What it is NOT is a `checkout` of a
            # different commit, which is the hazard the refusal below still
            # covers: a branch carrying commits HEAD does not have is genuine
            # divergence, moving HEAD onto it would yank every live peer's
            # tree, and that case is refused exactly as before.
            if _is_ancestor_of_head(new_branch):
                run_forwarding(
                    ["git", "checkout", "-B", new_branch, "HEAD"],
                    env=_checkout_env(env),
                    stdout=err,
                    stderr=err,
                    check=True,
                    **no_console_creationflags(),
                )
                print(f"ADVANCED-TO-HEAD branch={new_branch}")
                return EnsureResult(result=ADVANCED_TO_HEAD, new_branch=new_branch)

            print(
                f"REFUSED-LIVE-PEERS branch={new_branch} reason=today's branch "
                "already exists and carries commit(s) HEAD does not; checking "
                "it out would MOVE HEAD, which case (A) does not cover -- never "
                "adopted silently",
                file=err,
            )
            return EnsureResult(result="REFUSED-LIVE-PEERS", new_branch="")

        # Ceremony path ONLY. The arm above makes this structurally
        # unreachable from the boot path -- keep it that way.
        n = 2
        while _branch_ref_exists(f"{new_branch}-{n}"):
            n += 1
            if n > 9:
                raise SuffixCollisionError(
                    "cannot find unused workstream branch suffix (tried -2 through -9)"
                )
        new_branch = f"{new_branch}-{n}"

    checkout_env = _checkout_env(env)

    # run_forwarding, not subprocess.run: `err` may be workday-start-step0's
    # own `sys.stderr`, which is an io.StringIO with no fileno() when this
    # gate runs in-process through coordinator_core.workday_complete.apply's
    # capture-buffer dispatch -- see coordinator_core.win_portability.
    # run_forwarding's own docstring.
    run_forwarding(
        ["git", "checkout", "-b", new_branch],
        env=checkout_env,
        stdout=err,
        stderr=err,
        check=True,
        **no_console_creationflags(),
    )

    if is_boot:
        # NO network call on the boot path. The SessionStart fan-in runs under
        # a single shared 10s timeout with no per-guard budget; a cold-
        # connection push to GitHub routinely exceeds it, and a harness kill
        # mid-push leaves the cut lock held by a dead process for the whole
        # stale-grace window. The upstream is established by the CEREMONY
        # leg instead (workday-start-day-branch-resolve.py's
        # day-branch-assert subcommand -> publish_day_branch), with
        # push_with_retry's no-upstream arm as the backstop -- NOT by
        # auto_push.push_once, whose per-commit caller C6/C7 of
        # docs/plans/2026-08-30-who-pushes-and-when.md deleted.
        print(f"FRESH-CUT branch={new_branch}")
        return EnsureResult(result="FRESH-CUT", new_branch=new_branch)

    push = subprocess.run(
        ["git", "push", "-u", "origin", new_branch],
        env=checkout_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **no_console_creationflags(),
    )
    if push.returncode != 0:
        print(
            "WARN: push of new branch failed -- crash insurance is NOT in "
            "force for this branch even though the cut succeeded",
            file=err,
        )
        if push.stdout:
            err.write(push.stdout.decode("utf-8", errors="replace"))

    print(f"FRESH-CUT branch={new_branch}")
    return EnsureResult(result="FRESH-CUT", new_branch=new_branch)


def _checkout_env(env):
    checkout_env = dict(env) if env is not None else None
    if checkout_env is not None:
        checkout_env.update(_OVERRIDE_ENV)
    return checkout_env
