#!/usr/bin/env python3
"""Pre+PostToolUse:Bash naked-Python session-heartbeat dispatcher.

Replaces the former bash session-heartbeat Pre+PostToolUse:Bash dual
registration (last_activity heartbeat bookkeeping) with ONE `python3` hook
entry -- zero Git-Bash cold-start per Bash tool call on Windows (each bash.exe
spawn costs 200-500ms; this is the whole point).

DUAL REGISTRATION PRESERVED (do not collapse): this same file is registered
on BOTH PreToolUse:Bash and PostToolUse:Bash, mirroring the bash original --
the PreToolUse leg stamps recency at the START of a Bash call, the PostToolUse
leg stamps it again at COMPLETION (closes the F0 staleness hole for
long-running Bash commands -- see coordinator_core/hooks/session_heartbeat.py
docstring). The two legs are idempotent (same 60s throttle bucket, same
write), so this ONE stub file services both hook events unchanged -- no
event-name branching needed, since the op only reads session_id.

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the mapped params, relay its stdout. Claude-klabauter owns the
bookkeeping LOGIC (coordinator_core.hooks.session_heartbeat, registered under
the JSON-RPC method "hooks.session_heartbeat"). The engine is imported and run
IN-PROCESS via coordinator_core.ipc.dispatch_message -- no bash, no
`python3 -m` subprocess re-spawn -- so a whole Bash call pays exactly one
Python interpreter start per hook leg.

Contract (mirrors the former bash hook it replaces):
  stdin   -- Pre/PostToolUse JSON (session_id, tool_name, cwd, ...)
  stdout  -- ALWAYS empty (the op always returns no_advisory(); the product is
             the last_activity write side-effect on .git/coordinator-sessions/)
  exit 0  -- always (bookkeeping hook, never blocks tool calls)

stdin -> params mapping (op scope "common_dir" -- coordinator_core/hooks/
session_heartbeat.py's handler reads ONLY session_id via _payload.field();
see coordinator_core/ipc.py _OP_KEY_SCOPE -- "hooks.session_heartbeat":
"common_dir"):
    session_id  <- stdin["session_id"]
Missing/absent stdin keys map to "" -- mcp_tool's own "undeclared -> empty
string" convention; _payload.field() already treats "" as ABSENT, so an
absent key here is indistinguishable from one mcp_tool would have dropped.

_origin_worktree injection (REQUIRED -- this op is "common_dir"-scoped, unlike
the "none"-scoped postuse_advisory_dispatch reference stub): dispatch_message
resolves repo_root for the handler via git_common_dir(_origin_worktree), which
the handler needs to locate .git/coordinator-sessions/<sid>/meta.json. Without
this field, resolve_op_repo_key() raises ValueError (INVALID_PARAMS) inside
dispatch_message -- caught by this stub's own fail-open try/except, so it
degrades to a SILENT no-op (no heartbeat written), not a crash. Mirrors the
former bash hook's own `git rev-parse --show-toplevel` resolution: stdin's
`cwd` field (present on every PreToolUse/PostToolUse hook fire) is passed
through as _origin_worktree; resolve_request_repo() / git_common_dir() do the
actual worktree -> common-dir resolution engine-side (identical semantics to
the bash original's GIT_ROOT lookup, just resolved in-process instead of via a
git subprocess spawn per stub invocation).

Graceful degradation -- REQUIRED: any failure to resolve/import/run the claude-klabauter
engine, or to parse stdin, falls through to fail-open (exit 0, no stdout). A
missing sibling engine must NEVER brick a Bash tool call -- identical
philosophy to preuse-write-dispatch.py._resolve_claude_klabauter_root (kept in
lockstep deliberately; see W2-stub-contract.md).

The bash-to-Python cutover is complete; this dispatcher is the sole
registration on both PreToolUse:Bash and PostToolUse:Bash.
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
    EVERY Bash tool call (both Pre and Post legs), so a hang here stalls
    every subsequent tool call in the session -- highest-frequency hot path
    in this cohort, hence P1. Backstopped with a 2s threaded-join timeout,
    returning "" (the same fail-open value a JSON-decode failure already
    produces) instead of hanging.
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


def main() -> int:
    raw = _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.session_heartbeat triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time-per-invocation cost, in-process, still zero subprocess
        # spawns -- but each hook fire is a fresh process, so this import
        # cost recurs every fire, not just once per session.
        from coordinator_core.hooks import session_heartbeat as _op  # noqa: F401
        from coordinator_core.ipc import dispatch_message
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    params = {
        "session_id": payload.get("session_id", ""),
    }

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hooks.session_heartbeat",
        "params": params,
        # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- this op
        # writes .git/coordinator-sessions/<sid>/meta.json, so it needs
        # _origin_worktree to resolve the correct common .git directory.
        # stdin's "cwd" mirrors what the former bash hook derives via
        # `git rev-parse --show-toplevel`; absent/empty degrades to fail-open
        # (resolve_op_repo_key raises ValueError -> caught below -> exit 0,
        # no heartbeat written -- silent no-op, not a crash).
        "_origin_worktree": payload.get("cwd", ""),
    }

    try:
        response = asyncio.run(dispatch_message(msg))
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    result = response.get("result") if isinstance(response, dict) else None
    if result:  # {} (no_advisory) and None both fall through to no-output
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
