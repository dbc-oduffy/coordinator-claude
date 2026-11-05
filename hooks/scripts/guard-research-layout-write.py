# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py calls in-process. Never referenced literally in hooks.json.
"""PreToolUse guard: deny Write/Edit/MultiEdit/NotebookEdit that would create a new
`<repo>/docs/research/` entry outside the run-dir layout
`docs/research/<topic>/<date>-<run-slug>/` (the contract is `lib/research_layout.py`).

Contract:
  - Applies to every caller, EM and subagent alike.
  - Denies only a target that does not exist yet, whose top-level component under
    docs/research/ does not exist on disk either, and that `research_layout.classify`
    calls nonconforming. An existing top-level legacy entry is grandfathered: new files
    inside an existing legacy dir, and edits to existing files, pass.
  - Any failure fails open (exit 0, no stdout).
"""

from __future__ import annotations

import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _sentinel_write_guard import extract_target_path  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_MARKER = "/docs/research/"

_DENY_REASON = (
    "docs/research/{rel} is not a conforming research path. A research run writes only inside "
    "docs/research/<topic>/<date>-<run-slug>/ (children: synthesis.md, trail.yaml, verdict.md, "
    "outputs/, workdir/); the top level of docs/research holds topic dirs, dot-prefixed markers and README.md only. "
    "Move the output under a run dir, e.g. docs/research/<topic>/<date>-<run-slug>/synthesis.md. "
    "To relocate an existing flat run, use coordinator/bin/research-layout-migrate.py."
)


def _layout():
    import importlib.util

    path = os.path.normpath(os.path.join(_HERE, "..", "..", "lib", "research_layout.py"))
    spec = importlib.util.spec_from_file_location("research_layout", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("research_layout", module)
    spec.loader.exec_module(module)
    return module


def is_in_scope(target: str) -> bool:
    return _MARKER in "/" + target.replace("\\", "/").casefold()


def denial_for(tool_input: dict) -> "dict | None":
    target = extract_target_path(tool_input)
    if not target or not is_in_scope(target):
        return None
    posix = target.replace("\\", "/")
    idx = ("/" + posix).casefold().find(_MARKER)
    # idx indexes the "/"-prefixed string, so the marker starts at idx and ends idx+len-1 in posix.
    base = posix[: idx + len(_MARKER) - 1]
    rel = posix[idx + len(_MARKER) - 1 :]
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or os.path.exists(target):
        return None
    if os.path.exists(os.path.join(base, parts[0])):
        return None
    if _layout().classify(rel) != "nonconforming":
        return None
    reason = _DENY_REASON.format(rel="/".join(parts))
    if len(parts) == 1:
        reason += _conforming_hint(parts[0])
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _conforming_hint(name: str) -> str:
    """Sentence naming the run-dir path for a stray top-level file; "" when the layout helper fails."""
    try:
        today = datetime.date.today().isoformat()
        return f" The conforming path for this write is docs/research/{_layout().conforming_path_for(name, today)}."
    except Exception:
        return ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or payload.get("tool_name") not in _GUARDED_TOOLS:
            return 0
        result = denial_for(payload.get("tool_input") or {})
    except Exception:
        return 0
    if result:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
