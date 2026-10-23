"""PreToolUse hook (matchers: Agent, Workflow): refuse a dispatch brief that
carries a suite-shaped command. Forwarder only -- every decision lives in the
engine op `hooks.block_dispatch_suite_invocation`
(`coordinator_core.hooks.block_dispatch_suite_invocation`), which returns the
PreToolUse deny envelope or an allow.

Trap: no decision logic belongs here. A local classifier copy drifted from the
engine's and false-denied the engine's own emitted engine-ask script as a
Tier-U `pytest` command; the forwarder exists so there is one guard, not two.

The per-dispatch override env var is read by the engine from `payload["env"]`,
never from the engine process's own environment, so the forwarder hands it
`os.environ`.

Fails open (silent exit 0) when the payload is unreadable, the engine root is
unresolvable, the engine module is unimportable, or the op raises -- a broken
guard must never wedge every dispatch.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        payload["env"] = dict(os.environ)
        from _engine_root import place_engine_root_on_path, resolve_claude_klabauter_root

        claude_klabauter_root = resolve_claude_klabauter_root()
        if not claude_klabauter_root:
            return 0
        place_engine_root_on_path(claude_klabauter_root)
        from coordinator_core.hooks.block_dispatch_suite_invocation import _handler

        envelope = _handler(payload)
    except Exception:
        return 0
    if envelope and envelope.get("hookSpecificOutput", {}).get("permissionDecision"):
        print(json.dumps(envelope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
