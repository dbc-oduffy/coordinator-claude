#!/usr/bin/env python3
"""PreToolUse(WebFetch|WebSearch) naked-Python research-delegation advisory dispatcher.

Replaces the former bash suggest-sonnet-research PreToolUse registration
(nudge the EM to delegate web research to dedicated skills/agents rather than
running ad-hoc research as Opus) with ONE `python3` hook entry -- zero Git-Bash
cold-start per tool call on Windows (each bash.exe spawn costs 200-500ms; this
is the whole point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the engine repo, hand it the mapped params, relay its stdout. The engine repo owns the
advisory LOGIC (coordinator_core.hooks.suggest_sonnet_research, registered under
the JSON-RPC method "hooks.suggest_sonnet_research"). The engine is imported and
run IN-PROCESS via coordinator_core.ipc.dispatch_from_hook (DR-175 -- the named
hook-dispatch seam, above the dispatch_message telemetry wrapper) -- no bash,
no `python3 -m` subprocess re-spawn -- so a whole PreToolUse fire pays exactly one
Python interpreter start.

Contract (mirrors the former bash hook it replaces):
  stdin   -- PreToolUse JSON (tool_name, tool_input, session_id, agent_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope (allow_advisory shape) unless
             agent_id resolves to a subagent (suppressed via no_advisory --
             op-side resolve_subagent_identity, bare-hex or named-teammate
             shape); NOTHING in that suppressed case
  exit 0  -- always (advisory conveyed via stdout, never exit code; this hook
             is advisory-only and never blocks)

stdin -> params mapping (op scope "none" -- no _origin_worktree needed; see
coordinator_core/hooks/suggest_sonnet_research.py's handler -- it reads ONLY
agent_id via _payload.field(). The op does NOT reproduce the bash hook's
query-specific ready-to-paste dispatch-brief extraction (tool_input.url /
tool_input.query) -- that behavior was intentionally simplified away in the
engine repo's port per the op's own docstring/negative-spec; the engine repo's op emits a
fixed advisory message (with/without deep-research-plugin variants) rather
than a URL/query-parameterised one. tool_name/tool_input are therefore NOT
part of this op's params -- they are not read by the handler):
    agent_id  <- stdin["agent_id"]
Missing/absent stdin keys map to "" -- mcp_tool's own "undeclared -> empty
string" convention; _payload.field() already treats "" as ABSENT, so an
absent key here is indistinguishable from one mcp_tool would have dropped.

Graceful degradation -- REQUIRED: any failure to resolve/import/run the engine
repo, or to parse stdin, falls through to fail-open (exit 0, no stdout). A
missing sibling engine must NEVER brick a tool call -- identical philosophy to
preuse-write-dispatch.py._resolve_claude_klabauter_root (kept in lockstep deliberately;
see W2-stub-contract.md).

The bash-to-Python cutover is complete; this dispatcher is the sole
registration in hooks.json.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded read: a bare sys.stdin.read() can block forever if the harness
    never closes stdin's write end; this backstops with a timeout instead of
    hanging the hook chain."""
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
    # Fallback for a hook script deployed without its sibling _engine_root.py:
    # must fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    raw = _read_stdin()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine repo unresolvable on this machine

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        # Importing this triggers coordinator_core.hooks package __init__,
        # which registers all advisory + bookkeeping ops as a side-effect --
        # a per-fire cost (each hook fire is a fresh process), not one-time.
        from coordinator_core.hooks import suggest_sonnet_research as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    params = {
        "agent_id": payload.get("agent_id", ""),
    }

    # scope "none" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- no
    # _origin_worktree required; this op accesses no repo-specific state
    # (only an in-process coordinator content-root resolution, self-contained).
    try:
        result = dispatch_from_hook("hooks.suggest_sonnet_research", params)
    except HookDispatchError:
        return 0  # any engine failure -> fail-open (never brick a tool call)

    if result:  # {} (no_advisory) and None both fall through to no-output
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
