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
guard that exists specifically to bind subagents. `_git_root()` resolves the
root through `_git_root_walk` only -- no subprocess -- and fails toward NO
override on any resolution failure (not a repo, unreadable sentinel).

Fail-open on every detection-failure leg: `compute_strip` returns `None`
(nothing to strip) on any git-root-resolution failure -- it never raises.
Both callers remain responsible for their own stdin/JSON/tool_name/
tool_input validation; this module only computes the strip once the caller
has already established `tool_input` is a dict.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from _git_root_walk import git_root_walk as _git_root_walk
except Exception:
    # Fail open: missing sibling module must not crash import, only skip the fast path.
    def _git_root_walk() -> "str | None":
        return None

_OVERRIDE_SENTINEL_NAME = ".coordinator-override-worktree-guard"

_STRIP_NOTE = (
    "[worktree guard] isolation: \"worktree\" stripped -- per-dispatch "
    "worktrees are banned (shared-tree discipline); dispatch proceeds "
    "without it."
)


def _git_root() -> "str | None":
    return _git_root_walk() or None


def sentinel_override_active() -> bool:
    # Sentinel-file override only, deliberately no env-var leg -- a dispatched subagent can
    # set its own env, which would let it defeat a guard meant to bind subagents too.
    root = _git_root()
    if not root:
        return False
    try:
        return os.path.isfile(os.path.join(root, _OVERRIDE_SENTINEL_NAME))
    except Exception:
        return False


def compute_strip(tool_input: dict) -> Optional[tuple[dict, str]]:
    # Pure, no I/O beyond the override-sentinel check. Returns a FULL COPY of tool_input with
    # "isolation" removed plus the advisory note, or None when there is nothing to strip
    # (key absent, a non-"worktree" value, or the override sentinel is active).
    if tool_input.get("isolation") != "worktree":
        return None
    if sentinel_override_active():
        return None
    merged = dict(tool_input)
    del merged["isolation"]
    return merged, _STRIP_NOTE
