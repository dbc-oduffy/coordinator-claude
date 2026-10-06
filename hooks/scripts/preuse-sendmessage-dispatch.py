"""PreToolUse(SendMessage) shim -- chatty-workflow advisory.

Plumbing only: resolve the engine plane, hand it the raw payload, relay its stdout. The
engine owns the logic (`coordinator_core.hooks.preuse_sendmessage_dispatch`): locate the
sender's run dir from `agent_id`, read `<run-dir>/roster.json`, and emit
`additionalContext`. Advisory-only -- the op never denies and keeps no caps.

Deliberately NO shebang: hooks.json invokes this file through the `_hook_boot.py`
bootstrap, never directly.

Contract:
  stdin  -- PreToolUse JSON (agent_id, agent_type, session_id, transcript_path, tool_input...)
  stdout -- the op's hookSpecificOutput envelope, only when it has advice
  exit 0 -- every path, including every failure path (fail-open silent pass)

Wiki: docs/wiki/dispatching-parallel-agents/chatty-workflows.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Deployed without its sibling _engine_root.py: fail open, never crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        from coordinator_core.ipc import dispatch_from_hook
    except Exception:
        return 0

    # The whole payload is forwarded: run-dir resolution needs agent_id, session_id and
    # transcript_path together, and the op must see tool_input unflattened.
    try:
        result = dispatch_from_hook("hooks.preuse_sendmessage_dispatch", payload)
    except Exception:
        # Advisory-only: any dispatch failure (HookDispatchError or otherwise) is a silent pass.
        return 0

    if result:
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
