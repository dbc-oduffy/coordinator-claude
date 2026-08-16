"""klabauter-channel.py — move a consumer clone's checked-out ref between
the two klabauter release channels (`main`, `candidate`); or, bare, report
which channel the box is actually on versus what it declares.

Spec backlink: docs/plans/2026-08-16-one-engine-for-the-whole-box.md, chunk
C8's addendum (AC8 — "a user can move their box to the other target through
a documented, runnable path"). Policy doc:
docs/reference/klabauter-release-channels.md.

WHAT THIS IS, AND ISN'T. `klabauter-promote.py` (a sibling verb) is
PUBLISHER-side: it changes what `main` *contains*. This verb is CONSUMER-
side: it changes which ref a *box's own clone* is checked out on. Neither
verb writes `engine.target` or `track_ref` — this script moves a tree and
reports; the installer (C8's own scope) owns declaring a box's intent.

Default invocation REPORTS; it never mutates. It prints:
  - the resolved tree at `repos.claude_klabauter`,
  - the ref that tree is actually checked out on,
  - the channel the box DECLARES via `engine.target`
    (`coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py::resolve_engine_target`,
    imported — never reimplemented), and
  - whether those agree. An absent `engine.target` is the not-yet-rolled-out
    state (AC20) and is reported as such, never as a mismatch.

Mutation requires `--set <main|candidate>` and refuses, loudly and without
partial effect, when:
  - `repos.claude_klabauter` is unset, or does not resolve to a directory
    that is a git repository;
  - the target tree has uncommitted changes or untracked files;
  - the requested branch does not exist on the remote;
  - the target tree IS the operator's own publish mirror
    (`publish.mirrors.claude_klabauter.path`) AND `--set` contradicts what
    `publish.mirrors.claude_klabauter.track_ref` already declares (Finding
    3, staff-eng C8 review: narrowed from tree-IDENTITY to intent-
    CONFLICT). `--set <declared>` on a publish mirror is reconciliation
    with the declaration and PROCEEDS — moving a mirror onto the branch it
    already declares cannot break a publish round; it is the only thing
    that repairs one. Only a contradicting `--set` refuses, and only then
    is naming `track_ref` as the lever true.

Every refusal states one fact and one terse alternative — register, not
prose (docs/wiki/guard-messaging.md § Register): no self-legitimacy, no
repetition, no reassurance, no apology, never the override key.

Negative-spec (do not restore any of this as a "fix"):
  - Does NOT write `engine.target` or `publish.mirrors.claude_klabauter.track_ref`
    — the installer owns those writes; this verb moves a tree and reports.
  - Does NOT introduce a per-channel mirror root
    (`repos.claude_klabauter_main` / `_candidate`) — considered and declined
    for this plan; see C8's negative spec.
  - Does NOT infer a channel from whatever is checked out when declaring —
    `resolve_engine_target` is the only source of the declared value.

Usage:
    klabauter-channel.py [--set <main|candidate>]

Exit codes:
    0  — report succeeded, or `--set` moved the tree successfully.
    1  — `--set` and the git fetch/checkout itself failed (forwarded
         failure, nothing refused up front).
    2  — usage refusal: `repos.claude_klabauter` unset, or does not resolve
         to a directory that is a git repository.
    3  — refused: target tree has uncommitted changes or untracked files.
    4  — refused: requested branch does not exist on the remote.
    5  — refused: target tree is the operator's own publish mirror.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
_REPO_ROOT = _BIN_DIR.parent.parent
_RESOLVE_CLAUDE_KLABAUTER_DIR = _REPO_ROOT / "coordinator" / "lib" / "resolve-claude-klabauter"

for _p in (str(_LIB_DIR), str(_RESOLVE_CLAUDE_KLABAUTER_DIR), str(_BIN_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Review: staff-eng 2026-08-16 C8 Finding 7 — `coordinator_core` is only importable
# below because it happens to be reachable from an ambient site entry on
# this box -- verified false in general (a foreign cwd, or an exec through
# `_resolve_claude_klabauter.exec_cli` into a published mirror, would not carry it).
# `publish.py` already inserts `_REPO_ROOT` for the same reason; mirror it.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cli_shared  # noqa: E402
import _resolve_claude_klabauter  # noqa: E402

from coordinator_core.machine_resolver import registry_get  # noqa: E402
from coordinator_core.win_portability import same_path  # noqa: E402

_EXIT_OK = 0
_EXIT_GIT_OP_FAILED = 1
_EXIT_USAGE = 2
_EXIT_DIRTY_TREE = 3
_EXIT_BRANCH_NOT_ON_REMOTE = 4
_EXIT_IS_PUBLISH_MIRROR = 5

_REPOS_KEY = "repos.claude_klabauter"
_PUBLISH_MIRROR_PATH_KEY = "publish.mirrors.claude_klabauter.path"
_TRACK_REF_KEY = "publish.mirrors.claude_klabauter.track_ref"


def _run(cmd, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def _resolve_tree() -> Optional[str]:
    """`repos.claude_klabauter`, or `None` if unset."""
    return cli_shared.machine_local_get(_REPOS_KEY)


def _is_git_repo(tree: str) -> bool:
    result = _run(["git", "-C", tree, "rev-parse", "--git-dir"])
    return result.returncode == 0


def _current_ref(tree: str) -> Optional[str]:
    """The tree's actual checked-out ref: the branch name, or a short sha
    on detached HEAD. `None` if it could not be determined."""
    branch = _run(["git", "-C", tree, "symbolic-ref", "--short", "-q", "HEAD"])
    if branch.returncode == 0 and branch.stdout.strip():
        return branch.stdout.strip()
    sha = _run(["git", "-C", tree, "rev-parse", "--short", "HEAD"])
    if sha.returncode == 0 and sha.stdout.strip():
        return sha.stdout.strip() + " (detached)"
    return None


def _dirty_refusal(tree: str) -> Optional[str]:
    """`None` when the tree is clean; a refusal message otherwise. Fails
    CLOSED: a non-zero `git status` refuses rather than being read as
    clean."""
    result = _run(
        ["git", "-C", tree, "--no-optional-locks", "status", "--porcelain=v2", "--untracked-files=normal"]
    )
    if result.returncode != 0:
        return (
            f"klabauter-channel: could not read status of {tree} — refusing to move it.\n"
            + result.stderr.strip()
        )
    dirty_lines = [ln for ln in result.stdout.splitlines() if ln and not ln.startswith("#")]
    if dirty_lines:
        return (
            f"klabauter-channel: {tree} has {len(dirty_lines)} uncommitted path(s) — "
            "refusing to move a dirty tree. Commit or discard the changes first."
        )
    return None


def _branch_exists_on_remote(tree: str, branch: str) -> bool:
    result = _run(["git", "-C", tree, "ls-remote", "--exit-code", "--heads", "origin", branch])
    return result.returncode == 0 and bool(result.stdout.strip())


def _is_publish_mirror(tree: str) -> bool:
    # Review: staff-eng 2026-08-16 C8 Finding 9 — in-process, matching the doctor
    # probe added in this same chunk -- Finding 7's sys.path insert makes
    # coordinator_core importable, so the CLI shell-out this replaced was
    # an added process spawn for no reason (machine load norm:
    # docs/wiki/machine-load-norm.md).
    mirror_path = registry_get(_PUBLISH_MIRROR_PATH_KEY)
    if not mirror_path:
        return False
    return same_path(tree, mirror_path)


def _declared_track_ref_branch() -> Optional[str]:
    """The local branch `_expected_local_branch` derives from the declared
    `publish.mirrors.claude_klabauter.track_ref`, or `None` if undeclared."""
    from publish import _expected_local_branch  # noqa: PLC0415 -- see Finding 3 below

    track_ref = registry_get(_TRACK_REF_KEY)
    if not track_ref:
        return None
    return _expected_local_branch(track_ref)


def _cmd_report(args: argparse.Namespace) -> int:
    tree = _resolve_tree()
    declared = _resolve_claude_klabauter.resolve_engine_target()

    print(f"klabauter-channel: {_REPOS_KEY} = {tree!r}")

    if not tree:
        print(
            "klabauter-channel: no tree registered — nothing to report on. "
            f"Register one with `machine-local set {_REPOS_KEY} <path>`."
        )
        return _EXIT_OK

    if not Path(tree).is_dir() or not _is_git_repo(tree):
        print(
            f"klabauter-channel: {tree!r} does not resolve to a directory that is a "
            "git repository — nothing further to report."
        )
        return _EXIT_OK

    actual = _current_ref(tree)
    print(f"klabauter-channel: actual ref = {actual!r}")

    if declared is None:
        print(
            "klabauter-channel: engine.target is absent — not-yet-rolled-out "
            "(AC20: absence never diverts and is never read as a mismatch)."
        )
        return _EXIT_OK

    print(f"klabauter-channel: declared engine.target = {declared!r}")
    if actual == declared:
        print(f"klabauter-channel: agrees — the box is on {declared!r}.")
    else:
        # Review: staff-eng 2026-08-16 C8 Finding 4 — fold Finding 3's narrowed
        # predicate into the recommendation too. On a publish mirror,
        # `--set <declared>` is only permitted when it agrees with
        # `track_ref` -- recommend it only then; otherwise name the
        # track_ref lever instead of pointing at a command that refuses.
        if _is_publish_mirror(tree) and _declared_track_ref_branch() != declared:
            print(
                f"klabauter-channel: MISMATCH — declared {declared!r}, actual "
                f"{actual!r}. This tree is the publish mirror; its branch is "
                f"set by {_TRACK_REF_KEY}, not by --set."
            )
        else:
            print(
                f"klabauter-channel: MISMATCH — declared {declared!r}, actual "
                f"{actual!r}. Move it with `klabauter-channel --set {declared}`."
            )
    return _EXIT_OK


def _refuse(code: int, message: str) -> int:
    print(message, file=sys.stderr)
    return code


def _cmd_set(args: argparse.Namespace) -> int:
    target = args.set

    tree = _resolve_tree()
    if not tree:
        return _refuse(
            _EXIT_USAGE,
            f"klabauter-channel: {_REPOS_KEY} is unset — nothing to move. "
            f"Register a tree with `machine-local set {_REPOS_KEY} <path>` first.",
        )
    if not Path(tree).is_dir() or not _is_git_repo(tree):
        return _refuse(
            _EXIT_USAGE,
            f"klabauter-channel: {tree!r} does not resolve to a directory that is a "
            "git repository — refusing to move it.",
        )

    dirty_refusal = _dirty_refusal(tree)
    if dirty_refusal:
        return _refuse(_EXIT_DIRTY_TREE, dirty_refusal)

    # Review: staff-eng 2026-08-16 C8 Finding 3 — narrowed from tree-IDENTITY to
    # intent-CONFLICT. On a normal claude-klabauter developer box the discovered
    # `repos.claude_klabauter` IS the publish mirror, so a blanket refusal
    # here had zero mutating capability on the only box class that can
    # reach this path. `--set X` that agrees with the declared `track_ref`
    # is reconciliation -- the case this verb exists for -- and proceeds;
    # only a `--set X` that CONTRADICTS the declaration refuses, at which
    # point naming `track_ref` as the lever is finally true.
    if _is_publish_mirror(tree):
        declared_branch = _declared_track_ref_branch()
        if declared_branch != target:
            return _refuse(
                _EXIT_IS_PUBLISH_MIRROR,
                f"klabauter-channel: {tree!r} is this box's publish mirror "
                f"({_PUBLISH_MIRROR_PATH_KEY}). Its branch is set by "
                f"{_TRACK_REF_KEY}; change that key instead.",
            )

    if not _branch_exists_on_remote(tree, target):
        return _refuse(
            _EXIT_BRANCH_NOT_ON_REMOTE,
            f"klabauter-channel: branch {target!r} does not exist on {tree!r}'s "
            "origin remote — refusing to move it.",
        )

    fetch = _run(["git", "-C", tree, "fetch", "origin", target])
    if fetch.returncode != 0:
        print(
            f"klabauter-channel: `git fetch origin {target}` failed in {tree!r}:\n"
            + fetch.stderr.strip(),
            file=sys.stderr,
        )
        return _EXIT_GIT_OP_FAILED

    checkout = _run(
        ["git", "-C", tree, "checkout", "-B", target, "--track", f"origin/{target}"]
    )
    if checkout.returncode != 0:
        print(
            f"klabauter-channel: `git checkout -B {target} --track origin/{target}` "
            f"failed in {tree!r}:\n" + checkout.stderr.strip(),
            file=sys.stderr,
        )
        return _EXIT_GIT_OP_FAILED

    print(f"klabauter-channel: moved {tree!r} onto {target!r}.")
    return _EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klabauter-channel",
        description=(
            "Report, or move, which klabauter release channel this box's consumer "
            "clone is checked out on. Bare invocation reports and never mutates."
        ),
    )
    parser.add_argument(
        "--set",
        choices=(_resolve_claude_klabauter.ENGINE_TARGET_MAIN, _resolve_claude_klabauter.ENGINE_TARGET_CANDIDATE),
        default=None,
        help="Move the tree at repos.claude_klabauter onto this branch.",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.set:
        return _cmd_set(args)
    return _cmd_report(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
