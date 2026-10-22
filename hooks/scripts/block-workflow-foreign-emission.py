"""PreToolUse hook (matcher: Workflow): refuse to fire a script this session
did not emit. Forwarder only -- every decision lives in the engine's
`coordinator_core.hooks.block_workflow_foreign_emission.evaluate`, which
returns `{}` to admit or the PreToolUse deny envelope.

Trap: no decision logic belongs here. A local copy of the sha/session/fire-
token arms drifted from the engine's once already (it lacked the read-only
exemption, the no-receipt deny and the plan-amended deny); the forwarder
exists so there is one guard, not two.

Fails open (silent exit 0) when the payload is unreadable, the engine root is
unresolvable, the engine module is unimportable, or evaluate raises -- a
broken guard must never wedge every Workflow launch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        from _engine_root import place_engine_root_on_path, resolve_claude_klabauter_root

        claude_klabauter_root = resolve_claude_klabauter_root()
        if not claude_klabauter_root:
            return 0
        place_engine_root_on_path(claude_klabauter_root)
        from coordinator_core.hooks.block_workflow_foreign_emission import evaluate

        envelope = evaluate(payload)
    except Exception:
        return 0
    if envelope:
        print(json.dumps(envelope))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
