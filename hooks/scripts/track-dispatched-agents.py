#!/usr/bin/env python3
"""SubagentStart + PostToolUse(Agent) naked-Python bookkeeping dispatcher.

C3 (docs/plans/2026-08-10-adopt-harness-native-hook-capabilities.md) split
the write across two events. `SubagentStart` carries `agent_id`/`agent_type`
as first-class fields and fires before the agent-dies-early failure mode
that motivated this move; it makes the CREATE call, identity-only (see
`_build_subagent_start_params`). `PostToolUse(Agent)` -- the original
registration this module replaced the former bash cascade for -- is reduced
to the ENRICH call, supplying the real `subagent_type` and the real resolved
`dispatched_model`. Both calls go through the same engine op
(`hooks.track_dispatched_agents`); its shared collision resolver treats an
existing "unknown" subagent_type as an enrichable placeholder, so the create
call's identity-only shape is what routes the second call onto the enrich
branch instead of the idempotent-dedup branch that would otherwise discard
the real model. See `_SUBAGENT_START_PLACEHOLDER_TYPE`.

Replaces the former bash PostToolUse(Agent)
registration (agentId/model/subagent_type bookkeeping writes) with ONE
`python3` hook entry -- zero Git-Bash cold-start per Agent-tool return on
Windows (each bash.exe spawn costs 200-500ms; this is the whole point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): parse
the raw PostToolUse payload, extract the same flat scalars the legacy bash
cascade computed, resolve the claude-klabauter engine, hand it the mapped params, relay
its stdout. Claude-klabauter owns the write LOGIC (coordinator_core.hooks.
track_dispatched_agents, registered under "hooks.track_dispatched_agents") --
the dedup/collision-rewrite/append to dispatched-agents.txt and the atomic
em-session-id.txt back-pointer. The engine is imported and run IN-PROCESS via
coordinator_core.ipc.dispatch_message -- no bash, no `python3 -m` subprocess
re-spawn -- so a whole Agent-tool return pays exactly one Python interpreter
start.

Contract (mirrors the retired bash hook it replaces):
  stdin   -- PostToolUse JSON (tool_name, tool_input, tool_response,
             session_id, cwd, ...)
  stdout  -- NOTHING (this op returns no_advisory() unconditionally; its
             product is the on-disk write side-effect, not stdout)
  exit 0  -- always (advisory bookkeeping; never blocks the Agent tool call)
  As of the posttooluse-non-fire diagnostic, `main()` also appends one line
  to a scratch canary log before any other processing; see
  `_write_posttooluse_agent_canary`.

stdin -> params mapping (op scope "common_dir" -- REQUIRES _origin_worktree;
see coordinator_core/ipc.py _OP_KEY_SCOPE["hooks.track_dispatched_agents"] =
"common_dir", and W2-stub-contract.md § 3's bookkeeping-ops caveat).
Unlike postuse_advisory_dispatch (op scope "none", flat stdin-key ==
params-key identity mapping), this op's handler does NOT do its own field
extraction from tool_response/tool_input -- its docstring's "R-1" note says
dispatched_agent_id / dispatched_model / subagent_type arrive as FLAT SCALARS
"pre-resolved by manifest" (the mcp_tool-era three-pass / four-source
cascades). This stub is not going through mcp_tool, so it must itself run
those same cascades over the raw JSON payload before calling the op --
mirroring the retired bash hook's extraction logic exactly (see
_extract_dispatch_fields below), not just relaying stdin keys 1:1.

On PostToolUse(Agent) (enrich call):
    session_id                <- stdin["session_id"]                          (top level)
    dispatched_agent_id       <- stdin["tool_response"]["agentId"]            (pass a, camelCase)
    dispatched_agent_id_snake <- stdin["tool_response"]["agent_id"]           (pass a, snake_case)
    dispatched_model           <- tool_response.resolvedModel
                                   -> tool_response.model
                                   -> tool_input.model
                                   -> "" (handler itself defaults "" to "unknown")
    subagent_type               <- tool_input.subagent_type -> "" (handler defaults "unknown")

On SubagentStart (create call, see `_build_subagent_start_params`):
    session_id                <- stdin["session_id"]                          (top level)
    dispatched_agent_id       <- stdin["agent_id"]                            (top level)
    dispatched_model           <- _SUBAGENT_START_PLACEHOLDER_TYPE ("unknown", never resolved)
    subagent_type               <- _SUBAGENT_START_PLACEHOLDER_TYPE ("unknown", never the real
                                    stdin["agent_type"] -- see module docstring: writing the real
                                    type here would land the enrich call on the idempotent-dedup
                                    branch instead of the enrich branch, stranding model)

Handler-side validation NOT replicated here (belongs to claude-klabauter, not this
stub): agent-id format guard (bare-hex >=12 / teammate canonical id), the
session_id/agent_id required-field early-outs, and the model/subagent_type
"" -> "unknown" fallback -- all already implemented in
coordinator_core/hooks/track_dispatched_agents.py's handler. This stub only
extracts and forwards; it does not duplicate that logic.

_origin_worktree (REQUIRED -- "common_dir" scope): set to stdin["cwd"], the
same field preuse-write-dispatch.py already extracts for its own (non-scoped)
purposes. The op handler resolves this into the shared .git common directory
via coordinator_core.lifecycle.git_common_dir (a `git rev-parse
--path-format=absolute --git-common-dir` subprocess call with cwd=repo_root)
-- claude-klabauter-owned, not this stub's concern; mirrors the same "not the stub's
subprocess" caveat postuse-advisory-dispatch.py's reference contract already
names for the runtime-tripwire's git call. If cwd is absent, dispatch_message
returns an INVALID_PARAMS error response (not a raised exception) -- result is
None, `if result:` is already false, this degrades to the SAME silent no-op
fail-open as every other seam (see W2-stub-contract.md § 3's caveat: this is a
functional regression vs a resolvable cwd, but a safe one -- absent cwd never
crashes or writes partial state).

Event branch: `main()` dispatches on `hook_event_name`. On `SubagentStart`
it runs the create path unconditionally (there is no tool-name gate on this
event -- every fire carries a dispatched agent's identity). On `PostToolUse`
it preserves the legacy tool-name gate: the retired bash hook exited 0
immediately unless tool_name == "Agent" (matcher scoping done in-script, not
via hooks.json matcher alone, historically); this stub keeps that same
early-out -- running the extraction cascade and a full IPC dispatch on every
non-Agent PostToolUse event would be pure waste (the op has no tool_name
gate of its own; the docstring's "R-1" contract assumes the caller already
scoped to Agent-tool returns). Any other hook_event_name value is unreached
in registered use (this script is only ever invoked as SubagentStart or
PostToolUse) and falls through to fail-open.

Graceful degradation -- REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine, or to parse stdin, falls through to fail-open (exit 0, no
stdout). A missing sibling engine must NEVER brick an Agent-tool return --
identical philosophy to preuse-write-dispatch.py._resolve_claude_klabauter_root (kept
in lockstep deliberately; see W2-stub-contract.md).

NOTE (historical): during the bash->Python cutover, the retired bash hook and
this dispatcher briefly co-registered; both writing the same dedup/append-tab-
format file was harmless (idempotent dedup on matching agent_id +
subagent_type), so there was no window with bookkeeping down. The bash hook
is now fully retired; this dispatcher is the only writer.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- copied from
    runtime-tripwire-stop-watcher.py._read_stdin (~186-201).

    A bare sys.stdin.read() blocks forever if the harness never closes
    stdin's write end (observed Windows failure mode), backstopped with a 2s
    threaded-join timeout, returning "" (the same fail-open value a
    JSON-decode failure already produces) instead of hanging the hook chain.
    """
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


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


