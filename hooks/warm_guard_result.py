"""
coordinator.hooks.warm_guard_result -- the ONE correct reading of a warm-guard dispatch result.

Purpose: turn what `coordinator_core.warm.entry_seam.try_warm_guard_dispatch` returns into a
disposition the Bash `PreToolUse` guard can act on, without any caller having to re-derive the
rules. Pure logic: no I/O, no `coordinator_core` import, no interpreter cost worth measuring.

NEGATIVE SPEC -- why this file exists rather than three lines inlined at the call site.

`try_warm_guard_dispatch` counts ANY well-formed JSON-RPC response as `hit=True`, **error
envelopes included**; only `METHOD_NOT_FOUND` falls through to cold. The server cannot enforce
what a caller does with that. So a caller that reads `hit=True` as "a verdict arrived" turns an
engine error into a SILENT PASS -- the guard did not evaluate anything, and the command runs
anyway with nothing said. That is the C14 trap one layer out, reported by claude-klabauter-23 with
the op registration, and it is a security defect rather than a bug: the failure is invisible and
fails toward permitting.

The rule this module exists to make unmissable:

    "no verdict" is NEVER "no objection". Every non-verdict outcome routes to the COLD guard,
    which then produces a real verdict. Falling back to cold is not a degraded mode, it is the
    correct mode; the only unacceptable outcome is skipping evaluation entirely.

WHY IT IS NOT WIRED. Nothing calls this yet, deliberately. Piece (2) of C14b -- the door-side
caller -- is a hot-path edit to the live Bash guard and needs PM assent at execution dispatch
(`state/sizings/2026-08-23-warm-route-the-bash-guard-hook-doe-half.yaml`, `pm_resolution.scope`:
plan only). Two further reasons not to rush it: the http listener is currently un-startable on
this box (`docs/research/2026-08-25-http-listener-availability.md`), and AC13's <50ms saving is
NOT claimed by the op registration -- it lives in the client's reach path, which is unestablished.
Authoring the correct interpreter now is free and makes the trap un-fall-into-able the day the
caller lands.

CONTRACT (claude-klabauter-23, `warm_guard.evaluate`, live on `work/machine-a/2026-08-18to20`):
  deny          -> result {"permissionDecision": "deny", "permissionDecisionReason": "<reason>"}
  no objection  -> result {} with NO permissionDecision key -- deliberately never a literal
                   "allow", because an explicit allow overrides the operator's own permission
                   settings on some events. "I do not object" is the weaker, correct claim.
  internal fail -> a JSON-RPC error envelope, never a fabricated verdict.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

__all__ = [
    "DENY",
    "NO_OBJECTION",
    "GUARD_DID_NOT_RUN",
    "interpret",
]

#: A real verdict: the warm guard evaluated and objects.
DENY = "deny"
#: A real verdict: the warm guard evaluated and does not object.
NO_OBJECTION = "no_objection"
#: NOT a verdict. The caller MUST run the cold in-process guard. Never treat as permission.
GUARD_DID_NOT_RUN = "guard_did_not_run"


def interpret(hit: bool, response: Optional[Any]) -> "Tuple[str, Optional[str]]":
    """Reduce a `try_warm_guard_dispatch` outcome to (disposition, reason).

    `reason` is populated only for DENY. Every disposition other than DENY/NO_OBJECTION is
    GUARD_DID_NOT_RUN, which obliges the caller to fall back to the cold guard.

    Deliberately total: any shape not explicitly recognised as a verdict is GUARD_DID_NOT_RUN.
    A parser that raises on an unexpected payload would fail the hook open just as surely as
    one that treats an error as a pass, so this function never raises.
    """
    if not hit:
        # METHOD_NOT_FOUND or no reachable server -- the ordinary cold path.
        return GUARD_DID_NOT_RUN, None

    if not isinstance(response, dict):
        return GUARD_DID_NOT_RUN, None

    # THE TRAP. hit=True with an error envelope means the engine failed, not that it permitted.
    if response.get("error") is not None:
        return GUARD_DID_NOT_RUN, None

    if "result" not in response:
        return GUARD_DID_NOT_RUN, None

    result = response.get("result")
    if not isinstance(result, dict):
        return GUARD_DID_NOT_RUN, None

    decision = result.get("permissionDecision")

    if decision is None:
        # {} with no permissionDecision -- the contract's no-objection shape.
        return NO_OBJECTION, None

    if decision == "deny":
        reason = result.get("permissionDecisionReason")
        if not isinstance(reason, str) or not reason.strip():
            # A deny we cannot explain is still a deny -- never downgrade it to a pass.
            reason = "warm guard denied this command but supplied no reason"
        return DENY, reason

    # Anything else -- including a literal "allow", which this contract never sends. Receiving
    # one means the peer is not the op we think it is, so decline to propagate a permission we
    # cannot account for and let the cold guard decide.
    return GUARD_DID_NOT_RUN, None
