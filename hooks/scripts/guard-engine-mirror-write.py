# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py calls in-process. Never referenced literally in hooks.json.
"""PreToolUse guard: deny Write/Edit/MultiEdit/NotebookEdit against a file under the
resolved published engine mirror or any registered `publish.mirrors.*` directory.

A publish mirror is a publish target, never a working tree: an in-place edit is live
for every session until the next publish overwrites it. The engine's own tool-surface
bump is clearable by a marker a dispatched subagent inherits from its EM, so it does
not hold for subagents; this guard has no marker and no sentinel.

Contract:
  - Applies to every caller, EM and subagent alike. The one pass-through is a session
    whose own cwd is inside the mirror: someone opened it there deliberately.
  - Recovery stays reachable: `git -C <mirror> checkout -- <file>` is a Bash call.
  - Any failure fails open (exit 0, no stdout).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _sentinel_write_guard import extract_target_path  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _canon(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def mirror_roots() -> list:
    """Resolved published engine root (when the engine resolves to a published
    mirror) plus every registered publish-mirror directory, canonicalised."""
    import _engine_root as er

    roots = []
    root, resolution_class, _prov = er.resolve_claude_klabauter_root_with_provenance()
    if root and resolution_class == er.RESOLUTION_RESOLVED_ENGINE:
        roots.append(root)
    roots.extend(path for path, _owner, _key in er.resolve_publish_mirror_roster())
    return [_canon(r) for r in roots if r]


def denial_for(tool_input: dict, cwd: str = "", roots: "list | None" = None) -> "dict | None":
    target = extract_target_path(tool_input)
    if not target:
        return None
    resolved = _canon(target)
    hit = next((r for r in (mirror_roots() if roots is None else roots) if _inside(resolved, r)), None)
    if hit is None:
        return None
    if cwd and _inside(_canon(cwd), hit):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{hit} is a publish mirror: it is published to, never hand-edited. "
                "Author the change in the source repo and publish it. To undo an edit "
                f"already made there, run `git -C {hit} checkout -- <file>`."
            ),
        }
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or payload.get("tool_name") not in _GUARDED_TOOLS:
            return 0
        result = denial_for(payload.get("tool_input") or {}, str(payload.get("cwd") or ""))
    except Exception:
        return 0
    if result:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
