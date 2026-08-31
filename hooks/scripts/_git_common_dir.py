"""_git_common_dir -- stdlib-only, zero-spawn git COMMON-dir resolution primitive for hook consumers.

Purpose: nine hook-script copies of the same `_resolve_git_common_dir(git_root) -> str`
helper (plus two Path-typed callers that wrap it with their own git-root walk) were hand-synced
by docstring cross-reference back to a nominated canonical copy in
`offer-exploration-tier-dispatch.py`. A test
(`coordinator/tests/test_resolve_git_common_dir_worktree_portability.py`) asserted every copy
was a byte-identical local `FunctionDef` -- catching divergence, but only by enforcing the
duplication it should have eliminated. This module is the single definition site; the nine
callers (`_foreground_dispatch_strip.py`, `nudge-foreground-agent-dispatch.py`,
`nudge-multiwave-workflow.py`, `observe-config-change.py`, `observe-post-compact.py`,
`offer-exploration-tier-dispatch.py`, `runtime-tripwire-em-check.py`,
`runtime-tripwire-stop-watcher.py`, `subagent-zero-tool-use-detect.py`) import it instead of
carrying their own copy.

`_`-prefixed module name, unprefixed function name -- matches the `_git_root_walk.py` /
`git_root_walk()` sibling-import precedent already landed for the neighboring `_git_root()`
duplication. Stdlib-only (`os` only) -- satisfies `test_hook_stdlib_only_contract.py`'s
distribution-resolution invariant trivially, since it imports no third-party distribution at all.

In an ordinary clone, `<git_root>/.git` IS the common dir (a directory). In a worktree,
`<git_root>/.git` is a FILE containing a single `gitdir: <path>` line pointing at the worktree's
own private git dir (`<path>` may be relative to `git_root`); that private git dir in turn
contains a `commondir` file naming the actual shared common dir (again possibly relative -- this
time to the private git dir itself). Blindly joining `git_root + ".git"` silently resolves to a
location that doesn't exist as a directory under a worktree -- a write there fails and a
best-effort `except` swallows it; a read there simply finds nothing. Subagents DO run in
worktrees (the `Agent` tool's `isolation: "worktree"` mode), so this is a live fail-open
portability defect, not a theoretical one.

Negative spec: do NOT reintroduce a subprocess (`git rev-parse --git-common-dir`) here as a
routine path -- this module stays the zero-spawn primitive its sibling `_git_root_walk.py`
already established. Every caller degrades to "" on an unresolvable common dir and must treat
that as "skip, do not build a path from empty string" -- never as "already fired"/"already
present".
"""

from __future__ import annotations

import os


def resolve_git_common_dir(git_root: str) -> str:
    """Resolve the git COMMON dir for `git_root` without spawning a subprocess. Fails open to
    "" on any error, including the plain-clone case where `.git` is simply a directory. Never
    raises."""
    try:
        dot_git = os.path.join(git_root, ".git")
        if os.path.isdir(dot_git):
            return dot_git
        if os.path.isfile(dot_git):
            with open(dot_git, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
            if not text.startswith("gitdir:"):
                return ""
            gitdir_value = text[len("gitdir:"):].strip()
            git_dir = (
                gitdir_value
                if os.path.isabs(gitdir_value)
                else os.path.normpath(os.path.join(git_root, gitdir_value))
            )
            if not os.path.isdir(git_dir):
                return ""
            commondir_file = os.path.join(git_dir, "commondir")
            if os.path.isfile(commondir_file):
                with open(commondir_file, "r", encoding="utf-8", errors="replace") as fh:
                    common_value = fh.read().strip()
                if not common_value:
                    return git_dir
                return (
                    common_value
                    if os.path.isabs(common_value)
                    else os.path.normpath(os.path.join(git_dir, common_value))
                )
            return git_dir
        return ""
    except Exception:
        return ""
