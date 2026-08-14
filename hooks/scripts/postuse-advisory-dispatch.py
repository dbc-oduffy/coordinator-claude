#!/usr/bin/env python3
"""PostToolUse(*) naked-Python advisory dispatcher.

Replaces the former bash postuse-advisory-dispatch.sh PostToolUse
registration (context-pressure + runtime-tripwire checks) with ONE `python3`
hook entry -- zero Git-Bash cold-start per tool call on Windows (each bash.exe
spawn costs 200-500ms; this is the whole point).

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the mapped params, relay its stdout. Claude-klabauter owns the
advisory LOGIC (coordinator_core.hooks.postuse_advisory_dispatch, registered
under the JSON-RPC method "hooks.postuse_advisory_dispatch"). The engine is
imported and run IN-PROCESS via coordinator_core.ipc.dispatch_message -- no
bash, no `python3 -m` subprocess re-spawn -- so a whole PostToolUse fire pays
exactly one Python interpreter start.

TRACK-TOUCHED-FILES FOLD (C4b, docs/plans/2026-08-06-hook-spawn-fan-in-
finish-and-extend.md § C4b): this dispatcher ALSO issues the
`hooks.track_touched_files` MUTATING bookkeeping call (formerly
`track-touched-files.py`'s own standalone `Write|Edit|MultiEdit|
NotebookEdit` PostToolUse registration) -- the one guard among the five
PostToolUse write-path guards trivial to fold here rather than into the new
Stop-family runner (`postuse-stop-family-dispatch.py`, the sibling
mechanism for the other four): it has NO advisory text to aggregate (always
returns `no_advisory() == {}`), and both this dispatcher and that stub
already pay the SAME `coordinator_core.hooks` package-import cost and the
SAME in-process `dispatch_message` IPC call shape, so folding it in adds
one more `dispatch_message` call, not a second mechanism. Gated on
`tool_name` internally (see `_TRACK_TOUCHED_FILES_TOOLS` below) to mirror
that guard's own former hooks.json matcher -- this dispatcher's OWN matcher
(`''`, every PostToolUse event) is a strict superset, so no matcher
widening was needed to absorb it.

Contract (mirrors the bash hook it replaces -- postuse-advisory-dispatch.sh):
  stdin   -- PostToolUse JSON (tool_name, tool_input, session_id, transcript_path,
             agent_id, cwd, ...)
  stdout  -- one hookSpecificOutput JSON envelope (post_advisory shape) when
             context-pressure and/or runtime-tripwire fires; NOTHING otherwise
  exit 0  -- always (advisory conveyed via stdout, never exit code)

stdin -> params mapping (op scope "none" -- no _origin_worktree needed; see
docs/plans/2026-07-04-pcore-04-advisory-hook-ops-claude-klabauter-engine.md, Tasks row
C7: "current input: tool_name, session_id | add to input: transcript_path,
agent_id". coordinator_core/hooks/postuse_advisory_dispatch.py's handler reads
session_id / transcript_path / agent_id / tool_name via _payload.field().
Context-pressure and runtime-tripwire remain ungated and universal (fire on
every PostToolUse event regardless of tool_name); the first-Agent-dispatch
sidecar advisory is the exception -- it gates on tool_name == "Agent" (plus
its own once-per-session sentinel), so tool_name is read for that check, not
merely carried for input-declaration parity):
    session_id       <- stdin["session_id"]
    transcript_path  <- stdin["transcript_path"]
    agent_id         <- stdin["agent_id"]
    tool_name        <- stdin["tool_name"]   (gates only the first-Agent-dispatch
                                               check; context-pressure and
                                               runtime-tripwire ignore it)
    file_path        <- stdin["tool_input"]["file_path"]  (folded
                                               nudge_unauthorized_handoff advisory
                                               only; gates on tool_name == "Write".
                                               TRANSPORT-SEAM
                                               GATE: populated only when
                                               tool_name == "Write" -- every other
                                               tool call omits this key entirely
                                               rather than shipping an unbounded
                                               file body across the IPC seam for a
                                               param no other consumer reads)
    content          <- stdin["tool_input"]["content"]    (folded
                                               nudge_unauthorized_handoff advisory
                                               only; same tool_name == "Write" gate
                                               as file_path above)
Missing/absent stdin keys map to "" -- mcp_tool's own "undeclared -> empty
string" convention; _payload.field() already treats "" as ABSENT, so an
absent key here is indistinguishable from one mcp_tool would have dropped.

track_touched_files params (op scope "common_dir" -- REQUIRES
_origin_worktree, unlike postuse_advisory_dispatch's scope "none" above;
see coordinator_core/ipc.py _OP_KEY_SCOPE["hooks.track_touched_files"]):
    session_id       <- stdin["session_id"]
    tool_name        <- stdin["tool_name"]
    file_path        <- stdin["tool_input"]["file_path"]
    agent_id         <- stdin["agent_id"]
    _origin_worktree <- stdin["cwd"]   (JSON-RPC envelope field, not an op
                                          param -- required because this
                                          op's _OP_KEY_SCOPE is "common_dir")

Graceful degradation -- REQUIRED: any failure to resolve/import/run the claude-klabauter
engine, or to parse stdin, falls through to fail-open (exit 0, no stdout). A
missing sibling engine must NEVER brick a tool call -- identical philosophy to
preuse-write-dispatch.py._resolve_claude_klabauter_root (kept in lockstep deliberately;
see W2-stub-contract.md).

NOTE: cutover is complete -- hooks.json registers only this Python hook now.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- copied from
    runtime-tripwire-stop-watcher.py._read_stdin (~186-201).

    A bare sys.stdin.read() blocks forever if the harness never closes
    stdin's write end (observed Windows failure mode). This hook fires on
    EVERY PostToolUse event, so a hang here stalls every subsequent tool
    call in the session -- highest-frequency hot path in this cohort, hence
    P1. Backstopped with a 2s threaded-join timeout, returning "" (the same
    fail-open value a JSON-decode failure already produces) instead of
    hanging.
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


#: `track-touched-files.py`'s own former matcher, mirrored here as an
#: internal gate (C4b) -- this dispatcher's own hooks.json matcher (`''`,
#: every PostToolUse event) is wider, so folding the bookkeeping call in
#: without this gate would issue a wasted IPC round-trip on every
#: non-write PostToolUse event (Bash, Agent, ...).
_TRACK_TOUCHED_FILES_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def main() -> int:
    raw = _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.postuse_advisory_dispatch triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time-per-invocation cost, in-process, still zero subprocess
        # spawns -- but each hook fire is a fresh process, so this import
        # cost recurs every fire, not just once per session. track_touched_files
        # (C4b) is the SAME package -- no additional import cost to fold it in.
        from coordinator_core.hooks import postuse_advisory_dispatch as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message
    except Exception:
        return 0  # engine unimportable -> fail-open

    async def _dispatch_both(advisory_msg: dict, track_msg: "dict | None"):
        """Runs the (always-present) advisory dispatch, then (tool_name
        -gated, possibly absent) the track-touched-files bookkeeping call,
        SEQUENTIALLY under ONE `asyncio.run()` -- not `asyncio.gather()`.
        Concurrent scheduling of the two `dispatch_message()` calls was
        tried first and broke `test_postuse_advisory_dispatch.py`'s
        existing nudge-firing tests (empty stdout where an advisory was
        expected) -- `dispatch_message`'s own concurrency-safety under two
        simultaneous in-flight calls in one event loop is unverified engine
        -side behaviour this dispatcher has no business relying on.
        Sequential execution costs one extra await, not one extra process
        or import -- the actual fan-in goal (one interpreter, in-process,
        zero subprocess spawns) is unaffected either way. The
        track-touched-files call's own failure is swallowed here (never
        raised past this function) so it can never suppress the advisory
        dispatch's own result -- same fail-open-per-concern posture as the
        rest of this module."""
        advisory_response = await dispatch_message(advisory_msg)
        track_response = None
        if track_msg is not None:
            try:
                track_response = await dispatch_message(track_msg)
            except Exception:
                track_response = None
        return advisory_response, track_response

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    tool_name = payload.get("tool_name", "")

    params = {
        "session_id": payload.get("session_id", ""),
        "transcript_path": payload.get("transcript_path", ""),
        "agent_id": payload.get("agent_id", ""),
        "tool_name": tool_name,
    }
    # Gate the file body at the transport seam: file_path/content are read
    # ONLY by the folded nudge_unauthorized_handoff advisory, which itself
    # gates on tool_name == "Write" -- so every other PostToolUse fire
    # (the overwhelming majority of tool calls in a session) must not
    # serialise an unbounded file body across the IPC seam for a param no
    # consumer reads. Key omitted (not "") on the non-Write path, matching
    # the "missing/absent stdin keys map to absent" convention documented
    # above -- _payload.field() already treats "" as ABSENT so the two are
    # engine-equivalent; omission is chosen for symmetry with how absent
    # stdin keys are handled everywhere else in this mapping.
    if tool_name == "Write":
        params["file_path"] = tool_input.get("file_path", "")
        params["content"] = tool_input.get("content", "")

    advisory_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hooks.postuse_advisory_dispatch",
        "params": params,
        # scope "none" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- no
        # _origin_worktree required; this op accesses no repo-specific state.
    }

    track_msg = None
    if tool_name in _TRACK_TOUCHED_FILES_TOOLS:
        track_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "hooks.track_touched_files",
            "params": {
                "session_id": payload.get("session_id", ""),
                "tool_name": tool_name,
                "file_path": tool_input.get("file_path", "") or "",
                "agent_id": payload.get("agent_id", ""),
            },
            # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) --
            # REQUIRED. Handed through raw; the engine resolves
            # git-common-dir itself from whatever cwd the harness reports.
            "_origin_worktree": payload.get("cwd", ""),
        }

    try:
        response, _track_response = asyncio.run(_dispatch_both(advisory_msg, track_msg))
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    # _track_response is deliberately never inspected/relayed: track_touched_
    # files is MUTATING bookkeeping, never advisory (see track-touched-
    # files.py's own former module docstring, "stdout NOTHING") -- its
    # result is discarded here exactly as that stub discarded it itself.
    result = response.get("result") if isinstance(response, dict) else None
    if result:  # {} (no_advisory) and None both fall through to no-output
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
