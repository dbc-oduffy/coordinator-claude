#!/usr/bin/env python3
"""PostToolUse(Agent) naked-Python bookkeeping dispatcher.

Replaces the claude-klabauter-advisory half of the former bash agent-completion-log.sh
PostToolUse registration (the fire-and-forget `advisory_call
"hooks.agent_completion_log"` block at the bottom of that script) with ONE
`python3` hook entry -- zero Git-Bash cold-start per Agent-tool completion on
Windows (each bash.exe spawn costs 200-500ms; this is the whole point).

DoE owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the claude-klabauter engine, hand it the mapped params, relay its stdout.
Claude-klabauter owns the write LOGIC (coordinator_core.hooks.agent_completion_log,
registered under the JSON-RPC method "hooks.agent_completion_log") -- the
actual jsonl append to .git/coordinator-sessions/logs/agent-audit.jsonl. The
engine is imported and run IN-PROCESS via coordinator_core.ipc.dispatch_message
-- no bash, no `python3 -m` subprocess re-spawn -- so a whole Agent-tool
completion pays exactly one Python interpreter start.

Contract (mirrors the claude-klabauter-advisory half of the bash hook it replaces --
agent-completion-log.sh's `advisory_call "hooks.agent_completion_log"` block;
the LOCAL bash jq append to agent-audit.jsonl in that same script is a
SEPARATE, still-live write path this stub does NOT touch or supersede --
see "Open risks" below):
  stdin   -- PostToolUse JSON (tool_name, tool_input, tool_response,
             session_id, cwd, ...)
  stdout  -- NOTHING (this op always returns no_advisory() == {}; the
             product is the disk-append side-effect, not stdout)
  exit 0  -- always (write side-effect happens or it doesn't; never
             conveyed via exit code, and never blocks the tool call)

stdin -> params mapping (op scope "common_dir" -- REQUIRES _origin_worktree;
see coordinator_core/ipc.py _OP_KEY_SCOPE: "hooks.agent_completion_log":
"common_dir". coordinator_core/hooks/agent_completion_log.py's handler reads
description / subagent_type / name / dispatched_agent_id /
dispatched_agent_id_snake via _payload.field() -- each key is read straight
off the SAME-NAMED top-level stdin key, per the W2-stub-contract.md § 1 rule
("stdin-JSON-key == params-dict-key identity mapping, restricted to the keys
the target op's field() calls actually read"). The bash oracle
(agent-completion-log.sh's advisory_call block) builds its _PARAMS from
NESTED tool_input/tool_response fields via jq, not flat top-level stdin keys
-- this stub does the equivalent flattening in Python before building params,
since the claude-klabauter handler expects flat scalars (see the handler's own R-1
docstring: "inputs are flat scalars extracted by the mcp_tool manifest shim"
-- this stub IS that flattening shim, standing in for mcp_tool):
    session_id                <- stdin["session_id"]
    description                <- stdin["tool_input"]["description"]        (default "unknown" handled op-side)
    subagent_type               <- stdin["tool_input"]["subagent_type"]      (default "general-purpose" handled op-side)
    name                         <- stdin["tool_input"]["name"]               (default null handled op-side)
    dispatched_agent_id          <- stdin["tool_response"]["agentId"]         (R-1 flattened form)
    dispatched_agent_id_snake    <- stdin["tool_response"]["agent_id"]        (snake-case fallback, named-teammate dispatch)
Missing/absent stdin keys map to "" -- mcp_tool's own "undeclared -> empty
string" convention; _payload.field() already treats "" as ABSENT, so an
absent key here is indistinguishable from one mcp_tool would have dropped.

_origin_worktree: this op is "common_dir"-scoped (per W2-stub-contract.md
§ 3's bookkeeping-ops caveat) -- injected from stdin["cwd"] directly, mirroring
preuse-write-dispatch.py's existing cwd extraction (NOT walked up to the git
root by this stub; coordinator_core.lifecycle.git_common_dir(repo_root)
already does that resolution itself via a `git rev-parse --path-format=absolute
--git-common-dir` subprocess with cwd=repo_root -- any path inside the repo
tree is sufficient input). Absent cwd -> "_origin_worktree" omitted from the
envelope -> dispatch_message raises ValueError (INVALID_PARAMS) -> caught by
the fail-open seam below -> silent no-op (a functional regression vs the
legacy bash's unconditional jq append, but the LOCAL bash write path stays
live during the transition window, see "Open risks").

Graceful degradation -- REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine, or to parse stdin, falls through to fail-open (exit 0, no
stdout). A missing sibling engine, or a missing/unresolvable cwd, must NEVER
brick an Agent-tool completion -- identical philosophy to
preuse-write-dispatch.py._resolve_claude_klabauter_root (kept in lockstep deliberately;
see W2-stub-contract.md).

NOTE: hooks.json is rewired to this dispatcher (this file, agent-completion-log.py)
and the legacy bash hook (agent-completion-log.sh) has been removed; this
stub's LOCAL jq append to agent-audit.jsonl is the sole, authoritative write
path. The consumer, runtime-tripwire-em-check.py, greps for `"agentId":"<id>"`
substring-anywhere.

Open risks / caveats (see also W2-stub-contract.md § 7, which this stub
inherits verbatim for the shared parts):
  - _OP_KEY_SCOPE drift risk realized: this is one of the 4 "common_dir"-scoped
    bookkeeping ops the reference stub's § 3 flagged by name
    (track_touched_files, session_heartbeat, agent_completion_log,
    track_dispatched_agents) -- _origin_worktree IS wired here (unlike a stub
    that skipped it), but a missing/garbage stdin["cwd"] still silently
    degrades to a no-op via the fail-open seam, not a loud error. This is a
    known, accepted tradeoff (fail-open over fail-loud for a hook shim), not
    an oversight -- flagging per the reference contract's own instruction to
    make this an explicit, named risk rather than relying on fail-open to
    paper over it.
  - Package-wide eager import (all 11 coordinator_core.hooks ops registered on
    first import of any one) and asyncio.run() per-invocation event-loop cost
    both apply here identically to the reference stub -- see
    W2-stub-contract.md § 7 for the full rationale; not re-derived here.
  - hooks.json cutover is explicitly out of scope for this stub (EM-owned).
"""

