"""klabauter-reconcile.py — contain a diverged `main` back inside `candidate`
so `klabauter-promote.py`'s fast-forward predicate can hold again, doing the
merge in a THROWAWAY CLONE this module owns and always removes.

WHY A SEPARATE VERB. `klabauter-promote.py` refuses a non-fast-forward as a
HARD refusal and never synthesizes a merge commit (its predicate 3, and
docs/reference/klabauter-release-channels.md § "Promotion evidence bar").
That refusal is correct and stays: the byte-identity property the one-clone
topology depends on requires `main` to already be contained in `candidate`.
But nothing shipped could PRODUCE that containment once `main` had diverged —
observed 2026-09-06, when seven commits authored directly in the publish repo
(the 2026-09-05 Linux cloud dogfood, PR #5) left promotion permanently
refused with no tool able to clear it. This module is that missing producer.
It never promotes; it only makes promotion possible, and `klabauter-promote`
still owns the full evidence bar afterwards.

WHY A THROWAWAY CLONE, NOT THE MIRROR. The publish mirror is guarded against
foreign-repo writes (`bump-foreign-repo-write`), and a merge is exactly the
class of write that guard exists to stop: mirror-side authoring is what
produced the divergence in the first place. Reconciling in a disposable clone
of the REMOTE keeps the mirror read-only, and leaves the mirror's own refresh
(`lib/percolate/dest_refresh.py`, fast-forward-only) as the single way the
local clone ever moves.

THE CLONE IS ALWAYS REMOVED. A reconcile clone is pure scratch — every commit
it makes is pushed before it is torn down, and nothing else is ever written
into it. It is removed in a `finally`, on the success path and on every
failure alike, so a failed run cannot leave one behind; and any clone a
previous run leaked (a kill, a lost console) is swept at startup before this
run's own clone is made. Deletion is not a courtesy here: these are full
clones of a large repo in the system temp directory, and a leaked one is both
hundreds of MB and a stale copy of a public remote that no longer matches it.

Deletion is guarded, never unconditional — `_is_disposable_clone` refuses any
path that is not a git repository whose `origin` is the target's own remote,
that holds a commit no remote has, or that holds a stash. That is the same bar
the interactive `destructive-rm` guard states for removing a clone, enforced
here rather than asserted by an operator.

Negative-spec (do not restore any of this as a "fix"):
  - Does NOT push `main`, and does NOT promote — `klabauter-promote.py`
    remains the only verb that moves bits onto the consumer-facing branch,
    with its evidence bar intact.
  - Does NOT write to the publish mirror at all, not even a fetch.
  - Does NOT force, reset, or rebase; the only history it writes is one merge
    commit on `candidate`, pushed as a fast-forward of that branch.
  - Does NOT auto-resolve conflicts by default. `--take-candidate` is an
    explicit operator act, and even then it refuses on a conflicted path the
    published surface does not contain (a mirror-native file such as
    `.gitignore` has no source-side original to regenerate it from, so
    candidate's side is NOT authoritative for it).
  - Does NOT delete a directory it cannot prove is a disposable clone.

Usage:
    klabauter-reconcile.py <target> [--percolate-root <path>]
                                    [--take-candidate] [--confirm]
    klabauter-reconcile.py <target> --sweep <path>

Exit codes:
    0 — dry run reported a clean or resolvable reconcile (nothing pushed);
        `--confirm` pushed the merge; or `--sweep` removed the named clone.
    1 — the clone, merge, or push failed.
    2 — usage error, or refused (unresolvable target, conflicts without
        `--take-candidate`, a conflict outside the published surface, or a
        sweep path that is not a disposable clone).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_PERCOLATE_PUSH_PATH = _BIN_DIR / "percolate-push.py"

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2

#: Prefix every reconcile clone is created under, and the pattern the startup
#: sweep matches. Narrow on purpose: the sweep must never match a directory
#: this module did not create.
_CLONE_PREFIX = "klabauter-reconcile-"

_PERCOLATE_PUSH = None


def _percolate_push():
    """Load `percolate-push.py` under a private module name — the idiom
    `klabauter-promote.py::_load_percolate_push_module` already uses for this
    same sibling — lazily, so importing this file never executes that module's
    body on a warm server ~50 sessions share."""
    global _PERCOLATE_PUSH
    if _PERCOLATE_PUSH is None:
        spec = importlib.util.spec_from_file_location(
            "percolate_push_for_klabauter_reconcile", _PERCOLATE_PUSH_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _PERCOLATE_PUSH = module
    return _PERCOLATE_PUSH


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return _run(["git", "-C", str(repo), *args])


def _on_rm_error(func, path, exc):
    """`shutil.rmtree` error hook: git's object store is read-only on Windows,
    which makes `unlink` raise `PermissionError` on files that are genuinely
    ours to remove. Clear the read-only bit and retry once."""
    del exc
    Path(path).chmod(stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    """`shutil.rmtree` with the read-only retry hook, under whichever keyword
    the running interpreter accepts. `onerror` is deprecated from 3.12 and
    `onexc` does not exist before it, so the repo's 3.11+ floor needs both."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=_on_rm_error)


