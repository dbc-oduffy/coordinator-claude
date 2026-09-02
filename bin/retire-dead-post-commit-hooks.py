#!/usr/bin/env python3
"""Remove the retired `coordinator-auto-push` post-commit hook from every
registered repo on this machine.

C8 of `docs/plans/2026-08-30-who-pushes-and-when.md` gravestoned the
per-commit auto-push machinery: `coordinator/bin/coordinator-auto-push.py`
was deleted at `124e2c5c5c` and the job moved to
`coordinator_core/warm/push_cadence.py`. `ensure_post_commit_hook` -- the
only code that could ever rewrite an installed `.git/hooks/post-commit`
body -- was deleted in the same sweep, before any session ran it. The
`_HOOK_GEN_STAMP` bump to 11 that was meant to force one fleet rewrite pass
therefore can never be honoured: nothing left in this engine reaches those
bodies. See `coordinator/bin/lib/git_hook_install.py`'s gravestone above
`ensure_prepare_commit_msg_hook` for the census that established this.

What the orphaned bodies do until removed: their SCRIPT cascade probes the
deleted helper in the working tree (miss), then settles on
`${COORDINATOR_SETTINGS_HOME}/bin/coordinator-auto-push`, a generated
forwarder that outlived its target. A present forwarder is indistinguishable
from a working helper at a `[ -f ]` probe, so the cascade never reaches its
own clean "not found -> warn and exit 0" terminal rung; it execs the
forwarder, which exits 127 naming a repair route that cannot work. Confirmed
live from example-cockpit-repo 2026-09-01 and again 2026-09-02.

This is the runnable cold-path remediation for that residual (CLAUDE.md
"Cold-path remediation names a runnable script"): what fires before a
session exists cannot be repaired by a slash command. The forwarder half is
retired separately, by `install.substrate._KILLED_OP_ORPHAN_NAMES` on the
next `scripts/setup.py` run.

Negative spec -- what this deliberately does NOT do:

- Does not run as part of any install, self-heal, or session-boot path. A
  repo's `.git/hooks` is that repo's own local state, and this box runs ~50
  concurrent sessions; rewriting a peer's hooks unasked, mid-commit, is the
  change `git_hook_install`'s gravestone declined to make. Operator-invoked,
  by name, once.
- Does not touch `prepare-commit-msg`. The Session-Id trailer is a live
  hook installed by a different function that was not retired.
- Does not guess. A `post-commit` this cannot positively identify as the
  retired generator's output is reported and left byte-identical.
- Does not destroy what it cannot put back. `ensure_post_commit_hook` is
  gone, so no surviving code can regenerate a body this removes; every
  removal therefore writes the original bytes to `post-commit.retired`
  beside it first, which keeps this an undoable action (`mv` it back) rather
  than a one-way one. `.git/hooks` is untracked, so the copy costs nothing
  downstream.
- Does not spawn a process. Repo enumeration reads the machine registry
  directly (`git_hook_install._registry_repo_roots`, zero-spawn) and the
  rest is file I/O -- no `git`, no shell.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# This script lives at `<engine-root>/coordinator/bin/`, so both paths are
# structural, not resolved: `lib/` for the hook module itself and the engine
# root for the `coordinator_core` imports that module makes at import time.
_HERE = Path(__file__).resolve()
for _p in (_HERE.parent / "lib", _HERE.parents[2]):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import git_hook_install  # noqa: E402

#: The retired hook's own label, as `ensure_post_commit_hook` passed it to
#: `_append_markers` before that function was deleted. Carried here as a
#: literal because the deletion took the constant with it: an appended block
#: on disk is bounded by markers derived from this exact string, and the two
#: cannot be re-derived from any surviving call site.
_RETIRED_HEADER = "coordinator auto-push (crash insurance)"

#: First comment line of every fresh body the generator ever wrote. Positive
#: identification, never "mentions auto-push therefore ours" -- a foreign
#: hook is free to mention the name.
_FRESH_MARKER = "# coordinator coordinator-auto-push hook — installed by git_hook_install."

#: Last executable line of a fresh body. Checked together with the header so
#: a truncated or hand-edited body fails identification rather than being
#: deleted on the strength of a comment alone.
_FRESH_TAIL = 'exec "$_PY" "$SCRIPT" "$@"'

#: Where a removed body is preserved. A sibling of the hook it came from, so
#: the undo is a rename in place with no path to reconstruct.
_BACKUP_SUFFIX = ".retired"

GENERATES = []  # every write (_retire_one's backup + excise/unlink) targets <repo>/.git/hooks/post-commit and its .retired sibling, in each registered repo's own untracked .git dir -- never a fixed artifact tracked in this repo


def _hooks_dir(root: Path) -> "Path | None":
    """The `hooks/` directory governing `root`, or None if this is not a
    git worktree.

    A linked worktree's `.git` is a file naming a gitdir whose `commondir`
    points at the main repository; hooks live in the common dir, not the
    per-worktree one, so a naive `<gitdir>/hooks` would silently miss on
    every worktree. Resolved rather than skipped because `EnterWorktree`
    sessions are ordinary on this box.
    """
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git / "hooks"
    if not dot_git.is_file():
        return None
    try:
        line = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = Path(line.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (root / gitdir).resolve()
    commondir = gitdir / "commondir"
    if commondir.is_file():
        try:
            rel = commondir.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        common = Path(rel)
        gitdir = common if common.is_absolute() else (gitdir / common).resolve()
    return gitdir / "hooks"


def _classify(text: str):
    """`("fresh", None)`, `("appended", (start, end))`, or `(None, None)`.

    The two shapes the generator could produce are the only two this acts
    on. Everything else -- including a body that merely mentions the retired
    helper -- classifies as unidentified, which the caller reports and leaves
    alone.
    """
    start_marker, end_marker = git_hook_install._append_markers(_RETIRED_HEADER)
    extent = git_hook_install._block_extent(text, start_marker, end_marker)
    if extent is not None:
        return "appended", extent
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None, None
    if git_hook_install._has_line(text, _FRESH_MARKER) and lines[-1].strip() == _FRESH_TAIL:
        return "fresh", None
    return None, None


def _excise(text: str, start: int, end: int) -> str:
    """Drop lines [start, end] inclusive, preserving the foreign hook's own
    trailing newline convention."""
    lines = text.splitlines(keepends=True)
    remaining = lines[:start] + lines[end + 1:]
    return "".join(remaining)


def _retire_one(root: Path, apply: bool) -> str:
    hooks = _hooks_dir(root)
    if hooks is None:
        return "skipped-not-a-worktree"
    hook = hooks / "post-commit"
    if not hook.is_file():
        return "absent"
    try:
        text = hook.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "unreadable"
    shape, extent = _classify(text)
    if shape is None or (shape == "appended" and extent is None):
        return "unidentified-left-alone"
    if apply:
        backup = hook.with_name(hook.name + _BACKUP_SUFFIX)
        try:
            backup.write_text(text, encoding="utf-8")
        except OSError as exc:
            # The undo leg is the reason this removal is allowed to happen
            # at all; without it the action is one-way. Refuse rather than
            # proceed unbacked.
            print(f"[retire-post-commit] REFUSED {root}: cannot write {backup}: {exc}",
                  file=sys.stderr)
            return "refused-no-backup"
    if shape == "fresh":
        if apply:
            hook.unlink()
        return "removed" if apply else "would-remove"
    assert extent is not None
    remainder = _excise(text, extent[0], extent[1])
    if apply:
        hook.write_text(remainder, encoding="utf-8")
    return "block-excised" if apply else "would-excise-block"


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument(
        "--apply", action="store_true",
        help="perform the removals; without it every repo is only classified",
    )
    ap.add_argument(
        "--repo", action="append", default=[], metavar="PATH",
        help="a repo root to act on (repeatable); default is every repos.* entry "
             "in the machine registry",
    )
    args = ap.parse_args(argv)

    if args.repo:
        targets = [(p, p) for p in args.repo]
    else:
        targets = git_hook_install._registry_repo_roots("")
    if not targets:
        print("[retire-post-commit] no registered repos found — nothing to do")
        return 0

    counts: "dict[str, int]" = {}
    for key, path in sorted(targets, key=lambda kv: kv[1]):
        outcome = _retire_one(Path(path), args.apply)
        counts[outcome] = counts.get(outcome, 0) + 1
        print(f"[retire-post-commit] {outcome:<24} {path}  ({key})")

    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"[retire-post-commit] {len(targets)} repo(s): {summary}")
    if not args.apply and (counts.get("would-remove") or counts.get("would-excise-block")):
        print("[retire-post-commit] re-run with --apply to perform these removals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
