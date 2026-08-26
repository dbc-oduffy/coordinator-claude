#!/usr/bin/env python3
"""PostToolUse(Agent) naked-Python fan-in dispatcher.

W0 (docs/plans/2026-08-25-route-the-bash-guard-onto-the-native-htt.md) --
folds the two DoE `PostToolUse|Agent` registrations that used to spawn their
own interpreter each (agent-completion-log.py, track-dispatched-agents.py's
PostToolUse enrich leg) into ONE `python3` hook entry, calling the ENGINE-side
fan-in op `coordinator_core.hooks.agent_postuse_dispatch` (published mirror
HEAD 6bcbb8b7) that already merges both legs' `run()` calls under one
`asyncio.gather(..., return_exceptions=True)` -- see that op's own module
docstring for the merge contract and the isolation guarantee. This shim is
PLUMBING ONLY (DR-047 transport-seam carve-out): parse stdin, build the UNION
of both legs' flat-scalar params, relay to the engine, relay its stdout.

Both existing scripts (agent-completion-log.py, track-dispatched-agents.py)
STAY registered -- this fold is ADDITIVE, not a migration. `track-dispatched-
agents.py`'s SubagentStart leg (the `cater_subagent_start` create+catering
call) is untouched; only its PostToolUse|Agent enrich leg is superseded by
this shim on the registration surface (hooks.json), never by editing that
script.

Params (union of both legs' own field lists -- `agent_postuse_dispatch`
reads none of them itself, just passes them through verbatim to each leg):
    session_id                <- stdin["session_id"]
    description                <- stdin["tool_input"]["description"]        (agent_completion_log only)
    subagent_type               <- stdin["tool_input"]["subagent_type"]      (both legs, same source)
    name                         <- stdin["tool_input"]["name"]               (agent_completion_log only)
    dispatched_agent_id          <- stdin["tool_response"]["agentId"]         (both legs, same source)
    dispatched_agent_id_snake    <- stdin["tool_response"]["agent_id"]        (both legs, same source)
    dispatched_model             <- tool_response.resolvedModel
                                     -> tool_response.model
                                     -> tool_input.model
                                     -> ""                                    (track_dispatched_agents only;
                                        mirrors track-dispatched-agents.py's
                                        _extract_dispatch_fields cascade)
Missing/absent stdin keys map to "" -- mcp_tool's own "undeclared -> empty
string" convention; each leg's own field()/fallback logic already treats ""
as absent.

No tool_name=="Agent" gate here -- the registration's matcher IS exactly
`Agent` (hooks.json), so every fire is already scoped; re-checking it in this
shim would be a second copy of that config, drifting silently (the folded
op's own negative-spec makes the identical point about its own handler).

_origin_worktree: scope is the UNION of the two legs' own scopes, both
"common_dir" -- injected from stdin["cwd"] directly, same extraction shape as
agent-completion-log.py and track-dispatched-agents.py's own PostToolUse
path. Absent cwd -> "_origin_worktree" omitted from the envelope ->
resolve_op_repo_key() raises inside the engine -> caught by the fail-open
seam below -> silent no-op.

Graceful degradation -- REQUIRED: any failure to resolve/import/run the
engine, or to parse stdin, falls through to fail-open (exit 0, no
stdout). A missing sibling engine, or a missing/unresolvable cwd, must NEVER
brick an Agent-tool completion -- identical philosophy to
agent-completion-log.py / preuse-write-dispatch.py's own root resolver.
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
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    raw = sys.stdin.read()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.agent_postuse_dispatch triggers the
        # coordinator_core.hooks package __init__ (registers every op via
        # register_op side-effects at import time -- the hooks package has no
        # lazy-skip guard, unlike coordinator_core.ops). One-time cost per
        # invocation, in-process, still zero subprocess spawns.
        from coordinator_core.hooks import agent_postuse_dispatch as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    tool_response = payload.get("tool_response")
    if not isinstance(tool_response, dict):
        tool_response = {}

    dispatched_model = (
        tool_response.get("resolvedModel")
        or tool_response.get("model")
        or tool_input.get("model")
        or ""
    )

    params = {
        "session_id": payload.get("session_id", ""),
        "description": tool_input.get("description", ""),
        "subagent_type": tool_input.get("subagent_type", ""),
        "name": tool_input.get("name", ""),
        "dispatched_agent_id": tool_response.get("agentId", ""),
        "dispatched_agent_id_snake": tool_response.get("agent_id", ""),
        "dispatched_model": dispatched_model if isinstance(dispatched_model, str) else "",
    }

    cwd = payload.get("cwd")

    try:
        result = dispatch_from_hook(
            "hooks.agent_postuse_dispatch",
            params,
            origin_worktree=cwd if isinstance(cwd, str) else None,
        )
    except HookDispatchError:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    if result:
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
