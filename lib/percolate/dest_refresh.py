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
update here is fast-forward-only, with one exception narrow enough to name. A
landing branch that has diverged from its upstream is a human's call -- the
round refuses and says so, and no code path here can turn a divergence into a
silent overwrite. The one sanctioned abort outside a failed merge of our own is a
MERGE_HEAD whose message names this module's peer-merge of the upstream, left by
a killed round (`_recover_interrupted_op`); every other in-progress operation
is refused untouched. There is deliberately no override flag; a caller that wants
to publish from a stale clone has to make the clone not stale.

THE ONE RECONCILED DIVERGENCE: A SUBSUMED PEER PUBLISH. Two boxes publish the
same mirror; when box B publishes from source X and box A later merges X into
its own source, A's clone diverges from origin by B's publish commit -- whose
bytes A's source already carries. Nothing human-shaped remains to decide, yet
the refusal stranded every A publish until someone hand-merged a mirror the
`bump-foreign-repo-write` guard forbids touching. So when EVERY upstream-only
commit stamps a `[source-head <sha>]` that is an ancestor of the ref the round
publishes (`source_ref`, the `--source-ref` pin; HEAD when unpinned), the
branch records upstream as a parent with our tree kept (`merge -s ours`); the round then republishes the whole surface from a source
that contains B's. One unstamped commit, or one stamp the source cannot place
in its history, keeps the refusal.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TextIO

from coordinator_core.git.run import GitResult, run_git
from percolate.interrupted_op import (
    inspect_in_progress,
    is_own_peer_merge,
    peer_merge_message,
)
from percolate.peer_merge_regen import resolve_derived_after_merge

_SOURCE_HEAD_STAMP = re.compile(r"\[source-head ([0-9a-f]{7,40})\]")


@dataclass(frozen=True)
class RefreshResult:

    repo_root: Path
    ok: bool
    reason: str = ""
    branch: Optional[str] = None
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    fast_forwarded: bool = False
    warnings: tuple = ()
    dirty: bool = False


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


_ENDS_IN_PROGRESS = {
    "merge": "merge --abort",
    "cherry-pick": "cherry-pick --abort",
    "revert": "revert --abort",
    "rebase": "rebase --abort",
    "bisect": "bisect reset",
}


def _recover_interrupted_op(
    repo_root: Path, upstream: Optional[str], *, out: TextIO
) -> Optional[str]:
    """Round-start recovery: a refusal string, or None when the mirror is clear to use.

    The one sanctioned abort: a MERGE_HEAD whose MERGE_MSG is this module's own
    peer-merge of `upstream`, left by a round killed before its `merge --abort`.
    Any other in-progress operation is a human's and is refused untouched.
    """
    op = inspect_in_progress(repo_root)
    if op is None:
        return None
    if op.kind == "merge" and upstream and is_own_peer_merge(op.detail, upstream):
        abort = _git(repo_root, ["merge", "--abort"])
        if abort.returncode != 0:
            return (
                "{0} has an interrupted peer-merge of {1} that could not be aborted ({2})\n"
                "  Fix: git -C {0} merge --abort".format(
                    repo_root,
                    upstream,
                    _last_line(abort.stderr or abort.stdout, "merge --abort failed"),
                )
            )
        print(
            "[dest-refresh] {0}: aborted an interrupted peer-merge of {1} left by a "
            "killed round".format(repo_root, upstream),
            file=out,
        )
        return None
    return (
        "{0} has a {1} in progress ({2}); a round cannot run over it\n"
        "  Fix: git -C {0} {3}".format(
            repo_root,
            op.kind,
            op.detail or "no message",
            _ENDS_IN_PROGRESS.get(op.kind, "status"),
        )
    )


def _refresh_local_main(repo_root: Path, checked_out: Optional[str]) -> Optional[str]:
    if checked_out == "main":
        return None
    have_remote = _git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
    )
    if have_remote.returncode != 0:
        return None
    have_local = _git(
        repo_root,
        ["rev-parse", "--verify", "--quiet", "refs/heads/main"],
    )
    if have_local.returncode != 0:
        return None
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


def _subsumed_by_source(
    repo_root: Path, upstream: str, source_root: Optional[Path], source_ref: str
) -> Optional[List[str]]:
    """The upstream-only commits' source stamps when every one is already in
    `source_ref`'s history in `source_root`; `None` when any is not (or cannot be told)."""
    if source_root is None:
        return None
    log = _git(repo_root, ["log", "--format=%s", "HEAD.." + upstream])
    if log.returncode != 0:
        return None
    subjects = [line for line in log.stdout.splitlines() if line.strip()]
    stamps: List[str] = []
    for subject in subjects:
        match = _SOURCE_HEAD_STAMP.search(subject)
        if match is None:
            return None
        stamps.append(match.group(1))
    if not stamps:
        return None
    for stamp in stamps:
        probe = _git(Path(source_root), ["merge-base", "--is-ancestor", stamp, source_ref])
        if probe.returncode != 0:
            return None
    return stamps