# Identity-only create placeholder (C3): sent as BOTH dispatched_model and
# subagent_type on the SubagentStart call. Matches PLACEHOLDER_TYPE in the
# engine's collision resolver -- writing this literal (never the real,
# available stdin["agent_type"]) is what routes the later PostToolUse(Agent)
# enrich call onto the enrich-in-place branch instead of idempotent-dedup;
# see the module docstring.
_SUBAGENT_START_PLACEHOLDER_TYPE = "unknown"


def _extract_dispatch_fields(payload: dict) -> dict[str, str]:
    """Run the same agent-id / four-source model cascade as the bash hook.

    Mirrors the retired bash hook's steps (a)/(c) exactly, operating on the
    already-parsed JSON dict instead of raw-text slicing. Returns "" for any
    field that cannot be resolved -- the op handler's own field()/fallback logic
    treats "" as absent, matching mcp_tool's own convention.
    """
    tool_response = payload.get("tool_response")
    if not isinstance(tool_response, dict):
        tool_response = {}
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # (a) primary: camelCase agentId (unnamed/background agents).
    dispatched_agent_id = tool_response.get("agentId") or ""
    # (a) fallback: snake_case agent_id (named Agent-Teams teammates).
    dispatched_agent_id_snake = tool_response.get("agent_id") or ""

    # (c) model: resolvedModel -> model (both tool_response) -> tool_input.model -> "".
    dispatched_model = (
        tool_response.get("resolvedModel")
        or tool_response.get("model")
        or tool_input.get("model")
        or ""
    )

    # subagent_type: tool_input only; "" if absent (handler defaults to "unknown").
    subagent_type = tool_input.get("subagent_type") or ""

    return {
        "dispatched_agent_id": dispatched_agent_id if isinstance(dispatched_agent_id, str) else "",
        "dispatched_agent_id_snake": dispatched_agent_id_snake if isinstance(dispatched_agent_id_snake, str) else "",
        "dispatched_model": dispatched_model if isinstance(dispatched_model, str) else "",
        "subagent_type": subagent_type if isinstance(subagent_type, str) else "",
    }