def _is_disposable_clone(path: Path, remote_url: Optional[str]) -> Optional[str]:
    """Return None if `path` is safe to delete, else the sentence saying why
    it is not.

    Every predicate fails CLOSED: a git command that does not run at all
    leaves the directory in place. The bar is the one the interactive
    `destructive-rm` guard names for removing a clone — a git root, fully
    pushed, no stashes — plus an identity check that the clone is of the
    target's own remote, so a mistyped path cannot reach an unrelated repo.
    """
    if not path.is_dir():
        return "'{}' is not a directory".format(path)

    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return "'{}' is not a git repository".format(path)
    if Path(top.stdout.strip()).resolve() != path.resolve():
        return "'{}' is not the ROOT of its git repository ({})".format(
            path, top.stdout.strip()
        )

    if remote_url:
        origin = _git(path, "remote", "get-url", "origin")
        if origin.returncode != 0:
            return "'{}' has no 'origin' remote to identify it by".format(path)
        if origin.stdout.strip().rstrip("/") != remote_url.rstrip("/"):
            return (
                "'{}' is a clone of {}, not of {} — refusing to delete a clone "
                "of another repo".format(path, origin.stdout.strip(), remote_url)
            )

    unpushed = _git(path, "log", "--branches", "--not", "--remotes", "--oneline")
    if unpushed.returncode != 0:
        return "'{}': could not prove every commit is pushed".format(path)
    if unpushed.stdout.strip():
        count = len(unpushed.stdout.strip().splitlines())
        return "'{}' holds {} commit(s) no remote has".format(path, count)

    stashes = _git(path, "stash", "list")
    if stashes.returncode != 0:
        return "'{}': could not read the stash list".format(path)
    if stashes.stdout.strip():
        count = len(stashes.stdout.strip().splitlines())
        return "'{}' holds {} stash(es)".format(path, count)

    return None


def _remove_clone(path: Path, remote_url: Optional[str], label: str) -> bool:
    refusal = _is_disposable_clone(path, remote_url)
    if refusal is not None:
        print(
            "klabauter-reconcile: NOT removing {} — {}".format(label, refusal),
            file=sys.stderr,
        )
        return False
    _rmtree(path)
    print("klabauter-reconcile: removed {} ({})".format(label, path))
    return True


def _sweep_orphans(scratch_root: Path, remote_url: Optional[str]) -> None:
    """Remove reconcile clones a previous run leaked. A run killed outright
    never reaches its own `finally`, so without this a leak is permanent and
    silent."""
    for leftover in sorted(scratch_root.glob(_CLONE_PREFIX + "*")):
        if leftover.is_dir():
            _remove_clone(leftover, remote_url, "orphaned reconcile clone")


def _remote_url(dest: str) -> Optional[str]:
    result = _run(["git", "-C", dest, "remote", "get-url", "origin"])
    return result.stdout.strip() if result.returncode == 0 else None


def _published_paths(dest: str) -> Optional[Set[str]]:
    """The repo-relative paths the percolate rounds actually write, read from
    the mirror's own round manifest.

    A conflicted path INSIDE this set is regenerated from claude-klabauter source every
    round, so the channel's side is authoritative and taking it loses nothing.
    A conflicted path OUTSIDE it is mirror-native (`.gitignore` is the live
    example) and has no source-side original — resolving that toward the
    channel would silently delete content nothing rebuilds, so it is refused.
    Returns None when the manifest cannot be read, which refuses every
    auto-resolution rather than guessing.
    """
    manifest = Path(dest) / ".percolate" / "round-manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    paths: Set[str] = set()

    def _walk(node) -> None:
        if isinstance(node, str):
            paths.add(node.replace("\\", "/").lstrip("./"))
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value)

    _walk(data)
    return paths


