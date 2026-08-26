#!/usr/bin/env python3
"""PostToolUse(Write|Edit|MultiEdit|NotebookEdit|Agent) naked-Python advisory dispatcher.

Replaces the former bash postuse-advisory-dispatch.sh PostToolUse
registration (context-pressure + runtime-tripwire checks) with ONE `python3`
hook entry -- zero Git-Bash cold-start per tool call on Windows (each bash.exe
spawn costs 200-500ms; this is the whole point).

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the mapped params, relay its stdout. Claude-klabauter owns the
advisory LOGIC (coordinator_core.hooks.postuse_advisory_dispatch, registered
under the JSON-RPC method "hooks.postuse_advisory_dispatch"). The engine is
imported and run IN-PROCESS via coordinator_core.ipc.dispatch_ops_from_hook
(DR-175's named hook-dispatch seam, multi-op form -- see the per-concern
isolation note in `main()`) -- no bash, no `python3 -m` subprocess re-spawn
-- so a whole PostToolUse fire pays exactly one Python interpreter start.

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
SAME in-process `dispatch_ops_from_hook` IPC call shape, so folding it in
adds one more op to the same call, not a second mechanism. Gated on
`tool_name` internally (see `_TRACK_TOUCHED_FILES_TOOLS` below) to mirror
that guard's own former hooks.json matcher -- this dispatcher's OWN matcher
(`Write|Edit|MultiEdit|NotebookEdit|Agent`, narrowed 2026-08-16 from `''`
-- see the RE-SCOPE note below) is still a strict superset of this tuple,
so no matcher widening was needed to absorb it.

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
Context-pressure and runtime-tripwire remain ungated internally (they do not
inspect tool_name) but, since the 2026-08-16 RE-SCOPE below, fire only on the
narrowed matcher's tool set rather than literally every PostToolUse event;
the first-Agent-dispatch
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

RE-SCOPE (2026-08-16, state/handoffs/2026-08-16-untitled-6c1eb4ae.md Next
Steps 1, third bullet; state/audits/2026-08-16-doe-spawn-totality-kill-list.md
K-01): hooks.json's matcher for this dispatcher was narrowed from `''`
(every PostToolUse event -- the single largest broad-matcher offender the
2026-08-16 spawn-totality audit found) to `Write|Edit|MultiEdit|NotebookEdit
|Agent`. DIVERGENCE FROM THE HANDOFF'S LITERAL "move the advisory to Stop":
two of the four folded checks read fields a Stop payload never carries --
the first-Agent-dispatch sidecar advisory needs `tool_name == "Agent"` and
the unauthorized-handoff nudge needs `tool_name == "Write"` plus
`file_path`/`content` from the SAME PostToolUse fire. A Stop event has no
`tool_name` at all, so relaying it there would silently and permanently
disable both (their own internal gates would simply never match again) --
not a narrower firing cadence, an outright feature loss with no compensating
registration. Narrowing the matcher instead of moving the event keeps all
four checks' exact existing behaviour (context-pressure and runtime-tripwire
lose nothing but firing cadence, both being throttle/bark-once gated
already) while still dropping this dispatcher off the "" broad-matcher list.
`_TRACK_TOUCHED_FILES_TOOLS` (below) is unaffected -- it was already a
strict subset of the OLD matcher and remains one of the NEW, narrower matcher.
"""

from __future__ import annotations

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
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None


#: `track-touched-files.py`'s own former matcher, mirrored here as an
#: internal gate (C4b). RE-SCOPE (2026-08-16, state/handoffs/2026-08-16-
#: untitled-6c1eb4ae.md): this dispatcher's own hooks.json matcher was
#: narrowed from `''` (every PostToolUse event) to `Write|Edit|MultiEdit|
#: NotebookEdit|Agent` -- a strict superset of this tuple still (Agent is
#: the added tool the write itself never fires for), so this internal gate
#: remains live and load-bearing: it is what keeps the wasted IPC
#: round-trip out of every Agent-tool fire now reaching this script.
_TRACK_TOUCHED_FILES_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def main() -> int:
    raw = _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    # Must precede the first coordinator_core.* import -- see
    # _engine_root.arm_lazy_ops. Both ops this dispatcher names are
    # registered by the coordinator_core.hooks package import immediately
    # below, so the registry hits and no `_eager_import_all()` fallback
    # fires at lookup. Measured on Windows: ~0.12s -> ~0.09s end-to-end
    # per fire, warm cache, identical results either way.
    _arm_lazy_ops()

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
        from coordinator_core.ipc import HookDispatchError, dispatch_ops_from_hook
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

    # scope "none" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- no
    # _origin_worktree required for this op; it accesses no repo-specific
    # state. dispatch_ops_from_hook stamps origin_worktree onto EVERY op's
    # envelope (there is one shared origin_worktree kwarg, not a per-op
    # field), which is harmless here -- the postuse_advisory_dispatch
    # handler simply ignores an _origin_worktree key it never reads.
    ops: list[tuple[str, dict]] = [("hooks.postuse_advisory_dispatch", params)]

    if tool_name in _TRACK_TOUCHED_FILES_TOOLS:
        ops.append(
            (
                "hooks.track_touched_files",
                {
                    "session_id": payload.get("session_id", ""),
                    "tool_name": tool_name,
                    "file_path": tool_input.get("file_path", "") or "",
                    "agent_id": payload.get("agent_id", ""),
                },
            )
        )

    try:
        # Ops dispatched sequentially, in order, under ONE asyncio.run
        # inside dispatch_ops_from_hook -- same sequencing this dispatcher
        # always used, now expressed via the shared seam instead of a
        # locally-defined asyncio coroutine. Per-op errors are RETURNED
        # (HookDispatchError instances), not raised, so a failure in the
        # track_touched_files bookkeeping op can never suppress the
        # advisory op's own result, and vice versa -- the same
        # per-concern isolation the old local swallow provided, now
        # supplied by the seam's own returned-not-raised contract instead
        # of a try/except around the second call.
        results = dispatch_ops_from_hook(
            ops,
            origin_worktree=payload.get("cwd", ""),
        )
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    advisory_result = results[0] if results else None
    if isinstance(advisory_result, HookDispatchError):
        advisory_result = None

    # results[1] (track_touched_files), when present, is deliberately never
    # inspected/relayed: track_touched_files is MUTATING bookkeeping, never
    # advisory (see track-touched-files.py's own former module docstring,
    # "stdout NOTHING") -- a HookDispatchError there is simply discarded,
    # exactly as the old try/except swallow discarded it, and exactly as
    # the isolation contract above requires it not to touch advisory_result.
    if advisory_result:  # {} (no_advisory) and None both fall through to no-output
        sys.stdout.write(json.dumps(advisory_result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
