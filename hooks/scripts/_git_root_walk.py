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

Negative spec: do NOT reintroduce a `git rev-parse --show-toplevel` spawn here as a routine
path, and do NOT fold a subprocess fallback into this module. Each caller already carries its
own subprocess-fallback rung (this module intentionally leaves those in place unchanged --
different callers use different timeouts, exception scopes, and console-suppression idioms) for
the rare case this walk cannot resolve (a bare repo, or a `GIT_DIR`-driven invocation with no
`.git` above cwd); this function returns `None` on that path rather than falling back itself,
so it stays the zero-spawn primitive its name promises.
"""

from __future__ import annotations

from pathlib import Path


def git_root_walk() -> str | None:
    """Repo root as `git rev-parse --show-toplevel` would report it, fail-open to None.

    In-process parent walk for a `.git` entry (a directory in an ordinary clone, a FILE in a
    linked worktree or submodule) -- no subprocess spawn. Returns `str(candidate)` (a
    `pathlib`-resolved path, which on Windows carries backslash separators, NOT the
    forward-slash form `git rev-parse` prints) -- callers that need byte-parity with git's own
    output string must not assume separator style; compare via `Path(...).resolve()` equality
    instead, matching this module's own verification approach. Never raises.
    """
    try:
        start = Path.cwd().resolve()
        for candidate in (start, *start.parents):
            if (candidate / ".git").exists():
                return str(candidate)
    except Exception:
        pass
    return None
