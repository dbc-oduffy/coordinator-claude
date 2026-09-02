#!/usr/bin/env python3
"""Stop/SubagentStop producer shim for the engine's receiver-state sensor.

PURPOSE. Makes `hooks.receiver_state_sensor` actually fire. The engine op has
been shipped and dispatchable in the engine repo since 2026-08-14, registered
across five surfaces -- RPC method name, import list, op scope, authz class,
module map -- **every one of them engine-internal**. None is a harness trigger,
and the op's own docstring says so verbatim: *"the doctrine plane owns hooks.json and the
transport shim; this repo ships no per-hook bin entrypoint for an
mcp_tool-dispatched op ... nothing here registers a hook trigger."* The trigger
is this file. Its absence -- not any property of the sensor, and nothing the
engine plane owed us -- is the whole reason `receiver-state.json` existed in 0 of 43
session dirs here.

This is PLUMBING ONLY (DR-047 transport-seam carve-out), the same split
`session-heartbeat.py` implements: the doctrine plane resolves the engine,
maps the payload to the pinned IPC params, and relays. The engine owns the entire
detection ladder -- `PAUSED:asking-human`, `PAUSED:tool-unanswered`,
`PAUSED:away`, `PRODUCING:*` -- in `coordinator_core.session.receiver_state`.
Nothing here derives a verdict, and a grep of this file for ladder logic,
transcript reading, or CPU sampling must return nothing.

CONTRACT (the `session-heartbeat.py` producer shape, NOT the
`nudge-harness-directive-dispatch.py` verdict/exit-2 shape -- the sensor always
returns `no_advisory()`, so there is no verdict to convert):
  stdin   -- Stop or SubagentStop JSON
  stdout  -- ALWAYS empty; the product is the write side-effect at
             `.git/coordinator-sessions/<session_id>/receiver-state.json`
  exit 0  -- always, on every path. A Stop is never blocked by this file.

WHICH TRANSCRIPT (the one requirement that is easy to get silently wrong).
`Stop` carries `transcript_path` -- this session's own. `SubagentStop` carries
BOTH `agent_transcript_path` (the subagent's own) and `transcript_path` (the
PARENT's, a decoy: a real, valid, tool-call-rich JSONL that reads as plausible
and is the wrong session entirely). On SubagentStop this shim passes
`agent_transcript_path` and nothing else; the same trap and the same rule are
documented at length in `subagent-zero-tool-use-detect.py` AC10. Branching on
`hook_event_name` inside one file, rather than forking two, is the resolution
of the open question the `gem-01` baton left for its executor -- the two
payloads DO diverge, so one unbranched file would feed the op a parent
transcript on every subagent stop.

`pid` IS DELIBERATELY OMITTED. A Stop payload carries no pid field, and
`os.getpid()` here is the hook process, not the session -- passing it would
silently corrupt the CPU-delta leg the day that leg stops being gated off. The
op treats an absent `pid` as "skip the CPU cursor" and still writes its ladder
verdict, which is exactly what is wanted. Per COORDINATOR-RESOLUTIONS the CPU
leg is gated off engine-side pending the engine-side CPU-discrimination spike.

`delegation_evidence` IS PASSED FALSE, NOT DERIVED. The op accepts it as
caller-supplied and explicitly declines to derive it (correlated-not-independent;
see its own negative spec). An ask to widen the op is out to the engine team. Until it
lands this ships the decline branch as one line: do NOT build a DoE-side
deriver against an unpublished recency threshold.

`_origin_worktree` IS REQUIRED. The op is `common_dir`-scoped, so without it
`resolve_op_repo_key()` raises INVALID_PARAMS engine-side, surfacing as
`HookDispatchError` -- caught below and degraded to a silent no-op, never a
crash. stdin's `cwd` is the same value the bash originals derived via
`git rev-parse --show-toplevel`.

GRACEFUL DEGRADATION -- REQUIRED. Every failure path exits 0 with empty
stdout: unresolvable engine, unimportable engine, unparseable stdin, op error.
A machine with no engine installed must never have its Stop bricked by this
file.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
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
    from _engine_root import resolve_claude_klabauter_root as _resolve_engine_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its sibling
    # _engine_root.py must still fail-open rather than crash on import.
    def _resolve_engine_root():  # type: ignore[misc]
        return None


def _transcript_for(payload: dict) -> str:
    """The subagent's own transcript on SubagentStop, this session's on Stop.

    Never falls back from `agent_transcript_path` to `transcript_path` on a
    subagent stop -- not even as an `or`. The decoy is a valid transcript for
    a different session, so the fallback would not fail loudly; it would write
    a confident verdict about the wrong session.
    """
    event = payload.get("hook_event_name") or ""
    if event == "SubagentStop" or payload.get("agent_id"):
        value = payload.get("agent_transcript_path")
        return value if isinstance(value, str) else ""
    value = payload.get("transcript_path")
    return value if isinstance(value, str) else ""


def main() -> int:
    raw = _read_stdin()

    root = _resolve_engine_root()
    if not root:
        return 0  # fail-open -- the engine is unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        import coordinator_core.hooks.receiver_state_sensor  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id") or ""
    transcript_path = _transcript_for(payload)
    if not session_id or not transcript_path:
        # The op treats both as required; a missing either is a silent no-op
        # engine-side anyway, so spend no dispatch on it.
        return 0

    params = {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "delegation_evidence": "false",
    }

    try:
        dispatch_from_hook(
            "hooks.receiver_state_sensor",
            params,
            origin_worktree=payload.get("cwd", ""),
        )
    except HookDispatchError:
        return 0  # any engine failure -> fail-open (never block a Stop)
    except Exception:
        return 0

    # The op always returns no_advisory(); this shim emits nothing, ever.
    return 0


if __name__ == "__main__":
    sys.exit(main())