def _conflicted(repo: Path) -> List[str]:
    result = _git(repo, "diff", "--name-only", "--diff-filter=U")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _reconcile(
    clone: Path,
    channel: str,
    main_branch: str,
    take_candidate: bool,
    published: Optional[Set[str]],
) -> Tuple[int, bool]:
    """Merge `origin/<main_branch>` into `<channel>` inside `clone`.

    Returns `(exit_code, merged)`. `merged` is False when the branches were
    already contained, which is a success with nothing to push.
    """
    contained = _git(
        clone,
        "merge-base",
        "--is-ancestor",
        "origin/" + main_branch,
        "origin/" + channel,
    )
    if contained.returncode == 0:
        print(
            "klabauter-reconcile: '{}' is already an ancestor of '{}' — nothing "
            "to reconcile.".format(main_branch, channel)
        )
        return _EXIT_OK, False

    checkout = _git(clone, "checkout", channel)
    if checkout.returncode != 0:
        print(
            "klabauter-reconcile: could not check out '{}':".format(channel),
            file=sys.stderr,
        )
        print(checkout.stderr.strip(), file=sys.stderr)
        return _EXIT_FAIL, False

    message = (
        "reconcile: contain '{main}' in '{channel}' so promotion fast-forwards\n"
        "\n"
        "'{main}' carried commits authored directly in the publish repo that\n"
        "'{channel}' had never seen, so klabauter-promote.py's fast-forward\n"
        "predicate could not hold. Written by klabauter-reconcile.py in a\n"
        "throwaway clone.\n"
    ).format(main=main_branch, channel=channel)

    merge = _git(clone, "merge", "--no-ff", "origin/" + main_branch, "-m", message)
    if merge.returncode == 0:
        print("klabauter-reconcile: merged cleanly into '{}'.".format(channel))
        return _EXIT_OK, True

    conflicts = _conflicted(clone)
    if not conflicts:
        print("klabauter-reconcile: merge failed with no conflicted paths:", file=sys.stderr)
        print(merge.stderr.strip() or merge.stdout.strip(), file=sys.stderr)
        return _EXIT_FAIL, False

    print("klabauter-reconcile: {} conflicted path(s):".format(len(conflicts)))
    for path in conflicts:
        print("  " + path)

    if not take_candidate:
        print(
            "klabauter-reconcile: refusing — pass --take-candidate to resolve every\n"
            "  conflict above toward the channel side (the percolate-generated\n"
            "  output, regenerated from claude-klabauter source next round).",
            file=sys.stderr,
        )
        return _EXIT_USAGE, False

    if published is None:
        print(
            "klabauter-reconcile: refusing — could not read the mirror's round\n"
            "  manifest, so nothing proves these paths are percolate-generated.",
            file=sys.stderr,
        )
        return _EXIT_USAGE, False

    outside = [path for path in conflicts if path not in published]
    if outside:
        print(
            "klabauter-reconcile: refusing — these conflicted path(s) are NOT in the\n"
            "  published surface, so the channel's side is not authoritative for them\n"
            "  and taking it would delete mirror-native content nothing rebuilds:",
            file=sys.stderr,
        )
        for path in outside:
            print("    " + path, file=sys.stderr)
        return _EXIT_USAGE, False

    resolved = _git(clone, "checkout", "--ours", "--", *conflicts)
    if resolved.returncode != 0:
        print("klabauter-reconcile: could not take the channel side:", file=sys.stderr)
        print(resolved.stderr.strip(), file=sys.stderr)
        return _EXIT_FAIL, False

    staged = _git(clone, "add", "--", *conflicts)
    if staged.returncode != 0:
        print("klabauter-reconcile: could not stage the resolutions:", file=sys.stderr)
        print(staged.stderr.strip(), file=sys.stderr)
        return _EXIT_FAIL, False

    concluded = _git(clone, "commit", "--no-edit")
    if concluded.returncode != 0:
        print("klabauter-reconcile: could not conclude the merge:", file=sys.stderr)
        print(concluded.stderr.strip(), file=sys.stderr)
        return _EXIT_FAIL, False

    print(
        "klabauter-reconcile: resolved {} conflict(s) toward '{}' and concluded "
        "the merge.".format(len(conflicts), channel)
    )
    return _EXIT_OK, True


