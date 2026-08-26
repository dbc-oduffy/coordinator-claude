#!/usr/bin/env python3
"""enforce-agent-dispatch-mode.py -- PreToolUse hook, matcher: Agent (naked-Python port).

Byte-faithful port of enforce-agent-dispatch-mode.sh. Read that file's header
comment for the full concern breakdown, DEC references, sequencing assumption,
and fail-open contract -- this port preserves every one of those conditions
verbatim; only the extraction/emission MECHANISM changed (in-process JSON
handling instead of jq/python subprocess fan-out per Agent-tool dispatch,
the Windows spawn-tax motivation for this whole naked-Python migration wave).

Concern A -- mode elevation: raise a dispatched child agent's permission mode
up to an autonomous parent's posture (auto/dontAsk/bypassPermissions), never
lower. Absent child mode is treated as acceptEdits (rank 2).

Catering (run-report sidecar provisioning, contract-block injection, role
framing, and the named-teammate sidecar-fill clause) is RETIRED from this
leg (2026-08-21, SubagentStart catering cutover): that whole DR-091/W0-seam/
Concern-D/named-teammate family moved to `hooks.cater_subagent_start`,
relayed off the `SubagentStart` event by `track-dispatched-agents.py`
(`dispatch_ops_from_hook`, catering op second, after the bookkeeping op that
writes the back-pointer catering's own type resolution reads). This hook
keeps ONLY the concerns below that are inherently PreToolUse-shaped --
mode elevation must land before the child's first tool call, and the
worktree/named-dispatch/foreground-reroute strips all rewrite the SAME
Agent-tool-call `tool_input` this hook already owns emission for.

Emit-gate (single-emitter fold-in, widened): (mode-elevation-needed) OR
(worktree-isolation-stripped) OR (named-dispatch-stripped) OR
(foreground-dispatch-rerouted). None -> silent pass (exit 0, no stdout). Any
-> permissionDecision "allow" plus updatedInput carrying the FULL original
tool_input with whichever mutations apply layered on.

Escape hatch: COORDINATOR_AGENT_MODE_OK set (any non-empty value) in env ->
silent pass. Applies to mode-elevation only, per the oracle -- the escape
hatch short-circuits Concern A's computation only, exactly as the oracle's
early-exit does; it does NOT gate Concerns E/F/G, which are computed
unconditionally below (same discipline the old Concern D role-framing leg
followed before its retirement above).

Fail-open discipline: every optional leg below degrades to "nothing to add"
on any internal failure -- it NEVER blocks or denies the spawn on its own
account (Concerns F and G's own fail-CLOSED legs are the sole exceptions,
and those wins are documented at their own call sites below). This hook
exits 0 unconditionally; allow/advisory is conveyed via stdout only.

CRITICAL: updatedInput carries the FULL original tool_input with mode
overwritten and/or the E/F/G rewrites applied -- never a partial object. See
the oracle's SEQUENCING ASSUMPTION: this remains the ONLY updatedInput
emitter on the Agent matcher for the concerns above (nudge-foreground-agent-
dispatch's deny still wins via deny-precedence over this hook's allow --
unaffected by this port).

Concern E -- worktree-isolation strip (single-emitter fix, 2026-07-31): this
hook used to race `strip-worktree-isolation.py` for `updatedInput` on any
Agent dispatch carrying BOTH `isolation: "worktree"` AND a mode-elevation/
sidecar/role-framing trigger -- Claude Code runs same-event PreToolUse hooks
in parallel with undefined completion order, and `updatedInput` is
last-writer-wins, so exactly one hook's rewrite silently clobbered the
other's (confirmed live on harness 2.1.220: either the worktree strip was
silently un-done, or the mode elevation / sidecar offer / injected contract
/ role framing were silently dropped). Fix: this hook now ALSO computes the
worktree-isolation strip itself, via `_worktree_isolation_strip.compute_strip`
(the same pure, shared computation `strip-worktree-isolation.py` uses for
`Workflow` -- neither call site re-implements the strip/override logic), and
layers it onto the SAME `merged` dict / SAME single emission as every other
concern here. `strip-worktree-isolation.py` is narrowed to `Workflow` only
(its `tool_input` has no `prompt` key, so it cannot fold into this hook's
Agent-only merge path and stays a standalone hook for that tool). This is
now the sole `updatedInput` emitter on the Agent matcher for mode-elevation
AND worktree-isolation stripping.

Concern F -- named-dispatch (`name` key) strip (single-emitter fold-in,
2026-07-31, follow-up to Concern E): this hook used to race
`guard-named-dispatch-tool-restriction.py` for `updatedInput` on a named
Explore/Plan Agent dispatch that ALSO carried a mode-elevation/sidecar/
role-framing/worktree-isolation trigger -- the identical parallel-hook
clobber class Concern E closed for the worktree/mode-elevation pair, now
closed here too. Fix: this hook now ALSO computes the named-dispatch strip
itself, via `_named_dispatch_strip.compute_named_dispatch_result` (the same
pure computation `guard-named-dispatch-tool-restriction.py` used inline,
extracted so neither call site re-implements the restricted-type / unknown-
key / deny logic), and layers a "strip" result onto the SAME `merged` dict /
SAME single emission as every other concern here. A "deny" result (the
guard's own fail-closed leg for an unrecognised `tool_input` key or an
internal failure) short-circuits this hook's `main()` immediately, BEFORE
any other concern is merged in -- the guard's fail-closed contract must win
outright, not get silently folded into an "allow" that also happens to
strip `name`. `guard-named-dispatch-tool-restriction.py` is deregistered
from `hooks.json`'s `Agent` matcher entirely (it was its only matcher, so
unlike `strip-worktree-isolation.py` there is no distinct matcher left where
it is a legitimate standalone emitter); the script itself stays on disk,
still delegating to the same shared module, so its own dedicated test suite
(coordinator/tests/test_guard_named_dispatch_tool_restriction.py) keeps
exercising the real decision logic via direct subprocess invocation.

Concern G -- foreground-dispatch reroute (single-emitter fold-in, RE-LAND,
2026-07-31, follow-up to Concern F): `nudge-foreground-agent-dispatch.py`
used to independently relay the engine's `hooks.nudge_foreground_agent_
dispatch` REROUTE-gate result (`updatedInput` rewriting a foreground
`run_in_background: false` Agent dispatch to `true`) on this SAME Agent
matcher -- the identical parallel-hook clobber class Concern E/F already
closed, confirmed live on harness 2.1.220. A 2026-07-30 revert concluded,
wrongly, that `updatedInput` does not bind `run_in_background` for the
Agent tool; the real cause was this race, and a fresh live probe with the
reroute computed as a single-emitter fold-in (no competing emitter) showed
the EM regaining control 32.3s BEFORE the subagent finished -- genuinely
backgrounded. Fix: this hook now ALSO computes the foreground-reroute
decision itself, via `_foreground_dispatch_strip.compute_foreground_
reroute` (a byte-faithful pure-Python port of that op -- three-state
`run_in_background` handling, durable `.harness-bg-capable` calibration,
`.foreground-ok` escape hatch -- ported rather than called into in-process
specifically to avoid the ~18ms engine hooks-package import on a path every
Agent dispatch already reaches via this hook's own unconditional Concern
E/F/G computation above; the sidecar-provisioning subprocess spawn this
rationale used to also avoid no longer applies -- sidecar provisioning is
retired from this leg entirely, not merely avoided on this path), and layers
a "reroute" result (`run_in_background: true` plus an `additionalContext`
notice) onto the SAME `merged` dict / SAME single emission as every other
concern here. A "deny" result (no safely rewritable `tool_input` -- missing
or no `prompt` key) short-circuits `main()` immediately, same precedence
tier as Concern F's own deny -- never silently folded into an allow. The
notice fires on EVERY reroute, never bark-once: a suppressed once-per-
session notice is exactly how the 2026-07-30 non-binding race went a whole
session undetected, since the notice and the tool result were the only
feedback channels and both asserted success. `nudge-foreground-agent-
dispatch.py` is deregistered from `hooks.json`'s `Agent` matcher entirely
(same reasoning as Concern F); the script and the engine's own op stay on
disk as this algorithm's reference implementation, each still exercised by
its own dedicated test suite via direct invocation/subprocess. This hook is
now the sole `updatedInput` emitter on the Agent matcher for mode-elevation,
worktree-isolation stripping, named-dispatch stripping, AND foreground-
dispatch rerouting.

Concern I -- teammate-name path-segment refusal: a `name` value carrying a
path separator (e.g. "feature/auth-review") resolves a subagent_type and
passes provisioning eligibility while defeating the downstream canonical-
agent-id shape the engine expects -- neither Concern F's confinement leg
(Explore/Plan) nor its delivery leg (reporting types) catches this, since
both only fire for their own audited type populations and this defect
applies to ANY `name`, regardless of subagent_type. Refuses rather than
sanitizes (a silently mangled name would dispatch under a different name
than the one asked for), checked first in the deny-precedence chain -- it
wins outright over every other concern, same tier discipline as Concern
F/G's own fail-closed legs.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

# --- Concern I: teammate-name path-segment refusal ---
#
# `name` feeds the engine's canonical-agent-id builder downstream, which
# formats it directly into the teammate's canonical agent id and, from
# there, its sidecar path segment -- with no sanitization step of its own.
# A name containing a path separator (e.g. "feature/auth-review", the shape
# anyone doing branch-scoped review naturally reaches for) resolves a type
# and passes provisioning eligibility while defeating the engine's
# named-teammate-agent-id predicate (the canonical-id shape it expects never
# matches an id carrying an embedded `/`). This is NOT the same failure mode
# `_named_dispatch_strip.py` guards against (Explore/Plan confinement loss,
# reporting-agent report loss) -- it applies regardless of subagent_type,
# to any dispatch carrying a `name` at all, and refuses rather than
# sanitizes: silently mangling the name would let the dispatch through under
# a DIFFERENT name than the one asked for, which is worse than refusing.
_TEAMMATE_NAME_PATH_UNSAFE_RE = re.compile(r"[\\/]")


def _teammate_name_deny_message(name: str) -> Optional[str]:
    match = _TEAMMATE_NAME_PATH_UNSAFE_RE.search(name)
    if not match:
        return None
    offending_char = match.group(0)
    prose = (
        "[named-dispatch guard] denied: `name` contains {char!r}, illegal "
        "in a path segment -- it becomes the teammate's canonical id and "
        "sidecar path. Retry using only letters, digits, `.`, `_`, `@`, or "
        "`-` (e.g. \"feature-auth-review\")."
    ).format(char=offending_char)
    return render(compose(prose))

# --- Autonomy rank table (least -> most) ---
# plan=0 < default=manual=1 < acceptEdits=2 < auto=3 < dontAsk=4 < bypassPermissions=5
_MODE_RANK = {
    "plan": 0,
    "default": 1,
    "manual": 1,
    "acceptEdits": 2,
    "auto": 3,
    "dontAsk": 4,
    "bypassPermissions": 5,
}


def _mode_rank(mode: str) -> int:
    return _MODE_RANK.get(mode, -1)


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _message_envelope import compose, render  # noqa: E402
except Exception:
    # Same defensive fallback as the strips below -- a copied/deployed hook
    # without its sibling _message_envelope.py must still fail-open (Concern
    # I simply never fires) rather than crash on import.
    def compose(prose, alternative=None, anchor=None):  # type: ignore[no-redef]
        class _Message:  # minimal stand-in, unused beyond render() below
            pass

        msg = _Message()
        msg.prose = prose  # type: ignore[attr-defined]
        return msg

    def render(message):  # type: ignore[no-redef]
        return getattr(message, "prose", "")

try:
    from _worktree_isolation_strip import compute_strip as _compute_worktree_strip  # noqa: E402
except Exception:
    # Same defensive fallback as _engine_root above -- a copied/deployed
    # hook without its sibling _worktree_isolation_strip.py must still
    # fail-open (Concern E simply never fires) rather than crash on import.
    def _compute_worktree_strip(tool_input: dict):  # type: ignore[no-redef]
        return None

try:
    from _named_dispatch_strip import (  # noqa: E402
        compute_named_dispatch_result as _compute_named_dispatch,
    )
except Exception:
    # Same defensive fallback as above -- a copied/deployed hook without its
    # sibling _named_dispatch_strip.py must still fail-open (Concern F
    # simply never fires) rather than crash on import. NOTE: this is a
    # fail-open for THIS hook's own missing-sibling deploy failure, distinct
    # from the module's own internal fail-closed contract (an unrecognised
    # tool_input key on a real named Explore/Plan dispatch) which only
    # applies once the module is actually importable and running.
    def _compute_named_dispatch(tool_input: dict):  # type: ignore[no-redef]
        return None

try:
    from _plan_path_bridge import (  # noqa: E402
        extract_plan_path as _extract_plan_path,
        record_plan_path as _record_plan_path,
    )
except Exception:
    # Same defensive fallback as the strips below -- a copied/deployed hook
    # without its sibling _plan_path_bridge.py must still fail-open (Concern H
    # simply never fires) rather than crash on import.
    def _extract_plan_path(prompt: str) -> Optional[str]:  # type: ignore[no-redef]
        return None

    def _record_plan_path(  # type: ignore[no-redef]
        session_id: str, subagent_type: str, plan_path: str, cwd: Optional[str]
    ) -> bool:
        return False

try:
    from _foreground_dispatch_strip import (  # noqa: E402
        compute_foreground_reroute as _compute_foreground_reroute,
    )
except Exception:
    # Same defensive fallback as above -- a copied/deployed hook without its
    # sibling _foreground_dispatch_strip.py must still fail-open (Concern G
    # simply never fires) rather than crash on import.
    def _compute_foreground_reroute(run_in_background, session_id, tool_input, cwd):  # type: ignore[no-redef]
        return None

def main() -> int:
    raw = sys.stdin.read()

    try:
        data: Any = json.loads(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    tool_input = data.get("tool_input")
    tool_input_dict = tool_input if isinstance(tool_input, dict) else {}

    # --- Concern I: teammate-name path-segment refusal. Computed
    # unconditionally, before anything else -- it is not a mode-elevation
    # concern, must not be gated by COORDINATOR_AGENT_MODE_OK, and applies
    # regardless of subagent_type (unlike Concern F, which only strips/denies
    # for the Explore/Plan/reporting-type populations). A non-None result is
    # this hook's own fail-closed leg and wins outright over every other
    # concern -- checked first in the precedence chain below.
    teammate_name_deny_message: Optional[str] = None
    _name_value = tool_input_dict.get("name")
    if isinstance(_name_value, str):
        try:
            teammate_name_deny_message = _teammate_name_deny_message(_name_value)
        except Exception:
            teammate_name_deny_message = None

    # --- Escape hatch: deliberate down-scope dispatch (e.g. read-only scout
    # from YOLO session). Short-circuits Concern A computation only, matching
    # the oracle's early-exit placement for that concern (before any Concern
    # A computation). It deliberately does NOT short-circuit Concerns E/F/G
    # below: COORDINATOR_AGENT_MODE_OK is a permission-mode escape hatch, not
    # a doctrine/rewrite one, and letting it suppress those strips would
    # silently un-strip every session that sets it.
    mode_ok_escape = bool(os.environ.get("COORDINATOR_AGENT_MODE_OK"))

    parent_mode = data.get("permission_mode") or ""
    child_mode = tool_input_dict.get("mode") or ""

    need_mode_elevation = False

    if not mode_ok_escape:
        # --- Concern A gate: mode-elevation-needed ---
        if parent_mode:
            parent_rank = _mode_rank(parent_mode)
            child_effective = child_mode or "acceptEdits"
            child_rank = _mode_rank(child_effective)
            if parent_rank >= 0 and child_rank >= 0 and parent_rank >= 3 and child_rank < parent_rank:
                need_mode_elevation = True

    # --- Concern E: worktree-isolation strip (single-emitter fix, see module
    # docstring). Computed unconditionally -- it is not a
    # mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch. Pure computation; None when
    # there is nothing to strip (isolation absent, any non-"worktree" value,
    # or the override sentinel is active).
    # Review: code-reviewer -- the three _compute_* call sites relied entirely
    # on callee-internal fail-open discipline with no defensive try/except at
    # the call site; an uncaught exception here would produce no valid JSON
    # on stdout (fail-CLOSED on a hook whose whole design is fail-open).
    # Degrade to None on any exception, matching the ImportError fallback's
    # own contract.
    try:
        worktree_strip_result = _compute_worktree_strip(tool_input_dict)
    except Exception:
        worktree_strip_result = None

    # --- Concern F: named-dispatch (`name` key) strip (single-emitter
    # fold-in, see module docstring). Computed unconditionally, like Concern
    # E -- it is not a mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch. A "deny" result is this
    # module's own fail-closed leg (unrecognised tool_input key, or an
    # internal failure, on a genuinely named Explore/Plan dispatch) and MUST
    # win outright over every other concern -- short-circuit immediately,
    # before folding anything else into `merged`, exactly as the standalone
    # guard used to (its deny was never conditional on the other concerns'
    # state).
    try:
        named_dispatch_result = _compute_named_dispatch(tool_input_dict)
    except Exception:
        named_dispatch_result = None

    # --- Concern G: foreground-dispatch reroute (single-emitter fold-in,
    # RE-LAND, see module docstring). Computed unconditionally, like Concern
    # E/F -- it is not a mode-elevation concern and must not be gated by the
    # COORDINATOR_AGENT_MODE_OK escape hatch (its own, distinct escape hatch
    # is the `.foreground-ok` sentinel, checked inside the pure computation).
    # A "deny" result (no safely rewritable tool_input) MUST win outright
    # over every other concern, same precedence tier as Concern F's own
    # fail-closed leg.
    try:
        foreground_result = _compute_foreground_reroute(
            tool_input_dict.get("run_in_background"),
            data.get("session_id"),
            tool_input_dict,
            data.get("cwd"),
        )
    except Exception:
        foreground_result = None

    # --- Concern H: plan-path record for a plan-derivable lens dispatch.
    # Pure side effect, deliberately outside the emit-gate below: this event is
    # the only one that sees the child's prompt, and SubagentStart -- the only
    # event that caters -- carries no prompt at all, so the `plan_path` the
    # provisioning engine's plan-derivable leg gates on has to cross between
    # them on disk. Nothing about this leg reaches `updatedInput` or the
    # decision, so it neither joins nor widens the emit-gate. Fail-open: the
    # recorder swallows every failure and returns False, and a miss means the
    # lens's sidecar falls through to the session-keyed home exactly as it does
    # without this leg.
    try:
        _record_plan_path(
            str(data.get("session_id") or ""),
            str(tool_input_dict.get("subagent_type") or ""),
            _extract_plan_path(str(tool_input_dict.get("prompt") or "")) or "",
            data.get("cwd"),
        )
    except Exception:
        pass

    # --- Single-emitter invariant: exactly ONE hookSpecificOutput object is
    # ever built and written, at the single write call site at the bottom of
    # this function -- a "deny" (Concern F's or Concern G's own
    # fail-closed leg) and an "allow" (every other concern) are mutually
    # exclusive outcomes of the SAME decision, computed into `out` below,
    # never two independent write sites racing to be the last one out.
    out: Optional[dict[str, Any]] = None

    if teammate_name_deny_message is not None:
        # Concern I's own fail-closed leg -- wins outright over every other
        # concern, checked before Concern F/G's denies since a name that
        # cannot be a path segment is a structural defect regardless of
        # subagent_type or what Concern F would otherwise decide about it.
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": teammate_name_deny_message,
            }
        }
    elif named_dispatch_result is not None and named_dispatch_result[0] == "deny":
        # A "deny" result is this module's own fail-closed leg (unrecognised
        # tool_input key, or an internal failure, on a genuinely named
        # Explore/Plan dispatch) and MUST win outright over every other
        # concern -- built here, before anything else is folded into a
        # merged `tool_input`, exactly as the standalone guard used to (its
        # deny was never conditional on the other concerns' state).
        _, _, deny_message = named_dispatch_result
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_message,
            }
        }
    elif foreground_result is not None and foreground_result[0] == "deny":
        # Concern G's own fail-closed leg (a provably-foreground dispatch
        # with no safely rewritable tool_input) -- same precedence tier as
        # Concern F's deny above: built before anything else is folded into
        # `merged`, never silently absorbed into an allow.
        _, _, deny_message = foreground_result
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": deny_message,
            }
        }
    elif (
        need_mode_elevation
        or worktree_strip_result is not None
        or named_dispatch_result is not None
        or foreground_result is not None
    ):
        # --- Combined emit-gate (single-emitter fold-in, FOUR independent
        # legs): mode-elevation-needed OR worktree-isolation-stripped OR
        # named-dispatch-stripped OR foreground-dispatch-rerouted. Each leg
        # is independent -- the worktree strip must fire even when Concern A
        # doesn't apply (an ordinary dispatch that only happens to carry
        # isolation: "worktree"), the named-dispatch strip must fire even
        # when neither Concern A nor E apply (an ordinary named Explore/Plan
        # dispatch with no other trigger), and the foreground reroute must
        # fire even when none of Concerns A/E/F apply (an ordinary
        # foreground Agent dispatch with no other trigger).

        # --- Emit: permissionDecision "allow" + updatedInput (full merge,
        # whichever mutations apply). Type guard mirrors the oracle's jq path
        # ("object" type check only -- an empty {} tool_input still
        # qualifies) rather than the oracle's stricter python-fallback
        # truthy check, since jq is the oracle's PREFERRED path.
        if not isinstance(tool_input, dict):
            return 0

        merged = dict(tool_input)
        if need_mode_elevation:
            merged["mode"] = parent_mode

        # Concern E: worktree-isolation strip lands on the SAME merged dict
        # as every other concern above -- single object, single emission.
        # Surfaced via a sibling additionalContext string (the same shape
        # strip-worktree-isolation.py uses for Workflow) rather than
        # appended into tool_input.prompt, so it composes independently of
        # whether Concern A's mode overwrite also fired on this call.
        #
        # Concern F: named-dispatch strip lands on the SAME merged dict too
        # -- `name` removal, plus its own additionalContext note. Concern G:
        # foreground reroute lands on the SAME merged dict too -- sets
        # `run_in_background: true`, plus its own additionalContext note.
        # All three notes are additionalContext strings (tool_input.prompt is
        # untouched by this hook now that catering is retired -- see module
        # docstring); when several fire on the same dispatch they are
        # concatenated in a fixed order -- worktree, named-dispatch,
        # foreground-reroute -- deterministic, never a last-writer-wins
        # clobber, since this is one hook building one string, not several
        # hooks racing.
        additional_context_parts: list[str] = []
        if worktree_strip_result is not None:
            _, worktree_note = worktree_strip_result
            if "isolation" in merged:
                del merged["isolation"]
            additional_context_parts.append(worktree_note)
        if named_dispatch_result is not None:
            _, _named_merged, name_offer = named_dispatch_result
            if "name" in merged:
                del merged["name"]
            additional_context_parts.append(name_offer)
        if foreground_result is not None and foreground_result[0] == "reroute":
            # Review: code-reviewer -- consume the callee's returned value
            # rather than re-hardcoding the literal it stands for.
            merged["run_in_background"] = foreground_result[1]
            additional_context_parts.append(foreground_result[2])
        additional_context = "\n\n".join(additional_context_parts) if additional_context_parts else None

        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": merged,
            }
        }
        if additional_context:
            out["hookSpecificOutput"]["additionalContext"] = additional_context

    if out is None:
        return 0

    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
