#!/usr/bin/env python3
"""PreToolUse(AskUserQuestion) naked-Python advisory nudge.

Port of nudge-autonomous-askuserquestion.sh -- self-contained (no engine-repo op
exists for this logic; grepped the engine repo's coordinator_core/hooks and
coordinator_core/ops, no match). Zero Git-Bash cold-start per AskUserQuestion
call on Windows (each bash.exe spawn costs 200-500ms; this is the whole
point).

Fires at engagement_posture default/substrate-free, or inside an autonomous
run -- NOT gated on a run being active. The filename retains "autonomous"
for registration stability (re-registration touches hooks.json, the
baseline roster, and the test module by name), not because a run is
required to fire.

Nudges the EM away from AskUserQuestion for break-class / engineering-approach
decisions at those firing postures. Advisory ("allow" plus context) everywhere
EXCEPT under a verified fleet posture, where it refuses.

REFUSAL UNDER A VERIFIED FLEET POSTURE: when `_fleet_posture.resolve_posture`
reports `applies` (which only happens when `_fleet_grant.verify_grant` returned
`granted` for the posture's grant), AskUserQuestion returns
`permissionDecision: deny` with the text-turn alternative in the reason. Every
session class is refused, the human-channel holder included (design doc
`docs/research/2026-09-11-fleet-control-plane-design.md`, R5 and the
channel-holder ruling). The refusal is never conditioned on the per-session
autonomous sentinel or on posture "default"/"substrate-free" alone: those
signals are agent-mintable, and widening a block to them is a product-direction
call left to the PM. Today the verifier never returns `granted`, so the deny
branch is exercised only against a stub verifier and does not fire in
production.

The old rationale for never blocking -- "a hard deny would wedge a legitimate
irreversible-external ask" -- is re-argued, not inherited. It predates a
measured four-hour block: a session that held the channel sat behind an
AskUserQuestion modal with the human away while three peers' messages went
undelivered. A modal blocks the session, and a blocked process runs no hooks
and reads no files, so no guard can rescue it. The wedge the old rationale
feared (a needed ask that cannot be made) does not occur: the
irreversible-external ask is still carried by a text-turn ask, the ask as the
end of the turn, which keeps the session reachable, hooks firing and peer
messages delivering. The deny removes the ability to block the session while
asking, not the ability to ask. What protects the irreversible-external ask now
is that text-turn route plus the COORDINATOR_AUTONOMOUS_ASK_OK pre-flight
bypass for a caller that knows in advance. Not demonstrated: a live session
under refusal making a real irreversible-external ask via text turn.

UNCONDITIONAL ADVISORY (measured retirement of the C2 content classifier):
a prior version read `tool_input.questions[].question` and classified each
question text against a stdlib high-precision/low-recall keyword whitelist
before composing the message, choosing between a "matched"
(engineering-approach) branch and an "unmatched" non-verdict branch. Run
against the archived session corpus (19,370 transcripts, 444 real
AskUserQuestion payloads), that whitelist matched 2 of 444 (0.5%), one of
those two a false positive -- a true-positive rate of roughly 1 in 444.
Because the hook ALWAYS fired at a firing posture regardless of the
classification outcome, `_classify` never decided whether to speak, only
which paragraph to print, and the matched paragraph essentially never
printed. This version deletes the classifier and its whitelist entirely
and emits ONE unconditional advisory at a firing posture -- the standing
ask bar (`global-doctrine/CLAUDE.md` § Flag Severity: break-class is the
EM's to decide and report, not to ask; direction-class is correct to ask)
plus an explicit statement that this advisory renders no verdict on the
question at hand and blocks nothing. It no longer reads
`tool_input.questions` at all.

Fires when the autonomous sentinel /tmp/autonomous-run-<SESSION_ID> is
present, OR the resolved `engagement_posture` (see `_posture.py`) is
"default" or "substrate-free" -- the ask-bar disposition this hook advises
is standing at those postures, not a manual opt-in. Inert only at posture
"precision" with no sentinel. See commands/autonomous.md § Behavior While
Active for the doctrine this hook echoes back to the EM.

Spec backlink: fix4-report.md §3-4 (ceremony-bugfix-substrate scout sketch);
docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md (chunk C2);
docs/plans/2026-08-29-first-officer-posture-without-autonomous-mode.md
(chunk C2).

Suppression conditions (preserved verbatim from the bash oracle, in order):
  1. agent_id present -- a delegated worker's AskUserQuestion is not the EM's
     own halting decision (subagent fire). Pattern copied verbatim from the
     retired bash sibling.
  2. COORDINATOR_AUTONOMOUS_ASK_OK=1 -- a PRE-FLIGHT declaration by a caller
     that knows IN ADVANCE it is about to make a legitimate irreversible
     ask (e.g. a wrapper or ceremony script setting the var before the
     process that will emit the tool call starts). It is NOT the
     disagreement channel for an EM that has just been misclassified
     mid-flow -- by the time a nudge is in context the tool call is already
     in flight, so the var cannot excuse it retroactively. The
     disagreement channel for that case is the standing advisory itself
     (see `_compose_advisory`): it renders no verdict and blocks nothing,
     so proceeding with the ask is always available. Mirrors the
     established override convention (COORDINATOR_AGENT_FOREGROUND_OK=1,
     COORDINATOR_OVERRIDE_*).
  3. session_id absent/unresolvable -- cannot resolve the sentinel path ->
     fail-open, inert.
  4. Neither the sentinel /tmp/autonomous-run-<session_id> nor a
     "default"/"substrate-free" resolved posture -> not in an active
     autonomous run and posture is "precision" -> inert.

At a firing posture (bypasses 1-4 all cleared), the hook composes and emits
the single unconditional advisory below. No further discriminator applies.

Contract (mirrors the bash hook it replaces):
  stdin   -- PreToolUse JSON (agent_id, session_id, tool_input, ...)
  stdout  -- one hookSpecificOutput JSON envelope (permissionDecision:allow +
             additionalContext, the unconditional advisory text) at a
             firing posture with no bypass applies; NOTHING otherwise
             (silent pass -- bypasses 1-4 or a non-firing posture with no
             sentinel)
  exit 0  -- always (advisory or refusal conveyed via stdout, never exit code)
  stdout under a verified fleet posture -- permissionDecision:deny plus the
             text-turn alternative as permissionDecisionReason

Graceful degradation -- any failure to parse stdin, or any unexpected
exception, falls through to fail-open (exit 0, no stdout). This hook has no
sibling engine to resolve (self-contained). Failure surfaces are stdin
parsing, filesystem stat, and posture resolution (`_posture.py`) -- all
three guarded, the last both internally (its own fail-open body) and at
this call site (defense in depth, since `_posture.py` is imported by
sibling hooks that do block).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _message_envelope import compose, render  # noqa: E402
from _posture import resolve_posture  # noqa: E402
import _fleet_posture  # noqa: E402

_NUDGE_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "an-em-asking-the-pm-a-break-class-question.md"
)


def _compose_advisory(posture: str):
    """The single unconditional advisory emitted at every firing posture.
    Renders no verdict on the question at hand -- it does not classify,
    match, or inspect `tool_input.questions` at all -- and blocks nothing."""
    prose = (
        f"[first-officer posture: {posture}]\n"
        "Structure, naming, sequencing, break-class fixes: decide, report.\n"
        "Scope, product direction, prioritization, irreversible or external\n"
        "actions: ask. No verdict here."
    )
    return compose(prose, anchor=_NUDGE_ANCHOR)


def _compose_refusal(fleet_posture: str):
    """Refusal text for a verified fleet posture: names the text-turn route."""
    prose = (
        f"[fleet posture: {fleet_posture}] AskUserQuestion is refused: a modal "
        "blocks this session while the human may be away.\n"
        "Ask as a text turn (end the turn with the question), or decide and report."
    )
    return compose(prose, anchor=_NUDGE_ANCHOR)


def _fleet_refusal(session_id: str, payload: dict):
    """Fleet posture name when a verified posture applies to this session, else None.
    Fails to None: any reader error leaves the advisory path in charge."""
    try:
        cwd = payload.get("cwd")
        res = _fleet_posture.resolve_posture(
            session_id, cwd if isinstance(cwd, str) and cwd else None
        )
        return res.posture if res.applies else None
    except Exception:
        return None


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0  # fail-open -- stdin unreadable

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        # fail-open -- malformed JSON; an empty dict is behaviorally
        # equivalent here since no agent_id means bypass 1 falls through.
        payload = {}

    # Bypass 1: subagent fire -- not the EM's own AskUserQuestion
    if payload.get("agent_id"):
        return 0

    # Bypass 2: irreversible-external override
    if os.environ.get("COORDINATOR_AUTONOMOUS_ASK_OK", "") == "1":
        return 0

    session_id = payload.get("session_id") or ""
    if not isinstance(session_id, str):
        session_id = ""

    # Bypass 3: fail-open -- no session_id extracted
    if not session_id:
        return 0

    # Refusal: only a verified fleet posture; never the sentinel or default posture.
    fleet_posture = _fleet_refusal(session_id, payload)
    if fleet_posture:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": render(
                            _compose_refusal(fleet_posture)
                        ),
                    }
                }
            )
        )
        sys.stdout.write("\n")
        return 0

    # Bypass 4: sentinel gate OR standing posture -- fire inside an active
    # autonomous run, OR when the resolved engagement_posture is
    # "default"/"substrate-free" (the ask-bar disposition is standing at
    # those postures, not gated behind a manual sentinel toggle).
    # tempfile.gettempdir() is used rather than a literal "/tmp/..." path:
    # under a Windows-native python3.exe, "/tmp" is not the MSYS mount Git
    # Bash resolves to %TEMP%, so a literal path would silently miss every
    # sentinel the bash hook can see.
    sentinel_path = os.path.join(tempfile.gettempdir(), f"autonomous-run-{session_id}")
    try:
        sentinel_present = os.path.isfile(sentinel_path)
    except Exception:
        sentinel_present = False  # fail-open -- stat failure

    try:
        posture = resolve_posture()
    except Exception:
        posture = "precision"  # fail-open -- posture resolution failure

    if not sentinel_present and posture not in ("default", "substrate-free"):
        return 0

    message = _compose_advisory(posture)

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": render(message),
        }
    }
    sys.stdout.write(json.dumps(result))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
