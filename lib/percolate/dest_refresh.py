"""Bring a publish destination's checkout level with its origin before a round
materializes anything into it.

WHY THIS EXISTS. Every box in the fleet holds its own clone of the release
repo, and a percolate round writes the full published surface into that clone
and pushes it. A clone that is behind origin therefore does not merely miss a
peer's work -- it *reverts* it: the round syncs this box's idea of the whole
surface over the top, commits the difference as a deletion/rollback, and pushes
that as the new tip. Two boxes percolating in sequence, neither pulling, is a
ratchet that runs backwards. Refreshing first is what makes a round's commit a
delta against the fleet's tip rather than against this box's memory of it.

PM ruling 2026-09-02, in-session: the refresh is unconditional and blocking --
"the target release repo must be fully updated with origin/main before the
system starts, even if this means a few seconds delay" -- and it covers the
landing branch as well as `main`: "candidate branch of course on the local box
should be updated from origin before percolate and publish too, not just main,
as we land into candidate." The network round trip is a named exception to the
500ms brightline on that ruling, and belongs to the same class as
`push.outstanding.network`: its cost is the remote, not local work.

FAIL-CLOSED, AND ASYMMETRICALLY SO. A refresh that cannot be completed leaves
exactly the staleness this step exists to prevent, so a failure on the LANDING
branch (the checked-out one) refuses the round rather than proceeding on a
best-effort basis. `main` is warned about instead: it is not what a round lands
into, so a local `main` that cannot fast-forward cannot make this round
overwrite a peer -- it is a repo-hygiene fact worth printing, not a reason to
block a publish.

NEGATIVE SPEC. This module never forces, resets, rebases, or discards: every
update here is fast-forward-only. A landing branch that has diverged from its
upstream is a human's call -- the round refuses and says so, and no code path
here can turn a divergence into a silent overwrite. There is deliberately no
override flag; a caller that wants to publish from a stale clone has to make
the clone not stale.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TextIO

#: The landing branch's fetch is a remote round trip on a repo whose history
#: the box already holds; the observed cost is seconds, not tens of seconds.
#: Bounded well above that so a slow link degrades into a late round rather
#: than a spurious refusal, and far enough below a wedge that a dead remote
#: does not hold the destination lock indefinitely.
FETCH_TIMEOUT_SECS = 120.0

#: Every other leg here is local ref plumbing (`rev-parse`, `rev-list`, a
#: ff-only `merge`, a same-repo `fetch`) -- process creation is the whole cost.
LOCAL_GIT_TIMEOUT_SECS = 60.0

#: Same shape and same reason as `publish_sync._NO_CONSOLE`: a bare
#: `subprocess.run` of `git` pops a console window when this runs under a
#: windowless parent on Windows, and a percolate round spawns these per
#: destination.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


@dataclass(frozen=True)
class RefreshResult:
    """The outcome of one destination's refresh.

    `ok=False` is a refusal the caller must honour by not publishing into
    `repo_root`; `reason` is the sentence to print. `warnings` carries the
    non-blocking findings (the `main` leg), which are printed either way.
    """

    repo_root: Path
    ok: bool
    reason: str = ""
    branch: Optional[str] = None
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    fast_forwarded: bool = False
    warnings: tuple = ()


def _git(repo_root: Path, args: List[str], *, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), "--no-optional-locks", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        **_NO_CONSOLE,
    )


def _last_line(text: str, fallback: str) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[-1] if stripped else fallback


def _branch_and_upstream(repo_root: Path) -> "tuple[Optional[str], Optional[str], Optional[str]]":
    """`(branch, upstream, error)` for `repo_root`'s checked-out branch.

    One spawn for both names: `rev-parse` accepts several revs and prints one
    line each, so the branch and its tracking ref cost the same process. A
    detached HEAD prints `HEAD` for the first rev, and an untracked branch
    fails the whole invocation -- both are refusals, distinguished by message.
    """
    proc = _git(
        repo_root,
        ["rev-parse", "--abbrev-ref", "HEAD", "@{u}"],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if proc.returncode != 0:
        head = _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=LOCAL_GIT_TIMEOUT_SECS)
        name = head.stdout.strip() if head.returncode == 0 else "<unresolvable>"
        return name, None, _last_line(proc.stderr, "no upstream tracking ref")
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return (lines[0] if lines else None), None, "no upstream tracking ref"
    return lines[0], lines[1], None


def _ahead_behind(
    repo_root: Path, upstream: str
) -> "tuple[Optional[int], Optional[int], Optional[str]]":
    proc = _git(
        repo_root,
        ["rev-list", "--left-right", "--count", "HEAD..." + upstream],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if proc.returncode != 0:
        return None, None, _last_line(proc.stderr, "could not compare HEAD with " + upstream)
    parts = proc.stdout.split()
    if len(parts) != 2:
        return None, None, "unparseable rev-list output: {0!r}".format(proc.stdout)
    try:
        return int(parts[0]), int(parts[1]), None
    except ValueError:
        return None, None, "unparseable rev-list output: {0!r}".format(proc.stdout)


def _refresh_local_main(repo_root: Path, checked_out: Optional[str]) -> Optional[str]:
    """Fast-forward a local, non-checked-out `main` to `origin/main`.

    Returns a warning sentence, or `None` when there was nothing to say. The
    fetch source is the repository itself, so `refs/remotes/origin/main` is
    read from the tip the caller's network fetch just wrote -- no second round
    trip. `git fetch` refuses a non-fast-forward branch update by default, and
    that default is the guarantee this leg rests on: nothing here can rewrite a
    local `main` that carries commits origin does not have.
    """
    if checked_out == "main":
        return None  # already handled as the landing branch
    have_remote = _git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if have_remote.returncode != 0:
        return None  # this remote has no `main` -- nothing to be level with
    have_local = _git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if have_local.returncode != 0:
        return None  # no local `main` to keep current
    proc = _git(
        repo_root,
        ["fetch", "--no-tags", ".", "refs/remotes/origin/main:refs/heads/main"],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if proc.returncode != 0:
        return (
            "local `main` in {0} could not be fast-forwarded to origin/main ({1}); "
            "the round lands on the checked-out branch and proceeds".format(
                repo_root, _last_line(proc.stderr, "git fetch failed")
            )
        )
    return None


def refresh_dest_from_origin(repo_root: Path, *, out: TextIO, err: TextIO) -> RefreshResult:
    """Fetch `origin` and fast-forward `repo_root`'s landing branch (and `main`).

    The one entry point. Callers hold `repo_root`'s destination lock across
    this call, so the refresh and the round that follows cannot be interleaved
    with a peer's write to the same clone.
    """
    repo_root = Path(repo_root)
    branch, upstream, name_err = _branch_and_upstream(repo_root)
    if name_err is not None or upstream is None:
        if branch == "HEAD":
            reason = (
                "{0} is in detached HEAD -- a round cannot tell which branch it would "
                "land on, so it cannot be brought level with origin first".format(repo_root)
            )
        else:
            reason = (
                "{0}'s checked-out branch ({1}) has no upstream tracking ref, so it "
                "cannot be brought level with origin before publishing".format(repo_root, branch)
            )
        return RefreshResult(repo_root, ok=False, reason=reason, branch=branch)

    print(
        "[dest-refresh] {0}: fetching origin (landing branch {1})".format(repo_root, branch),
        file=out,
    )
    fetch = _git(repo_root, ["fetch", "--no-tags", "--prune", "origin"], timeout=FETCH_TIMEOUT_SECS)
    if fetch.returncode != 0:
        return RefreshResult(
            repo_root,
            ok=False,
            reason=(
                "could not fetch origin for {0} ({1}); publishing from a clone that could "
                "not be brought level would overwrite whatever another box has already "
                "landed".format(repo_root, _last_line(fetch.stderr, "git fetch failed"))
            ),
            branch=branch,
            upstream=upstream,
        )

    ahead, behind, count_err = _ahead_behind(repo_root, upstream)
    if count_err is not None or ahead is None or behind is None:
        return RefreshResult(
            repo_root,
            ok=False,
            reason="could not measure {0}'s {1} against {2}: {3}".format(
                repo_root, branch, upstream, count_err
            ),
            branch=branch,
            upstream=upstream,
        )

    if ahead and behind:
        return RefreshResult(
            repo_root,
            ok=False,
            reason=(
                "{0}'s {1} has diverged from {2} ({3} ahead, {4} behind) -- reconciling "
                "that is a human's call, and publishing over it would discard one "
                "side".format(repo_root, branch, upstream, ahead, behind)
            ),
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
        )

    fast_forwarded = False
    if behind:
        merge = _git(repo_root, ["merge", "--ff-only", upstream], timeout=LOCAL_GIT_TIMEOUT_SECS)
        if merge.returncode != 0:
            detail = _last_line(merge.stderr or merge.stdout, "ff-only merge failed")
            return RefreshResult(
                repo_root,
                ok=False,
                reason=(
                    "{0}'s {1} is {2} behind {3} and could not be fast-forwarded "
                    "({4})".format(repo_root, branch, behind, upstream, detail)
                ),
                branch=branch,
                upstream=upstream,
                ahead=ahead,
                behind=behind,
            )
        fast_forwarded = True
        print(
            "[dest-refresh] {0}: {1} fast-forwarded {2} commit(s) to {3}".format(
                repo_root, branch, behind, upstream
            ),
            file=out,
        )
    else:
        print(
            "[dest-refresh] {0}: {1} already level with {2}".format(repo_root, branch, upstream),
            file=out,
        )

    warnings: List[str] = []
    main_warning = _refresh_local_main(repo_root, branch)
    if main_warning is not None:
        warnings.append(main_warning)
        print("[dest-refresh] WARNING: {0}".format(main_warning), file=err)

    return RefreshResult(
        repo_root,
        ok=True,
        branch=branch,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        fast_forwarded=fast_forwarded,
        warnings=tuple(warnings),
    )


def reconcile_dest_before_push(repo_root: Path, *, out: TextIO, err: TextIO) -> RefreshResult:
    """Bring `repo_root` level with origin again, immediately before its push.

    `refresh_dest_from_origin` closes the window BEFORE a round; this closes
    the one DURING it. A full round takes minutes, and a peer box landing in
    that window turns the push into a non-fast-forward rejection with a
    finished, committed round stranded in the mirror -- observed on the very
    first run of the pre-round refresh (2026-09-02).

    The reconciliation here is a MERGE, not a fast-forward, and that asymmetry
    with `refresh_dest_from_origin` is forced rather than chosen: by this point
    the round's own commit is on the landing branch, so the branch is ahead as
    well as behind and no fast-forward exists. A merge is nonetheless the right
    shape for this repo specifically -- both sides are projections of the same
    published surface from two boxes' sources, so they agree except where the
    sources do. Where they do NOT agree, git says so: a conflicted merge is
    aborted here and refused, never resolved by picking a side, because
    picking a side is precisely the overwrite this whole mechanism exists to
    prevent.

    `ok=True` with `fast_forwarded=True` means a merge commit was made and the
    caller should push. `ok=True` with `fast_forwarded=False` means there was
    nothing to reconcile.
    """
    repo_root = Path(repo_root)
    branch, upstream, name_err = _branch_and_upstream(repo_root)
    if name_err is not None or upstream is None:
        return RefreshResult(
            repo_root,
            ok=False,
            reason=(
                "{0}'s checked-out branch ({1}) has no upstream tracking ref, so its "
                "push cannot be checked against origin first".format(repo_root, branch)
            ),
            branch=branch,
        )

    fetch = _git(repo_root, ["fetch", "--no-tags", "--prune", "origin"], timeout=FETCH_TIMEOUT_SECS)
    if fetch.returncode != 0:
        return RefreshResult(
            repo_root,
            ok=False,
            reason="could not fetch origin for {0} before pushing ({1})".format(
                repo_root, _last_line(fetch.stderr, "git fetch failed")
            ),
            branch=branch,
            upstream=upstream,
        )

    ahead, behind, count_err = _ahead_behind(repo_root, upstream)
    if count_err is not None or ahead is None or behind is None:
        return RefreshResult(
            repo_root,
            ok=False,
            reason="could not measure {0}'s {1} against {2} before pushing: {3}".format(
                repo_root, branch, upstream, count_err
            ),
            branch=branch,
            upstream=upstream,
        )

    if not behind:
        return RefreshResult(
            repo_root, ok=True, branch=branch, upstream=upstream, ahead=ahead, behind=0
        )

    print(
        "[dest-refresh] {0}: {1} is {2} commit(s) behind {3} — a peer landed during this "
        "round; merging before push".format(repo_root, branch, behind, upstream),
        file=out,
    )
    merge = _git(
        repo_root,
        ["merge", "--no-edit", upstream],
        timeout=LOCAL_GIT_TIMEOUT_SECS,
    )
    if merge.returncode != 0:
        detail = _last_line(merge.stdout or merge.stderr, "merge failed")
        _git(repo_root, ["merge", "--abort"], timeout=LOCAL_GIT_TIMEOUT_SECS)
        return RefreshResult(
            repo_root,
            ok=False,
            reason=(
                "{0}'s {1} and {2} both changed the same published paths and could not be "
                "merged ({3}); the merge was aborted and nothing was pushed -- resolving "
                "which box's source is right is a human's call".format(
                    repo_root, branch, upstream, detail
                )
            ),
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
        )

    print(
        "[dest-refresh] {0}: merged {1} ({2} peer commit(s)) into {3}".format(
            repo_root, upstream, behind, branch
        ),
        file=out,
    )
    return RefreshResult(
        repo_root,
        ok=True,
        branch=branch,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        fast_forwarded=True,
    )