def _build_subagent_start_params(payload: dict) -> dict[str, str] | None:
    """Build the identity-only create-call params from a SubagentStart payload.

    Returns None when the identity field is absent -- the caller degrades to
    fail-open rather than dispatching a params dict with no agent_id.
    """
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    return {
        "dispatched_agent_id": agent_id,
        "dispatched_agent_id_snake": "",
        "dispatched_model": _SUBAGENT_START_PLACEHOLDER_TYPE,
        "subagent_type": _SUBAGENT_START_PLACEHOLDER_TYPE,
    }


def _write_posttooluse_agent_canary(raw: str) -> None:
    """Diagnostic scaffolding for
    state/bug-backlog/2026-08-10-posttooluse-agent-does-not-fire-for-some-8c1d40be9f2a.yaml.

    Discriminates whether the PostToolUse(Agent) hook PROCESS ever started
    on a given Agent-tool return: a line present in the canary log means
    this process ran at least this far, so a missing dispatched-agents.txt /
    agent-audit.jsonl row on that spawn is a downstream (in-process) failure;
    a line absent means the harness never delivered or killed the chain
    before this point. Both consumer writers are already exonerated by
    replay (fast, always-exit-0) -- this canary is the only thing that can
    tell the two remaining hypotheses apart. Remove once that bug is closed
    and the discriminator is no longer needed.

    Parses `raw` only (the SAME stdin string `main()` already read via its
    single `_read_stdin()` call) -- never reads stdin itself, so it cannot
    starve `main()`'s own read on a machine running many concurrent
    sessions. Wrapped entirely in try/except: an unwritable path, a full
    disk, or a malformed payload degrades to "no canary line", never to a
    broken hook -- this function's whole contract is fail-open.
    """
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        tool_name = payload.get("tool_name") or ""
        session_id = payload.get("session_id") or ""
        cwd = payload.get("cwd") or None

        tool_response = payload.get("tool_response")
        if not isinstance(tool_response, dict):
            tool_response = {}
        agent_id = tool_response.get("agentId") or tool_response.get("agent_id") or ""

        probe = Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd()
        git_dir = None
        for candidate in (probe, *probe.parents):
            marker = candidate / ".git"
            if marker.is_dir():
                git_dir = marker
                break
            if marker.is_file():
                raw_pointer = marker.read_text(encoding="utf-8", errors="replace")
                if not raw_pointer.startswith("gitdir:"):
                    return
                pointer = raw_pointer[len("gitdir:"):].strip()
                if not pointer:
                    return
                pointer_path = Path(pointer)
                if not pointer_path.is_absolute():
                    pointer_path = (candidate / pointer_path).resolve()
                git_dir = pointer_path
                break
        if git_dir is None:
            return

        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            raw_common = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            if not raw_common:
                return
            common_path = Path(raw_common)
            if not common_path.is_absolute():
                common_path = (git_dir / common_path).resolve()
            common_dir = common_path
        else:
            common_dir = git_dir

        log_dir = common_dir / "coordinator-sessions" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{stamp}\t{tool_name}\t{session_id}\t{agent_id}\n"
        # Windows append-atomicity for concurrent writers is NOT independently
        # verified here (see finding 1 in the 0d753c61e canary review, and the
        # closure note in the linked bug-backlog entry): a torn/interleaved
        # line under concurrent CRT "a"-mode writes is an accepted false
        # negative for this discriminator -- a present-but-malformed line
        # still proves the process ran this far, which is the only question
        # this canary exists to answer.
        with (log_dir / "posttooluse-agent-canary.log").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write(line)
    except Exception:
        return


