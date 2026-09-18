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

WHAT "LEVEL WITH ORIGIN" MEANS FOR A BRANCH WITH NO UPSTREAM. It means level
with the remote's DEFAULT branch, not a refusal. A tracking ref is how the
comparison is USUALLY made, never the thing being protected -- what is protected
is that this clone's base is not behind the tip a peer landed on, and a branch
with no upstream has a base like any other. A fresh clone on a fresh local
branch is the ordinary cloud shape, so refusing it made the normal case the
broken one. `default_remote_branch` resolves the base; only a clone that can
name no remote branch at all is refused, and detached HEAD still is (there is no
landing branch to measure).

NEGATIVE SPEC. This module never forces, resets, rebases, or discards: every
update here is fast-forward-only. A landing branch that has diverged from its
upstream is a human's call -- the round refuses and says so, and no code path
here can turn a divergence into a silent overwrite. There is deliberately no
override flag; a caller that wants to publish from a stale clone has to make
the clone not stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TextIO

from coordinator_core.git.run import GitResult, run_git



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


def _git(repo_root: Path, args: List[str], *, remote: bool = False) -> GitResult:
    """Every git leg in this module, through the one seam that carries a bound.

    Was a private runner with its own two timeout constants (a 120s fetch, a
    60s everything-else) and its own `CREATE_NO_WINDOW` mapping. Both dials
    are gone rather than repointed: `coordinator_core.git.run` holds the only
    two a git spawn may carry -- `LOCAL_PLUMBING_BUDGET_SECS` for the ref
    plumbing (`rev-parse`, `rev-list`, a ff-only `merge`) and
    `REMOTE_BUDGET_SECS` under `remote=True` for the two `fetch` legs -- and
    console suppression is that seam's job too.

    `remote` is the fetch legs ONLY, and narrows rather than widens what the
    old constant allowed: the fetch is a round trip against a repo whose
    history this box already holds, whose observed cost the deleted constant's
    own note put at "seconds, not tens of seconds".
    """
    return run_git(
        ["-C", str(repo_root), "--no-optional-locks", *args],
        remote=remote,
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
    )
    if proc.returncode != 0:
        head = _git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
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
    )
    if have_remote.returncode != 0:
        return None  # this remote has no `main` -- nothing to be level with
    have_local = _git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
    )
    if have_local.returncode != 0:
        return None  # no local `main` to keep current
    proc = _git(
        repo_root,
        ["fetch", "--no-tags", ".", "refs/remotes/origin/main:refs/heads/main"],
    )
    if proc.returncode != 0:
        return (
            "local `main` in {0} could not be fast-forwarded to origin/main ({1}); "
            "the round lands on the checked-out branch and proceeds".format(
                repo_root, _last_line(proc.stderr, "git fetch failed")
            )
        )
    return None


def default_remote_branch(repo_root: Path) -> Optional[str]:
    """`origin/<default branch>`, or `None` when the clone cannot name one.

    Three rungs, cheapest first, all local — no network:
      1. `refs/remotes/origin/HEAD`'s symbolic target, which a normal
         `git clone` writes and which is the remote's OWN answer.
      2. `refs/remotes/origin/main`, then 3. `refs/remotes/origin/master`,
         for a clone fetched with `--no-tags`/`--single-branch` or one whose
         `origin/HEAD` was never set (a fetched-into-existing-repo shape).

    This exists for the NO-UPSTREAM case below and nothing else; a branch that
    HAS an upstream is always measured against that upstream, never against
    this.
    """
    head = _git(repo_root, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"])
    if head.returncode == 0:
        ref = head.stdout.strip()
        if ref.startswith("refs/remotes/"):
            return ref[len("refs/remotes/") :]
    for candidate in ("origin/main", "origin/master"):
        probe = _git(
            repo_root,
            ["rev-parse", "--verify", "--quiet", "refs/remotes/" + candidate],
        )
        if probe.returncode == 0:
            return candidate
    return None


def _no_upstream_base(
    repo_root: Path, branch: Optional[str], *, out: TextIO
) -> "tuple[Optional[str], Optional[str]]":
    """`(base_ref, refusal_reason)` for a checked-out branch with no upstream.

    WHY THIS IS NOT A FATAL. The refusal it replaces read "cannot be brought
    level with origin before publishing", which is the right INSTINCT applied
    to the wrong FACT: a branch with no upstream has no remote counterpart to
    be level WITH, so there is nothing to fast-forward and nothing a publish
    here could revert on that branch. What the module actually protects is
    narrower and survives intact — a clone whose BASE is behind the fleet's
    tip would republish the whole surface over the top of work landed since.
    That base is the remote's default branch, which this resolves, so the
    no-upstream case is measured against the same tip every other case is,
    instead of being refused for lacking a ref it was never going to need.

    A fresh clone on a new local branch is the ORDINARY cloud shape — a
    container clones the mirror and a session checks out its own branch — and
    a fatal there made the normal case the broken one. It still refuses when
    the clone can name no remote branch at all, because then there genuinely
    is no tip to measure against, and it names the one command that fixes it.
    """
    base = default_remote_branch(repo_root)
    if base is None:
        return None, (
            "{0}'s checked-out branch ({1}) has no upstream tracking ref and the "
            "clone can name no remote default branch either (no "
            "refs/remotes/origin/HEAD, origin/main or origin/master), so there is "
            "no tip to bring it level with.\n"
            "  Fix: git -C {0} remote set-head origin --auto".format(repo_root, branch)
        )
    print(
        "[dest-refresh] {0}: {1} has no upstream; measuring against {2} "
        "(the remote's default branch)".format(repo_root, branch, base),
        file=out,
    )
    return base, None


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
            # Detached HEAD stays a refusal, and the asymmetry with the
            # no-upstream case below is the point: a round cannot tell which
            # branch it would land on, so there is no landing branch to
            # measure, let alone bring level.
            return RefreshResult(
                repo_root,
                ok=False,
                reason=(
                    "{0} is in detached HEAD -- a round cannot tell which branch it "
                    "would land on, so it cannot be brought level with origin "
                    "first".format(repo_root)
                ),
                branch=branch,
            )
        upstream, refusal = _no_upstream_base(repo_root, branch, out=out)
        if refusal is not None:
            return RefreshResult(repo_root, ok=False, reason=refusal, branch=branch)

    print(
        "[dest-refresh] {0}: fetching origin (landing branch {1})".format(repo_root, branch),
        file=out,
    )
    fetch = _git(repo_root, ["fetch", "--no-tags", "--prune", "origin"], remote=True)
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
                "side.\n"
                "  Fix: git -C {0} merge {2}   (or rebase, then re-run)".format(
                    repo_root, branch, upstream, ahead, behind
                )
            ),
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
        )

    fast_forwarded = False
    if behind:
        merge = _git(repo_root, ["merge", "--ff-only", upstream])
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
        # Same base substitution as `refresh_dest_from_origin`, for the same
        # reason: a branch with no upstream is checked against the remote's
        # DEFAULT branch, which is the tip a peer's landed work is on. Only a
        # clone that can name no remote branch at all is refused here.
        upstream, refusal = _no_upstream_base(repo_root, branch, out=out)
        if refusal is not None:
            return RefreshResult(repo_root, ok=False, reason=refusal, branch=branch)

    fetch = _git(repo_root, ["fetch", "--no-tags", "--prune", "origin"], remote=True)
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
    )
    if merge.returncode != 0:
        detail = _last_line(merge.stdout or merge.stderr, "merge failed")
        _git(repo_root, ["merge", "--abort"])
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