def _stamps_missing_from_source(
    repo_root: Path, upstream: str, source_root: Optional[Path], source_ref: str
) -> List[str]:
    """Upstream-only `[source-head]` stamps the source ref in `source_root` does not contain.

    TRAP: a fast-forward over a peer's publish is not safe on its own. The round
    then writes this source's whole surface over the peer's bytes, so a source
    that lacks the peer's commits reverts them under a clean fast-forward.
    """
    if source_root is None:
        return []
    log = _git(repo_root, ["log", "--format=%s", "HEAD.." + upstream])
    if log.returncode != 0:
        return []
    missing: List[str] = []
    for match in _SOURCE_HEAD_STAMP.finditer(log.stdout):
        stamp = match.group(1)
        probe = _git(Path(source_root), ["merge-base", "--is-ancestor", stamp, source_ref])
        if probe.returncode != 0 and stamp not in missing:
            missing.append(stamp)
    return missing


def refresh_dest_from_origin(
    repo_root: Path,
    *,
    out: TextIO,
    err: TextIO,
    source_root: Optional[Path] = None,
    source_ref: str = "HEAD",
) -> RefreshResult:
    repo_root = Path(repo_root)
    branch, upstream, name_err = _branch_and_upstream(repo_root)
    if name_err is not None or upstream is None:
        if branch == "HEAD":
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

    stuck = _recover_interrupted_op(repo_root, upstream, out=out)
    if stuck is not None:
        return RefreshResult(repo_root, ok=False, reason=stuck, branch=branch, upstream=upstream)

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

    subsumed = _subsumed_by_source(repo_root, upstream, source_root, source_ref) if ahead and behind else None
    if subsumed is not None:
        merge = _git(
            repo_root,
            ["merge", "-s", "ours", "--no-edit", "-m", peer_merge_message(upstream, branch), upstream],
        )
        if merge.returncode != 0:
            _git(repo_root, ["merge", "--abort"])
            subsumed = None
        else:
            print(
                "[dest-refresh] {0}: {1} diverged from {2} only by peer publish(es) of "
                "source already merged here ({3}); recorded {2} as a parent, tree kept".format(
                    repo_root, branch, upstream, ", ".join(subsumed)
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

    missing = (
        _stamps_missing_from_source(repo_root, upstream, source_root, source_ref) if behind else []
    )
    if missing:
        return RefreshResult(
            repo_root,
            ok=False,
            reason=(
                "{0} carries a peer publish of source {1} that {3} in {2} does not contain; "
                "publishing now reverts it.\n"
                "  Fix: fetch and merge the branch holding {1} into {2}, then re-run; or, "
                "without touching the worktree, build a commit containing {1} "
                "(git merge-tree --write-tree + git commit-tree) and re-run with "
                "--source-ref <that commit>".format(
                    upstream, ", ".join(missing), source_root, source_ref
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


def fast_forward_consumer(repo_root: Path) -> RefreshResult:
    """Fetch, then fast-forward a clean mirror that is strictly behind its upstream.

    INVARIANT: a dirty or diverged checkout is reported, never merged; ahead-only is
    ok and left alone. After a fast-forward `behind` reads 0. Never raises.

    TRAP: do not route this through `refresh_dest_from_origin` -- its source-stamp
    refusal is publish semantics and would refuse exactly the stale-consumer case.
    A dirty tree still fetches and counts: a fetch never touches the worktree.
    """
    repo_root = Path(repo_root)
    try:
        branch, upstream, name_err = _branch_and_upstream(repo_root)
        if upstream is None or name_err is not None:
            reason = (
                "{0} is in detached HEAD".format(repo_root)
                if branch == "HEAD"
                else "{0}: {1}".format(repo_root, name_err or "no upstream tracking ref")
            )
            return RefreshResult(repo_root, ok=False, reason=reason, branch=branch)

        status = _git(repo_root, ["status", "--porcelain", "--untracked-files=no"])
        dirty_count = len([l for l in status.stdout.splitlines() if l.strip()])
        dirty = dirty_count > 0

        fetch = _git(repo_root, ["fetch", "--no-tags", "--prune", "origin"], remote=True)
        fetch_err = (
            None
            if fetch.returncode == 0
            else "could not fetch origin ({0})".format(_last_line(fetch.stderr, "git fetch failed"))
        )

        ahead, behind, count_err = _ahead_behind(repo_root, upstream)
        if ahead is None or behind is None:
            return RefreshResult(
                repo_root,
                ok=False,
                reason="could not measure against {0}: {1}{2}".format(
                    upstream, count_err, " ({0})".format(fetch_err) if fetch_err else ""
                ),
                branch=branch,
                upstream=upstream,
                dirty=dirty,
            )

        def result(ok: bool, reason: str = "", b: int = behind, ff: bool = False) -> RefreshResult:
            return RefreshResult(
                repo_root, ok=ok, reason=reason, branch=branch, upstream=upstream,
                ahead=ahead, behind=b, fast_forwarded=ff, dirty=dirty,
            )

        if fetch_err is not None:
            return result(False, fetch_err)
        if dirty:
            return result(False, "{0} has {1} modified tracked file(s); not merged".format(repo_root, dirty_count))
        if ahead and behind:
            return result(False, "{0}'s {1} has diverged from {2} ({3} ahead, {4} behind)".format(
                repo_root, branch, upstream, ahead, behind))
        if not behind:
            return result(True)
        merge = _git(repo_root, ["merge", "--ff-only", upstream])
        if merge.returncode != 0:
            return result(False, "could not fast-forward ({0})".format(
                _last_line(merge.stderr or merge.stdout, "ff-only merge failed")))
        return result(True, b=0, ff=True)
    except Exception as exc:  # contract: never raises
        return RefreshResult(repo_root, ok=False, reason="fast_forward_consumer failed: {0}".format(exc))


def reconcile_dest_before_push(repo_root: Path, *, out: TextIO, err: TextIO) -> RefreshResult:
    repo_root = Path(repo_root)
    branch, upstream, name_err = _branch_and_upstream(repo_root)
    if name_err is not None or upstream is None:
        upstream, refusal = _no_upstream_base(repo_root, branch, out=out)
        if refusal is not None:
            return RefreshResult(repo_root, ok=False, reason=refusal, branch=branch)

    stuck = _recover_interrupted_op(repo_root, upstream, out=out)
    if stuck is not None:
        return RefreshResult(repo_root, ok=False, reason=stuck, branch=branch, upstream=upstream)

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
    def refused(reason: str) -> RefreshResult:
        return RefreshResult(
            repo_root,
            ok=False,
            reason=reason,
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
        )

    regenerated: tuple = ()
    if not ahead:
        merge = _git(repo_root, ["merge", "--no-edit", upstream])
        if merge.returncode != 0:
            detail = _last_line(merge.stdout or merge.stderr, "merge failed")
            _git(repo_root, ["merge", "--abort"])
            return refused(
                "{0}'s {1} could not fast-forward to {2} ({3}); nothing was pushed".format(
                    repo_root, branch, upstream, detail
                )
            )
    else:
        merge = _git(
            repo_root,
            [
                "merge", "--no-commit", "--no-edit", "-m",
                peer_merge_message(upstream, branch), upstream,
            ],
        )
        if merge.returncode != 0 and inspect_in_progress(repo_root) is None:
            return refused(
                "git refused to start the peer merge of {0} into {1} in {2} ({3}); "
                "nothing was pushed".format(
                    upstream,
                    branch,
                    repo_root,
                    _last_line(merge.stderr or merge.stdout, "merge failed"),
                )
            )
        regen = resolve_derived_after_merge(repo_root, lambda a: _git(repo_root, a))
        if not regen.ok:
            _git(repo_root, ["merge", "--abort"])
            return refused(
                "{0}'s {1} and {2} both changed the same published paths and could not be "
                "merged ({3}); the merge was aborted and nothing was pushed -- resolving "
                "which box's source is right is a human's call".format(
                    repo_root,
                    branch,
                    upstream,
                    ", ".join(regen.unmerged_other) or _last_line(merge.stdout or merge.stderr, "merge failed"),
                )
            )
        commit = _git(repo_root, ["commit", "--no-edit"])
        if commit.returncode != 0:
            _git(repo_root, ["merge", "--abort"])
            return refused(
                "could not commit the peer merge of {0} into {1} in {2} ({3}); the merge "
                "was aborted and nothing was pushed".format(
                    upstream,
                    branch,
                    repo_root,
                    _last_line(commit.stderr or commit.stdout, "git commit failed"),
                )
            )
        regenerated = regen.regenerated

    print(
        "[dest-refresh] {0}: merged {1} ({2} peer commit(s)) into {3}{4}".format(
            repo_root,
            upstream,
            behind,
            branch,
            " (regenerated: {0})".format(", ".join(regenerated)) if regenerated else "",
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