def _cmd_reconcile(args: argparse.Namespace) -> int:
    push = _percolate_push()

    percolate_root = push._resolve_percolate_root(args.percolate_root)
    if not percolate_root:
        return _EXIT_USAGE

    dest = push._resolve_dest(args.target, percolate_root)
    if not dest:
        print(
            "klabauter-reconcile: could not resolve a mirror for '{}'.".format(args.target),
            file=sys.stderr,
        )
        return _EXIT_USAGE

    remote_url = _remote_url(dest)
    if not remote_url:
        print(
            "klabauter-reconcile: '{}' has no 'origin' remote to clone from.".format(dest),
            file=sys.stderr,
        )
        return _EXIT_USAGE

    if args.sweep:
        swept = Path(args.sweep).resolve()
        return _EXIT_OK if _remove_clone(swept, remote_url, "clone") else _EXIT_USAGE

    main_branch, err = push._resolve_default_branch(dest)
    if not main_branch:
        print("klabauter-reconcile: {}".format(err), file=sys.stderr)
        return _EXIT_FAIL

    channel = args.channel
    scratch_root = Path(args.scratch_root) if args.scratch_root else Path(tempfile.gettempdir())
    _sweep_orphans(scratch_root, remote_url)

    clone = Path(tempfile.mkdtemp(prefix=_CLONE_PREFIX, dir=str(scratch_root)))
    try:
        cloned = _run(["git", "clone", "--quiet", remote_url, str(clone)])
        if cloned.returncode != 0:
            print("klabauter-reconcile: clone failed:", file=sys.stderr)
            print(cloned.stderr.strip(), file=sys.stderr)
            return _EXIT_FAIL

        code, merged = _reconcile(
            clone, channel, main_branch, args.take_candidate, _published_paths(dest)
        )
        if code != _EXIT_OK or not merged:
            return code

        if not args.confirm:
            print(
                "klabauter-reconcile: dry run — nothing pushed. Re-run with --confirm\n"
                "  to push the reconciled '{}'. Promotion stays a separate act:\n"
                "  klabauter-promote.py {} --confirm".format(channel, args.target)
            )
            return _EXIT_OK

        pushed = _git(clone, "push", "origin", channel)
        if pushed.returncode != 0:
            print("klabauter-reconcile: push failed:", file=sys.stderr)
            print(pushed.stderr.strip(), file=sys.stderr)
            return _EXIT_FAIL

        print("klabauter-reconcile: pushed '{}'.".format(channel))
        print(
            "klabauter-reconcile: '{}' is now contained in '{}'. Promote with: "
            "klabauter-promote.py {} --confirm".format(main_branch, channel, args.target)
        )
        return _EXIT_OK
    finally:
        _remove_clone(clone, remote_url, "reconcile clone")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klabauter-reconcile",
        description=(
            "Contain a diverged default branch back inside the release channel, in a "
            "throwaway clone that is always removed. Never promotes."
        ),
    )
    parser.add_argument("target", help="Single registered percolate target name.")
    parser.add_argument(
        "--percolate-root",
        help="Override PERCOLATE_ROOT (default: percolate-gate.py resolve-root).",
    )
    parser.add_argument(
        "--channel",
        default="candidate",
        help="Release-channel branch to reconcile into (default: candidate).",
    )
    parser.add_argument(
        "--scratch-root",
        help="Directory the throwaway clone is made under (default: system temp).",
    )
    parser.add_argument(
        "--take-candidate",
        action="store_true",
        help=(
            "Resolve conflicts toward the channel side. Refused for any conflicted "
            "path outside the published surface."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Push the reconciled channel branch. Without it, nothing is pushed.",
    )
    parser.add_argument(
        "--sweep",
        metavar="PATH",
        help=(
            "Remove one leftover clone at PATH instead of reconciling. Refuses "
            "unless it is a fully-pushed, stash-free clone of the target's remote."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return _cmd_reconcile(args)


if __name__ == "__main__":
    sys.exit(main())
