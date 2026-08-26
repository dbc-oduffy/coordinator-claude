#!/usr/bin/env python3
"""PostToolUse(Write|Edit|MultiEdit|NotebookEdit) naked-Python touched-files tracker.

Replaces the former bash PostToolUse registration
(dedup-append the edited file path into the per-session/per-agent touched.txt
bookkeeping records) with ONE `python3` hook entry -- zero Git-Bash cold-start
per edit on Windows (each bash.exe spawn costs 200-500ms; this is the whole
point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the mapped params, relay its stdout. Claude-klabauter owns the
bookkeeping LOGIC (coordinator_core.hooks.track_touched_files, registered under
the JSON-RPC method "hooks.track_touched_files"). The engine is imported and run
IN-PROCESS via coordinator_core.ipc.dispatch_from_hook (DR-175 -- the named
hook-dispatch seam, above the dispatch_message telemetry wrapper) -- no bash,
no `python3 -m` subprocess re-spawn -- so a whole edit pays exactly one Python
interpreter start.

Contract (mirrors the retired bash hook it replaces):
  stdin   -- PostToolUse JSON (session_id, tool_name, tool_input.file_path,
             agent_id, cwd, ...)
  stdout  -- NOTHING (this op is MUTATING bookkeeping, not advisory; it always
             returns no_advisory() == {} on every path)
  exit 0  -- always (the write side-effect is the product, never conveyed via
             stdout/exit code)

stdin -> params mapping (op scope "common_dir" -- REQUIRES _origin_worktree;
see coordinator_core/ipc.py _OP_KEY_SCOPE["hooks.track_touched_files"] ==
"common_dir". coordinator_core/hooks/track_touched_files.py's handler reads
session_id / tool_name / file_path / agent_id via _payload.field(), and its
repo_root arg (derived by dispatch_message from the "_origin_worktree" envelope
field) via git_common_dir(repo_root) -- the claude-klabauter engine itself resolves the
git-common-dir from ANY path inside the repo (git rev-parse --git-common-dir
with cwd=repo_root), so this stub does NOT need to run its own `git rev-parse
--show-toplevel` the way the bash original did; it hands the raw stdin `cwd`
straight through as `_origin_worktree` and lets the engine's own subprocess
resolve it -- zero subprocess spawns in this stub's own code):
    session_id   <- stdin["session_id"]
    tool_name    <- stdin["tool_name"]        (handler fast-exits unless one of
                                                 Write|Edit|MultiEdit|NotebookEdit
                                                 -- redundant with the hooks.json
                                                 matcher, defense-in-depth mirror
                                                 of the retired bash hook's own tool_name gate)
    file_path    <- stdin["tool_input"]["file_path"]   (NESTED -- the raw harness
                                                 PostToolUse payload nests the
                                                 edited path under tool_input, not
                                                 top-level; the legacy bash hook's
                                                 naive first-occurrence-anywhere
                                                 string extraction happened to land
                                                 on this same nested field because
                                                 it was the only "file_path" key in
                                                 the payload -- this stub reads the
                                                 same value by its real JSON path
                                                 instead of by accident)
    agent_id     <- stdin["agent_id"]         (raw subagent id; op-side resolves
                                                 to the canonical EM-side id itself
                                                 -- this stub does NOT replicate
                                                 resolve_subagent_identity(), that
                                                 logic lives in the claude-klabauter handler)
    _origin_worktree <- stdin["cwd"]          (JSON-RPC envelope field, NOT an op
                                                 param -- required because this op's
                                                 _OP_KEY_SCOPE is "common_dir")
Missing/absent stdin keys map to "" -- exactly what _payload.field() treats as
ABSENT; an absent/empty "cwd" makes resolve_request_repo() return None, which
makes resolve_op_repo_key() raise for this common_dir-scoped op -> a JSON-RPC
INVALID_PARAMS error response -> this stub's own fail-open path (result is None)
-> exit 0, no side effect. This mirrors the bash original's own
`GIT_ROOT=$(git rev-parse --show-toplevel) || exit 0` early-out, just via a
different failure seam (op-side key-resolution instead of a stub-side git call).

Graceful degradation -- REQUIRED: any failure to resolve/import/run the claude-klabauter
engine, or to parse stdin, falls through to fail-open (exit 0, no stdout, no
touched.txt mutation). A missing sibling engine must NEVER brick an edit --
identical philosophy to preuse-write-dispatch.py._resolve_claude_klabauter_root (kept in
lockstep deliberately; see W2-stub-contract.md).

NOTE (historical): during the bash->Python cutover, the retired bash hook and
this dispatcher briefly co-registered. Both firing concurrently was a real
double-write risk for this MUTATING op (unlike the advisory ops, where
duplicate emission is harmless) -- that risk was accepted for the duration of
the transition window because
_dedup_append/_dedup_append_locked on the claude-klabauter side and cs_atomic_dedup_append
on the bash side are BOTH dedup-on-write, so a concurrent double-fire produces
at most a redundant no-op append, never a duplicate line in touched.txt.
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


def main() -> int:
    raw = _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- claude-klabauter unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.track_touched_files triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time-per-invocation cost, in-process, still zero subprocess
        # spawns from this stub -- but each hook fire is a fresh process, so
        # this import cost recurs every fire, not just once per session.
        from coordinator_core.hooks import track_touched_files as _op  # noqa: F401
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
    file_path = ""
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path", "") or ""

    params = {
        "session_id": payload.get("session_id", ""),
        "tool_name": payload.get("tool_name", ""),
        "file_path": file_path,
        "agent_id": payload.get("agent_id", ""),
    }

    # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- REQUIRED.
    # Handed through raw; the engine resolves git-common-dir itself from
    # whatever cwd the harness reports (no subprocess spawn in this stub).
    # dispatch_from_hook builds the {"jsonrpc", "id", "method", "params"}
    # envelope itself and stamps _origin_worktree only when non-empty --
    # matches this stub's own payload.get("cwd", "") semantics unchanged.
    try:
        dispatch_from_hook(
            "hooks.track_touched_files",
            params,
            origin_worktree=payload.get("cwd", ""),
        )
    except HookDispatchError:
        return 0  # any engine failure -> fail-open (never brick an edit)

    # No stdout relay: this op is MUTATING bookkeeping (dedup-append into
    # touched.txt), never advisory -- it always returns no_advisory() == {}.
    # The contract is "stdout NOTHING" (see module docstring), enforced
    # structurally here by never inspecting/relaying the response, not
    # incidentally via `{}`'s falsiness under `if result:`.
    return 0


if __name__ == "__main__":
    sys.exit(main())
