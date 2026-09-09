"""repo_root — the repo a script is standing in, found by walking `cwd` upward for `.git`.

WHY THIS EXISTS. The same eight-line `cwd`-upward `.git` walk, each copy carrying its own
paragraph of identical rationale about `.git` being a file in a linked worktree, was independently
authored into seven scripts under `coordinator/bin/` and `coordinator/skills/**`. This is the one
home for that walk, sited beside `_engine_root.py` because both new callers already put this
directory on `sys.path` to reach it. Callers supply their own fallback: what a script defaults to
when no `.git` is found (its own repo root, a doctrine-repo-relative constant, ...) differs per
module and is not this seam's business.

Zero subprocess: `.git` is a directory in a primary checkout and a file in a linked worktree, and
`Path.exists()` covers both without spawning `git rev-parse` (25.3ms, per DR-344) to answer it.
"""

from __future__ import annotations

from pathlib import Path


def repo_root(fallback: Path) -> Path:
    """Walk `cwd` and its parents for a `.git` entry; `fallback` when none is found or `cwd`
    itself cannot be read.

    Never spawns a process. `fallback` is always a path the caller already trusts, so degrading to
    it on an unreadable `cwd` is always safe — the walk fails closed, not silently wide.
    """
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return fallback
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return fallback