def main() -> int:
    raw = _read_stdin()
    _write_posttooluse_agent_canary(raw)

    try:
        payload: Any = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    event = payload.get("hook_event_name")

    if event == "SubagentStart":
        fields = _build_subagent_start_params(payload)
        if fields is None:
            return 0  # fail-open -- missing identity field, nothing to write
        session_id = payload.get("session_id") or ""
        cwd = payload.get("cwd") or None
        params = {
            "session_id": session_id if isinstance(session_id, str) else "",
            **fields,
        }
        return _dispatch_bookkeeping_write(cwd, params)

    # PostToolUse(Agent) enrich path -- unreached hook_event_name values
    # (this script is only ever registered on SubagentStart and PostToolUse)
    # fall through this branch and hit the tool-name gate below, which
    # returns 0 on anything but an Agent-tool return.

    # Tool-name gate (mirrors bash line 82): only Agent-tool returns carry a
    # dispatched agentId worth bookkeeping. Cheap early-out before any engine
    # resolution / IPC dispatch cost.
    if payload.get("tool_name") != "Agent":
        return 0

    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd") or None

    fields = _extract_dispatch_fields(payload)

    params = {
        "session_id": session_id if isinstance(session_id, str) else "",
        **fields,
    }

    return _dispatch_bookkeeping_write(cwd, params)


def _dispatch_bookkeeping_write(cwd: Any, params: dict) -> int:
    """Shared IPC seam for both the SubagentStart create call and the
    PostToolUse(Agent) enrich call -- same op, same in-process dispatch, same
    fail-open contract on either side.
    """
    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.track_dispatched_agents triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time-per-invocation cost, in-process, still zero subprocess
        # spawns -- but each hook fire is a fresh process, so this import
        # cost recurs every fire, not just once per session.
        from coordinator_core.hooks import track_dispatched_agents as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message
    except Exception:
        return 0  # engine unimportable -> fail-open

    msg: dict = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hooks.track_dispatched_agents",
        "params": params,
    }
    # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- REQUIRED.
    # Absent/unresolvable cwd degrades to an INVALID_PARAMS error response
    # (caught below by the `if result:` falsy check), not a raised exception.
    if cwd:
        msg["_origin_worktree"] = str(cwd)

    try:
        asyncio.run(dispatch_message(msg))
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a hook fire)

    # No stdout relay: this op is MUTATING bookkeeping (dedup/append to
    # dispatched-agents.txt + the em-session-id.txt back-pointer), never
    # advisory -- it always returns no_advisory() == {}. The contract is
    # "stdout NOTHING" (see module docstring), enforced structurally here by
    # never inspecting/relaying the response, not incidentally via `{}`'s
    # falsiness under `if result:`.
    return 0


if __name__ == "__main__":
    sys.exit(main())
