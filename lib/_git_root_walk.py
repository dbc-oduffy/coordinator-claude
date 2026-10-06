"""_git_root_walk -- stdlib-only, zero-spawn git-root resolution primitive for hook consumers.

Purpose: seven hook-script copies of the same `_git_root()`/`_resolve_this_repo_root()` idiom
each opened with `git rev-parse --show-toplevel` as their FIRST rung, spawning a subprocess on
every routine call even though the answer is almost always obtainable in-process. Measured on
this box: `git rev-parse --show-toplevel` costs ~25.1ms plus one process; an in-process parent
walk for a `.git` entry costs ~0.065ms median, zero processes, and returns a byte-identical
resolved path (verified `Path(...).resolve()`-equal, not string-equal -- see the callers'
`resolve()`-equality probes). Ported from the walk already landed in
`runtime-tripwire-em-check.py::_git_root`; this module is the shared seam so the other six
copies (`nudge-multiwave-workflow.py`, `block-workflow-unmodeled-agent.py`,
`block-worktree-tool.py`, `_worktree_isolation_strip.py`,
`guard-hook-generation-self-probe.py`, `sweep-boot.py`) reuse ONE walk instead of independently
re-deriving it a seventh and eighth time.

`_`-prefixed name matches the existing hook-module sibling-import convention (`_engine_root.py`,
`_win_portability.py`, `_message_envelope.py`): the hook scripts already do
`sys.path.insert(0, _HOOKS_DIR)` and import `_`-prefixed siblings from `hooks/scripts/`
directly. Stdlib-only (`pathlib` only) -- satisfies `test_hook_stdlib_only_contract.py`'s
distribution-resolution invariant trivially, since it imports no third-party distribution at all.

Start-anchored form: `git_root_walk(start)` walks from `start` instead of cwd, for callers that
resolve a root from a payload path rather than the process cwd; a falsy `start` falls back to
cwd.

Negative spec: do NOT reintroduce a `git rev-parse --show-toplevel` spawn here as a routine
path, and do NOT fold a subprocess fallback into this module. Each caller already carries its
own subprocess-fallback rung (this module intentionally leaves those in place unchanged --
different callers use different timeouts, exception scopes, and console-suppression idioms) for
the rare case this walk cannot resolve (a bare repo, or a `GIT_DIR`-driven invocation with no
`.git` above cwd); this function returns `None` on that path rather than falling back itself,
so it stays the zero-spawn primitive its name promises.
"""

from __future__ import annotations

import re
from pathlib import Path

# An absolute path token: a drive-letter or POSIX-root start not glued to a preceding path/URL
# character, so `https://host/x` never yields `//host/x`.
_ABS_PATH_RE = re.compile(r"(?<![\w/\\:.~-])(?:[A-Za-z]:[\\/]|/)[^\s\"'`<>|*?,;()\[\]{}]+")


def git_root_walk(start: str | None = None) -> str | None:
    """Return the nearest ancestor of `start` (default: cwd) holding a `.git` entry, else None."""
    try:
        origin = Path(start).resolve() if start else Path.cwd().resolve()
        for candidate in (origin, *origin.parents):
            if (candidate / ".git").exists():
                return str(candidate)
    except Exception:
        pass
    return None


def git_roots_named_in_text(text: str, limit: int = 3) -> list[str]:
    """Return up to `limit` distinct git roots that absolute paths in `text` live under.

    For a dispatch from a cwd that is no repo (a multi-repo parent directory): the brief's own
    absolute paths name the repo the subagent must be started in. Order is first mention.
    """
    roots: list[str] = []
    try:
        for match in _ABS_PATH_RE.finditer(text or ""):
            root = git_root_walk(match.group(0).rstrip(".:"))
            if root and root not in roots:
                roots.append(root)
                if len(roots) >= limit:
                    break
    except Exception:
        pass
    return roots
