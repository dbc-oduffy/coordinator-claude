"""PreToolUse(Agent) naked-Python advisory dispatcher — named-dispatch report delivery.

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the engine plane, hand it the raw payload, relay its stdout. The engine plane owns
the ADVISORY LOGIC (coordinator_core.hooks.nudge_named_agent_report_delivery,
registered under the JSON-RPC method hooks.nudge_named_agent_report_delivery).
The engine is imported and run IN-PROCESS via coordinator_core.ipc.dispatch_from_hook
(DR-175 -- the named hook-dispatch seam, above the dispatch_message telemetry wrapper)
-- no bash, no python3 -m subprocess re-spawn -- so a whole PreToolUse fire pays
exactly one Python interpreter start.

Why this hook exists: passing `name` to the Agent tool converts the dispatch into
an Agent-teams TEAMMATE, whose plain-text output is never delivered to the
dispatcher (only an explicit SendMessage to "main" reaches it). A brief that ends
"Report back: ..." — correct for an unnamed dispatch — silently produces nothing
from a named one; the EM sees only an idle_notification and, read as failure,
redispatches and races two writers onto the same files. This advisory fires at
dispatch time, where the choice is being made, and names both working shapes
(drop the name, or brief the SendMessage) rather than arguing against naming.

Deliberately NO shebang: hooks.json invokes this file through an explicit
`python3 -c ... runpy.run_path(...)` wrapper, so it is never exec'd directly.

Contract (mirrors the engine op's own contract):
  stdin   -- PreToolUse JSON (tool_name, tool_input, session_id, cwd, ...)
  stdout  -- one hookSpecificOutput allow+additionalContext envelope when a named
             Agent dispatch's brief carries no SendMessage-to-main delivery
             instruction; NOTHING otherwise (silent pass)
  exit 0  -- always. Never denies, never rewrites input -- purely advisory, so
             there is no fail-closed leg at all (contrast
             nudge-foreground-agent-dispatch.py, which reserves a local deny for
             the one payload shape it can prove foreground without the engine;
             this hook has no analogous provably-actionable shape to fail closed
             on, and the op never denies even when the engine IS reachable).

stdin -> params mapping: tool_name (flattened top-level) and tool_input (raw,
unflattened -- the op reads tool_input["name"] / tool_input["prompt"] directly,
and `field()` would stringify a dict, so tool_input must be forwarded as the
complete dict, not merged into flattened scalars the way the sibling foreground
shim does).

The op (coordinator_core/hooks/nudge_named_agent_report_delivery.py) is NOT
scoped (no _origin_worktree / common_dir requirement) -- its handler signature
defaults repo_root=None and reads nothing from disk, so this shim omits the
`_origin_worktree` field the common_dir-scoped sibling op requires.

Graceful degradation -- REQUIRED and unconditional: any failure to resolve/
import/run the engine plane, or a malformed/absent payload, falls through to
fail-open silent pass (exit 0, no stdout). An unreachable engine, or a
transport hiccup, must never brick an Agent dispatch to deliver a nag that is
advisory in the first place.

Spec backlink: the cross-repo ask requesting this wiring, dated 2026-07-30,
"wire-named-agent-report-delivery-hook" (cross-repo/inbox/).
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

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open silent pass -- engine plane unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks import nudge_named_agent_report_delivery as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open silent pass

    params = {
        "tool_name": payload.get("tool_name", ""),
        # Forwarded UNFLATTENED and complete: the op reads tool_input["name"] and
        # tool_input["prompt"] raw, so a flattened scalar will not work here.
        "tool_input": tool_input,
    }

    # Not scoped (see module docstring): no _origin_worktree forwarded, matching
    # the op's own repo_root=None default.
    try:
        result = dispatch_from_hook("hooks.nudge_named_agent_report_delivery", params)
    except HookDispatchError:
        return 0  # any engine failure -> fail-open silent pass

    if result:  # {} (no_advisory) and None both fall through to no-output
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
