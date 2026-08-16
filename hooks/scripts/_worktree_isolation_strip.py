"""_worktree_isolation_strip.py -- shared library, NOT a registered hook.

Single-emitter fix (2026-07-31): `strip-worktree-isolation.py` and
`enforce-agent-dispatch-mode.py` used to independently build their own
`hookSpecificOutput.updatedInput` from a full copy of the same `tool_input`
on overlapping PreToolUse matchers (`Agent|Workflow` and `Agent`
respectively). Claude Code runs same-event hooks in parallel with undefined
completion order, and `updatedInput` is last-writer-wins -- so on an `Agent`
dispatch carrying BOTH `isolation: "worktree"` AND a mode-elevation/sidecar/
role-framing trigger, exactly one hook's rewrite silently clobbered the
other's (confirmed live on harness 2.1.220; see
`docs/plans/2026-07-31-agent-updated-input-single-emitter.md` -- or the
dispatch brief that fixed this, if that plan was never written).

Fix shape: the worktree-isolation-strip COMPUTATION (this module) is now
shared, pure, and side-effect-free (no stdout, no sys.exit). The only two
callers that may EMIT `updatedInput` for a tool_name are:
  - `enforce-agent-dispatch-mode.py` for `Agent` -- folds this module's
    result into its own single merged `updatedInput` (mode elevation +
    sidecar + contract-blocks + role-framing + worktree-strip, all layered
    onto ONE `merged` dict, ONE emission site).
  - `strip-worktree-isolation.py` for `Workflow` -- `Workflow`'s tool_input
    has no `prompt` key (it carries `script`/`scriptPath`), so it cannot
    share `enforce-agent-dispatch-mode.py`'s Agent-only emit path; it stays
    its own hook, scoped to `Workflow` only, importing this module instead
    of re-implementing the strip/override logic.

Neither caller re-implements the override-sentinel check or the key-removal
logic -- both import `compute_strip` from here. This is the "one function,
one module" shape: two matchers still need the computation, so both call it,
but the merge-and-emit path per matcher exists exactly once.

Only the literal value "worktree" is banned. `isolation: "remote"` (and any
other value) is a legitimate, unrelated isolation mode and passes through
byte-identical -- `compute_strip` returns `None` for it, same as when no
`isolation` key is present at all.

Override: a repo-root sentinel file only, `.coordinator-override-worktree-
guard` -- deliberately NOT an env-var leg. An env var is process-inheritable
by a dispatched subagent (it can set its own env before its own tool calls
run under this same hook), which would let a subagent silently defeat a
guard that exists specifically to bind subagents. `_git_root()` and
`sentinel_override_active()` are copied in shape (not behavior-modified)
from `block-workflow-unmodeled-agent.py` lines 487-533: 1s subprocess
timeout on `git rev-parse --show-toplevel`, fails toward NO override on any
resolution failure (not a repo, git missing, timeout, unreadable sentinel).

Fail-open on every detection-failure leg: `compute_strip` returns `None`
(nothing to strip) on any git-root-resolution failure -- it never raises.
Both callers remain responsible for their own stdin/JSON/tool_name/
tool_input validation; this module only computes the strip once the caller
has already established `tool_input` is a dict.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

try:
    from _git_root_walk import git_root_walk as _git_root_walk
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_root_walk.py
    # must still fail open to the subprocess rung below, not crash on import.
    def _git_root_walk() -> "str | None":
        return None

_OVERRIDE_SENTINEL_NAME = ".coordinator-override-worktree-guard"

_STRIP_NOTE = (
    "[worktree guard] isolation: \"worktree\" stripped -- per-dispatch "
    "worktrees are banned (shared-tree discipline); dispatch proceeds "
    "without it."
)


def _git_root() -> "str | None":
    """Repo root as `git rev-parse --show-toplevel` would report it -- same idiom as
    block-workflow-unmodeled-agent.py's `_git_root()`: an in-process parent walk
    (`_git_root_walk`) first, no subprocess on the routine path, with the 1s-timeout
    `git rev-parse --show-toplevel` subprocess below kept only as a fallback for the case the
    walk cannot resolve. Any failure (not a git repo, git missing, timeout) returns None and
    the sentinel check below is skipped -- fails toward "no override", never toward a crash.
    """
    walked = _git_root_walk()
    if walked:
        return walked
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def sentinel_override_active() -> bool:
    """Repo-root sentinel file override, ONLY leg -- no env-var leg by
    design (see module docstring: a subagent can set its own env, which
    would defeat a guard that must bind subagents too). Fails toward "no
    override" (returns False) on any resolution failure.
    """
    root = _git_root()
    if not root:
        return False
    try:
        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


def compute_strip(tool_input: dict) -> Optional[tuple[dict, str]]:
    """Pure computation, no I/O beyond the override-sentinel git-root check.

    Returns `(merged_tool_input, note)` when `tool_input["isolation"] ==
    "worktree"` and no override sentinel is active -- `merged_tool_input` is
    a FULL COPY of `tool_input` with the `isolation` key removed (never a
    partial object), and `note` is the fixed advisory string every caller
    surfaces via `hookSpecificOutput.additionalContext`.

    Returns `None` when there is nothing to strip: `isolation` absent, any
    non-"worktree" value (including "remote", which passes through
    byte-identical), or the override sentinel is active.
    """
    if tool_input.get("isolation") != "worktree":
        return None
    if sentinel_override_active():
        return None
    merged = dict(tool_input)
    del merged["isolation"]
    return merged, _STRIP_NOTE
