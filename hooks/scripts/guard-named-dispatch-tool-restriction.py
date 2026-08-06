"""guard-named-dispatch-tool-restriction.py -- standalone script, formerly a
registered PreToolUse hook on matcher: Agent.

DEREGISTERED FROM `hooks.json` (single-emitter fold-in, 2026-07-31): this
script's own `updatedInput` emission (a `name`-key strip) used to race
`enforce-agent-dispatch-mode.py`'s single merged `updatedInput` emission on
the SAME `Agent` matcher -- same-event PreToolUse hooks run in parallel with
undefined completion order, and `updatedInput` is last-writer-wins, so
exactly one hook's rewrite was silently clobbered on a named Explore/Plan
dispatch that ALSO carried a mode-elevation/sidecar/role-framing/worktree-
isolation trigger. Fix: the pure decision logic below now lives in
`_named_dispatch_strip.compute_named_dispatch_result`, and
`enforce-agent-dispatch-mode.py` (this matcher's sole `updatedInput` emitter)
calls it directly and folds the result into its own single merge, as
"Concern F". `Agent` was this script's only matcher, so unlike
`strip-worktree-isolation.py` (kept registered on `Workflow`, a distinct
matcher the Agent-only merge path cannot reach) there is no matcher left
where this script is a legitimate standalone emitter -- it is fully
deregistered from `hooks.json`.

This script itself is UNCHANGED IN BEHAVIOUR and kept on disk: it still
implements the full standalone stdin-JSON / stdout-JSON / exit-code contract
below, now by calling the shared pure computation instead of inlining it, so
its dedicated test suite
(`coordinator/tests/test_guard_named_dispatch_tool_restriction.py`, which
drives it directly via subprocess) keeps exercising the real decision logic
unmodified in intent. It is simply never invoked by the live hook seam
anymore.

Everything below this point is the ORIGINAL module docstring, preserved for
the rationale behind the decision this script (and the shared module it now
delegates to) makes.

Closes the named-dispatch tool-restriction hole: passing `name:` on an Agent
dispatch routes it to a teammate spawn that keeps the resolved built-in agent
definition only if `source !== "built-in" && source !== "plugin"`. `Explore`
and `Plan` are both built-in, so naming either fabricates a synthetic
definition with `tools: ["*"]` -- the agent's own `omitClaudeMd`, system
prompt, and `disallowedTools` are all discarded, and nothing at the call site
signals it. A named `Explore` is therefore not read-only, silently.

Framing (PM correction, 2026-07-30): this is NOT a security boundary. The
mechanism is real but the harm is an eager agent exceeding what the call site
implies, on a git-tracked, recoverable tree -- the "defends against eager,
not adversary" class (docs/wiki/bash-guard-threat-model.md), not a safety
chunk. The defect that matters is correctness and cost: the dispatch bills
~48.6k tokens instead of ~17.6k and does not do what its call site says.
Do not restate a safety framing in this guard's message, commit, or any
doctrine entry that cites it -- overstating severity is how a guard earns a
bypass.

Do NOT author a named alternative to `Explore`. Naming IS the defect: a new
named agent intended as an Explore-equivalent routes through the identical
teammate-spawn path and reintroduces the same hole under a new label, while
adding a roster entry whose boot cost the concurrent boot-doctrine plan is
cutting. The fix is to stop dispatches being named, not to supply a better
name -- this guard's default action (strip `name`, let the dispatch through)
is the whole fix.

Shape, authoring precedent: standalone script, modeled structurally on
`strip-worktree-isolation.py` (single-key strip via `updatedInput`, offer
message via `additionalContext`) rather than the
`nudge-foreground-agent-dispatch.py` engine-shim pattern. Chosen
because the predicate here is pure, static, and total over `tool_input`'s
known shape (two literal `subagent_type` values, one key's presence) --
there is no session-scoped calibration state or cross-process adjudication
to justify a round-trip to the engine, and the fail-closed requirement below
is far simpler to guarantee without one.

SHAPE -- offer, not mistrust, for the caller's ordinary mistake. Fires when
`subagent_type` is `Explore` or `Plan` AND `name` is present. Default action
strips `name` and lets the dispatch through, via `updatedInput` (which
REPLACES `tool_input` wholesale -- `prompt` and `subagent_type` are carried
forward in full, not just the stripped field, mirroring the trap
`nudge-foreground-agent-dispatch.py` documents in its own header). The
`additionalContext` note leads with what the caller gets (still read-only,
~31k fewer tokens) and only then names the escape hatch -- pick an existing
non-built-in type whose definition survives naming -- never a licence to
create one.

FAIL-CLOSED FOR THE GUARD'S OWN FAILURE -- the second, non-optional register.
The offer-shape above is right for the CALLER's mistake; it is wrong for
this guard's own. PreToolUse hooks on this seam are permissive by default
when they error (see the sibling scripts' fail-open legs), which would
silently restore `tools: ["*"]` here if this guard's own detection or
rewrite construction failed. So: ONLY the narrow, provably-safe legs below
(no stdin, unparsable JSON, non-dict payload, non-"Agent" tool_name,
`tool_input` not a dict, `subagent_type` not Explore/Plan, `name` absent)
return silently (no stdout, exit 0) -- normal pass, not a failure. Once this
guard has determined the case IS a named Explore/Plan dispatch, any
condition that would prevent it from constructing a complete, faithful
`updatedInput` (an unrecognised key in `tool_input` this guard does not know
how to carry forward, or any other unhandled exception while building the
rewrite) emits `permissionDecision: deny` with the same offer message,
never a silent pass. `_KNOWN_AGENT_TOOL_INPUT_KEYS` is the explicit
allowlist that makes "unrecognised key" a checkable condition rather than an
implicit assumption -- a future Agent tool_input field this guard has not
been taught about must not be silently dropped by the strip-and-forward
rewrite; it denies instead.

Only `Explore` and `Plan` are in scope. Every other built-in `subagent_type`
either already carries its own restrictions defensibly, or (for a
non-built-in / non-plugin type) survives naming with its definition intact
-- there is no hole there, and firing on them would make this a nag rather
than an offer.

Override: none. Unlike `strip-worktree-isolation.py` (which bans a value
outright, with a sentinel escape hatch for a genuinely exceptional case),
there is no legitimate reason to want a named, tools-unrestricted `Explore`
or `Plan` -- the escape hatch IS the strip-and-continue default action, not
a bypass of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _named_dispatch_strip import compute_named_dispatch_result  # noqa: E402


def _deny(message: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")


def _strip_and_allow(merged: dict, message: str) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": merged,
            "additionalContext": message,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        # Cannot even read stdin -- there is no dispatch to classify, so
        # this is a genuine pass, not a guard failure.
        return 0
    if not raw:
        return 0

    try:
        data: Any = json.loads(raw)
    except Exception:
        # Unparsable payload -- same as above, nothing to classify.
        return 0
    if not isinstance(data, dict):
        return 0

    tool_name = data.get("tool_name")
    if tool_name != "Agent":
        return 0

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    # Delegate the decision to the shared, pure computation (see module
    # docstring above, and `_named_dispatch_strip.py`) -- `None` means
    # nothing to do (ordinary pass), `("deny", ...)` and `("strip", ...)`
    # mirror the exact two decisions this script used to make inline.
    result = compute_named_dispatch_result(tool_input)
    if result is None:
        return 0

    action, merged, message = result
    if action == "deny":
        _deny(message)
        return 0
    _strip_and_allow(merged, message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
