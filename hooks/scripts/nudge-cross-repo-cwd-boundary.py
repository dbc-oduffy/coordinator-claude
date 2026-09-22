#!/usr/bin/env python3
"""CwdChanged naked-Python cross-repo boundary nudge for register entry #15.

BUILD ARM (C13's spike verdict, `state/reference/anthropic-docs/_hook-frontmatter-
reachability.md`: `unit-b-15 verdict: BUILD`). Fires on the same crossing `CwdChanged`
itself reports -- `PreToolUse` -> `CwdChanged` -> `PostToolUse`, ~47µs apart -- so the
nudge lands on the crossing, not a later tool call that happens to observe the new cwd.
Payload carries BOTH `old_cwd` and `new_cwd`; C13 confirmed one fire per crossing
regardless of the shell's own later auto-reset (the reset-case `Shell cwd was reset to
<A>` message never produces a second fire).

MATCH DIRECTION: a boundary crossing is `new_cwd` resolving INTO, or `old_cwd`
resolving OUT OF, the engine sibling path -- resolved at runtime IN-PROCESS via
`_engine_root._resolve_live_working_tree()`, whose registry rung reads
`repos.claude_klabauter` through `_registry_value`. Never a hardcoded path, and never a
`machine-local` CLI subprocess: this registration already pays one python3 cold start
per fire, and the CLI form would pay a second, redundant one.

UNRESOLVED SIBLING IS A NO-OP (negative spec, binding). When
`_resolve_live_working_tree()` returns `(None, provenance)` -- the normal state on an
install with no `repos.claude_klabauter` registry rung -- this script exits 0 having
emitted nothing. It never compares against a `None` endpoint and never falls back to a
substring match on the engine repo's directory-name literal; a substring match would
false-positive on an unrelated path merely containing that text.

NO MATCHER FILTERS THIS. `CwdChanged` is on the documented no-matcher list, and the
spike proved the harness accepts a matcher and fires anyway -- a matcher chosen so it
could not possibly match still fired. All narrowing happens in-script against the
payload, not via the hooks.json registration.

WINDOWS LEG: both endpoints are normalised (case-folded, separators unified) before
comparison -- a POSIX-shaped comparison here does not error, it silently never fires,
the worst failure mode a nudge can have (project CLAUDE.md § Runtime conventions,
multi-OS P0).

Contract:
  stdin   -- CwdChanged JSON (cwd, hook_event_name, new_cwd, old_cwd, prompt_id,
             session_id, transcript_path)
  stdout  -- one hookSpecificOutput JSON envelope (additionalContext) on a matching
             crossing; NOTHING otherwise (silent pass)
  exit 0  -- always (advisory only; never blocks/denies)

Graceful degradation -- REQUIRED: any failure to parse stdin, import `_engine_root`, or
resolve the sibling falls through to a silent pass (exit 0, no stdout, never a crash).
A filesystem/registry hiccup must never brick a cwd-change.

House pattern: this script resolves its own sibling directory via
`Path(__file__).resolve().parent`, mirroring every other naked-Python hook in this
directory. Fail-open on every internal error (broad `except Exception`), per the
`_hook_boot.py` house bootstrap this registration runs under.

SOURCE OF THE REMEDIATION PROSE: the baton pointing at this entry named a now-removed
meta-repo local-doctrine file's "Cross-repo write discipline" section. The live
replacement is this repo's own `CLAUDE.md` § Subject-matter routing: no standing
cross-repo commit grant survives in either direction; a cross-repo commit needs
per-session PM assent obtained at execution dispatch; when held, scoped commits only --
never `git add -A`/`.`/`commit -a`, no destructive git ops, never leave the sibling's
tests red.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _engine_root import _resolve_live_working_tree
except Exception:
    # A hook script deployed WITHOUT its sibling _engine_root.py must still
    # fail-open rather than crash on import.
    def _resolve_live_working_tree():  # type: ignore[misc]
        return None, "none"


_REMEDIATION = (
    "[cross-repo boundary] this session just crossed into or out of the claude-klabauter "
    "sibling repo. No standing cross-repo commit grant survives in either direction "
    "(DoE-claude CLAUDE.md § Subject-matter routing) -- a cross-repo commit needs "
    "per-session PM assent obtained at execution dispatch. When held: scoped commits "
    "only, never `git add -A`/`.`/`commit -a`; no destructive git ops; never leave "
    "the sibling's tests red."
)


def _norm(path: str) -> str:
    """Case-fold and separator-normalise for a Windows-safe boundary comparison --
    a POSIX-shaped comparison here does not error, it silently never fires."""
    return os.path.normcase(os.path.normpath(path))


def _crosses_boundary(old_cwd: str, new_cwd: str, sibling_root: str) -> bool:
    root_norm = _norm(sibling_root)
    old_norm = _norm(old_cwd)
    new_norm = _norm(new_cwd)

    def _inside(candidate: str) -> bool:
        return candidate == root_norm or candidate.startswith(root_norm + os.sep)

    new_inside = _inside(new_norm)
    old_inside = _inside(old_norm)
    # INTO the sibling, or OUT OF it -- not a crossing when both endpoints agree.
    return new_inside != old_inside


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    old_cwd = payload.get("old_cwd")
    new_cwd = payload.get("new_cwd")
    if not isinstance(old_cwd, str) or not old_cwd:
        return 0
    if not isinstance(new_cwd, str) or not new_cwd:
        return 0

    try:
        sibling_root, _provenance = _resolve_live_working_tree()
    except Exception:
        sibling_root = None
    if not sibling_root:
        # UNRESOLVED SIBLING IS A NO-OP -- never a substring fallback.
        return 0

    try:
        crosses = _crosses_boundary(old_cwd, new_cwd, sibling_root)
    except Exception:
        return 0
    if not crosses:
        return 0

    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "CwdChanged",
            "additionalContext": _REMEDIATION,
        }
    }
    try:
        sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open, unconditionally -- a CwdChanged hook that itself raises
        # must never brick a session's ability to change directory.
        sys.exit(0)
