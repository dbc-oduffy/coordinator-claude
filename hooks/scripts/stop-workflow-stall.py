"""Stop-dispatch REGISTRY member -- relays the engine's stalled-workflow resume leg.

Plumbing only. The engine owns the decision: which of this session's Workflow
runs is stalled, and the exact `Workflow({scriptPath, resumeFromRunId, args})`
call that resumes it (`coordinator_core.hooks.postuse_advisory_dispatch.
workflow_stall_resume_text`, the same reader the engine's own
`hooks.workflow_stall_stop` op calls).

The shim imports that reader rather than the `hooks.workflow_stall_stop` op
because the op lives in `coordinator_core.hooks.stop_dispatch`, whose import
pulls every Stop leg the engine composes. Measured on this box: 64 ms against
28 ms, paid on every top-level Stop.

Channels, matching the engine op's three outcomes:
  - stalled, first Stop of the chain -> reason on stderr, exit 2 (block)
  - stalled, chained Stop (stop_hook_active) -> reason on stdout, exit 0
    (an advisory; blocking again would loop the Stop chain)
  - nothing stalled, subagent Stop, engine unresolvable or failing -> nothing,
    exit 0 (fail-open)

Contract:
  stdin  -- Stop JSON (session_id, transcript_path, stop_hook_active, agent_id)
  exit   -- 2 on a block, 0 otherwise
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else {}
    except Exception:
        return 0
    if not isinstance(payload, dict) or payload.get("agent_id"):
        return 0
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return 0
    transcript_path = payload.get("transcript_path")

    try:
        root = _resolve_claude_klabauter_root()
    except Exception:
        return 0
    if not root:
        return 0
    from _engine_root import place_engine_root_on_path
    place_engine_root_on_path(root)

    try:
        from coordinator_core.hooks.postuse_advisory_dispatch import (
            workflow_stall_resume_text,
        )
        text = workflow_stall_resume_text(
            session_id,
            transcript_path if isinstance(transcript_path, str) else "",
            time.time(),
        )
    except Exception:
        return 0
    if not text:
        return 0

    if payload.get("stop_hook_active"):
        sys.stdout.write(text + "\n")
        return 0
    sys.stderr.write(text + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