from __future__ import annotations

import asyncio
import json
import os
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
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.agent_completion_log triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time cost, in-process, still zero subprocess spawns.
        from coordinator_core.hooks import agent_completion_log as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message
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

    params = {
        "session_id": payload.get("session_id", ""),
        "description": tool_input.get("description", ""),
        "subagent_type": tool_input.get("subagent_type", ""),
        "name": tool_input.get("name", ""),
        # R-1: dispatched_agent_id is the flattened tool_response.agentId (camelCase);
        # dispatched_agent_id_snake is the snake_case fallback from named-teammate
        # dispatch returns -- the handler ORs the two, mirroring the bash oracle's
        # `.tool_response.agentId // .tool_response.agent_id // null` cascade.
        "dispatched_agent_id": tool_response.get("agentId", ""),
        "dispatched_agent_id_snake": tool_response.get("agent_id", ""),
    }

    cwd = payload.get("cwd")

    msg: dict = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hooks.agent_completion_log",
        "params": params,
    }
    # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- REQUIRES
    # _origin_worktree; the handler resolves git_common_dir(repo_root) from it
    # (any path inside the repo tree is sufficient, git does the walk-up).
    if isinstance(cwd, str) and cwd:
        msg["_origin_worktree"] = cwd

    try:
        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    result = response.get("result") if isinstance(response, dict) else None
    if result:  # {} (no_advisory) and None both fall through to no-output;
        # this op always returns no_advisory() -- the product is the disk-append
        # side-effect, not stdout -- so this branch is dead in normal operation
        # but kept for parity with the reference stub's envelope-relay shape.
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
