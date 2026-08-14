"""Shared helper for PreToolUse write-guards that protect a named sentinel
file (a file whose mere ABSENCE gates a guarded capability) from being
created or modified through Write/Edit/MultiEdit/NotebookEdit.

Why this exists
----------------
Two guards in this tree gate a capability on a repo-root sentinel file's
absence: `guard-doctrine-surface-edits.py` (`.coordinator-doctrine-edit-
approved`) and the git-worktree ban (`.coordinator-override-worktree-
guard`, enforced on the tool-call surface by `block-worktree-tool.py` /
`strip-worktree-isolation.py`). Any guard shaped this way has the same
hole unless its sentinel is ALSO protected on the file-write surface: an
agent can `Write` the sentinel into existence directly, bypassing whatever
shell-level guard blocks `touch`. That is exactly how the doctrine guard's
own sentinel-write hole was found (see its module docstring), and it is
exactly how the worktree-ban sentinel's matching hole was found (both
`Write` and `touch` succeeded against `.coordinator-override-worktree-
guard`, after which `EnterWorktree` succeeded). This module makes closing
that second leg a two-line call instead of a hand-copied basename check,
so the next sentinel-gated guard is cheap to protect rather than repeating
the pattern -- and the bug -- by hand.

Ordering contract -- read before use
-------------------------------------
A caller that ALSO consults the sentinel's presence for an approval/allow
decision (as `guard-doctrine-surface-edits.py` does) MUST call
`sentinel_write_denial()` BEFORE that approval-state lookup. Consulting
approval state first and only then checking the target path would let a
currently-valid approval authorize an edit that EXTENDS or RENEWS itself.
A caller that has no such approval lookup at all (e.g. a guard whose only
job is protecting one sentinel, like the worktree-sentinel guard built
against this module) has no ordering hazard to worry about -- there is
nothing else in that script to order against.

Removal is intentionally out of scope here -- this module only knows how
to DENY a Write/Edit/MultiEdit/NotebookEdit call whose target is the
sentinel path. Deletion tools are not in the guarded matcher set, so
`rm`/deletion always stays available through other surfaces, and removing
a sentinel to re-lock its boundary remains the sanctioned recovery path
every sentinel-gated guard relies on.

`reconstruct_after` re-export
-------------------------------
This module also re-exports `reconstruct_after`, resolving to the ENGINE
implementation (`coordinator_core.write_guards._sentinel_write_guard
.reconstruct_after`), not a local reimplementation. `preuse-write-dispatch
.py` puts `_HOOKS_DIR` (this directory) on `sys.path` ahead of the engine
root (clause 8 of `_guard_runner_contract.py`), so a bare
`_sentinel_write_guard` import always binds THIS file, not the engine's
module of the same basename -- the engine copy is never reachable that
way. The package-qualified name `coordinator_core.write_guards
._sentinel_write_guard` has no such collision, which is what makes this
re-export resolve to the one real implementation instead of shadowing it.

If the engine root cannot be resolved, or the import otherwise fails,
`reconstruct_after` falls back to a stub returning `None` unconditionally.
`None` is the established unreconstructable/fail-open signal every caller
of this function already honours as "cannot compute, do not deny". In
production this fallback is largely unreachable: `preuse-write-dispatch
.main()` already returns fail-open ALLOW before any guard runs when the
engine is unresolvable, so the guards that call `reconstruct_after` do not
execute at all in that state. The stub exists for a pytest or
partial-deploy environment where this module is imported without its
sibling engine checkout present.
"""

from __future__ import annotations

import os
import sys

_PATH_KEYS = ("file_path", "notebook_path", "path")


def extract_target_path(tool_input: dict) -> str:
    """Best-effort target path from a Write/Edit/MultiEdit/NotebookEdit
    `tool_input` payload, checking `_PATH_KEYS` in order. Returns "" if
    none of the recognized keys carry a non-empty string value.

    Deliberately permissive, not an oversight: a non-string value under a
    `_PATH_KEYS` entry (e.g. a list/dict, which no real Write/Edit/
    MultiEdit/NotebookEdit tool schema produces today) is treated as "no
    path" and falls through to the next key / the empty-string return,
    i.e. fail-open. That is the same fail-open posture every other
    unresolvable shape in this module takes -- there is nothing to protect
    against a payload shape the guarded tools cannot actually emit.
    """
    if not isinstance(tool_input, dict):
        return ""
    for key in _PATH_KEYS:
        val = tool_input.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def is_sentinel_write(target_path: str, sentinel_name: str) -> bool:
    """True if `target_path` resolves to `sentinel_name`, case-folded.

    Two hardenings beyond a plain basename `==`:

    - Resolved before comparison via `os.path.realpath(os.path.abspath(...))`,
      so a write through a symlink whose own name is NOT the sentinel but
      which POINTS AT the sentinel path still matches. `os.path.realpath`
      on a not-yet-existing leaf component is safe -- it normalizes the
      path without raising, which matters here because the sentinel
      usually does not exist yet (that is the whole point of a guard that
      denies its creation).
    - Compared case-folded (`.lower()`), because the read side that grants
      the override this guard exists to prevent (`block-worktree-tool.py`
      ::`_sentinel_override_active`, and the doctrine guard's own approval
      lookup) checks presence via `os.path.isfile()`, which is effectively
      case-insensitive on the fleet's primary hazard filesystem (macOS
      APFS, default case-insensitive-but-case-preserving). A case-varied
      write that a case-sensitive check here would silently allow still
      round-trips into a live override on that filesystem.

    Basename match only (never substring/prefix) -- a near-miss filename
    (e.g. a `-typo` suffix) or an unrelated file must never be caught by
    this check.

    Safe to call on a path a caller has already resolved itself (e.g.
    `guard-doctrine-surface-edits.py`'s own `_norm()`): `os.path.realpath`
    is idempotent, so resolving an already-resolved absolute path a second
    time is a harmless no-op, not a correctness concern.
    """
    if not target_path:
        return False
    try:
        resolved = os.path.realpath(os.path.abspath(target_path))
        return os.path.basename(resolved).lower() == sentinel_name.lower()
    except Exception:
        return False


def sentinel_write_denial(
    target_path: str, sentinel_name: str, reason: str
) -> "dict | None":
    """Returns a PreToolUse deny `hookSpecificOutput` dict if `target_path`
    targets `sentinel_name`, else None.

    Caller is responsible for invoking this BEFORE any approval-state
    lookup that also consults the same sentinel (see module docstring,
    "Ordering contract").
    """
    if not is_sentinel_write(target_path, sentinel_name):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _reconstruct_after_stub(tool_name: str, tool_input: dict, before: str) -> "str | None":
    """Fail-open fallback bound to `reconstruct_after` when the engine
    implementation cannot be imported. See the module docstring's
    "`reconstruct_after` re-export" section for why `None` unconditionally
    is the correct fallback rather than a local reimplementation."""
    return None


try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_engine_root

    _engine_root = _resolve_engine_root()
except Exception:
    _engine_root = None

if _engine_root:
    try:
        if _engine_root not in sys.path:
            sys.path.insert(0, _engine_root)
        from coordinator_core.write_guards._sentinel_write_guard import (
            reconstruct_after,
        )
    except Exception as _exc:
        print(
            f"_sentinel_write_guard: engine reconstruct_after import failed, "
            f"falling back to stub: {_exc!r}",
            file=sys.stderr,
        )
        reconstruct_after = _reconstruct_after_stub
else:
    reconstruct_after = _reconstruct_after_stub
