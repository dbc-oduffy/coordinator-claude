#!/usr/bin/env python3
"""PreToolUse(AskUserQuestion) naked-Python advisory nudge.

Port of nudge-autonomous-askuserquestion.sh -- self-contained (no claude-klabauter op
exists for this logic; grepped /x/claude-klabauter/coordinator_core/hooks and
coordinator_core/ops, no match). Zero Git-Bash cold-start per AskUserQuestion
call on Windows (each bash.exe spawn costs 200-500ms; this is the whole
point).

Nudges the EM away from AskUserQuestion for break-class / engineering-approach
decisions while an autonomous run is active. Advisory only -- "allow" always;
never blocks. The nudge redirects, it does not gate, matching the
design-as-offers doctrine (a hard deny would wedge a legitimate
irreversible-external ask).

Fires when the autonomous sentinel /tmp/autonomous-run-<SESSION_ID> is
present, OR the resolved `engagement_posture` (see `_posture.py`) is
"default" or "substrate-free" -- the ask-bar disposition this hook advises
is standing at those postures, not a manual opt-in. Inert only at posture
"precision" with no sentinel. See commands/autonomous.md § Behavior While
Active for the doctrine this hook echoes back to the EM.

Spec backlink: fix4-report.md §3-4 (ceremony-bugfix-substrate scout sketch);
docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md (chunk C2).

Suppression conditions (preserved verbatim from the bash oracle, in order):
  1. agent_id present -- a delegated worker's AskUserQuestion is not the EM's
     own halting decision (subagent fire). Pattern copied verbatim from the
     retired bash sibling.
  2. COORDINATOR_AUTONOMOUS_ASK_OK=1 -- the EM has deliberately authorized
     this ask (the one legitimate autonomous-mode ask: a genuinely
     irreversible external action with no pre-authorization, or a true
     no-correct-answer product fork). Mirrors the established override
     convention (COORDINATOR_AGENT_FOREGROUND_OK=1, COORDINATOR_OVERRIDE_*).
  3. session_id absent/unresolvable -- cannot resolve the sentinel path ->
     fail-open, inert.
  4. Neither the sentinel /tmp/autonomous-run-<session_id> nor a
     "default"/"substrate-free" resolved posture -> not in an active
     autonomous run and posture is "precision" -> inert.

Contract (mirrors the bash hook it replaces):
  stdin   -- PreToolUse JSON (agent_id, session_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope (permissionDecision:allow +
             additionalContext) when the sentinel is present and no bypass
             applies; NOTHING otherwise (silent pass)
  exit 0  -- always (advisory conveyed via stdout, never exit code; this hook
             is advisory-only and never blocks)

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

_NUDGE_PROSE = (
    "AskUserQuestion halts autonomous mode for PM return -- the "
    "costliest action. Fix-class findings are yours to decide, not ask. "
    "Advisory only -- this call is always allowed to proceed."
)
_NUDGE_ANCHOR = "coordinator/docs/wiki/guard-unlock-channel.md"


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
        payload = {}  # fail-open -- malformed JSON; bash oracle's substring
        # check would also miss a non-JSON blob, so an empty dict here is
        # behaviorally equivalent (no agent_id -> bypass 1 falls through).

    # --- Bypass 1: subagent fire -- not the EM's own AskUserQuestion ---
    if payload.get("agent_id"):
        return 0

    # --- Bypass 2: irreversible-external override ---
    if os.environ.get("COORDINATOR_AUTONOMOUS_ASK_OK", "") == "1":
        return 0

    # --- Extract session_id ---
    session_id = payload.get("session_id") or ""
    if not isinstance(session_id, str):
        session_id = ""

    # --- Bypass 3: fail-open -- no session_id extracted ---
    if not session_id:
        return 0

    # --- Bypass 4: sentinel gate OR standing posture -- fire inside an
    # active autonomous run, OR when the resolved engagement_posture is
    # "default"/"substrate-free" (the ask-bar disposition is standing at
    # those postures, not gated behind a manual sentinel toggle).
    # The bash oracle hardcodes "/tmp/autonomous-run-<sid>". A naive literal
    # port ("/tmp/...") is WRONG under a Windows-native python3.exe: Git
    # Bash's /tmp is an MSYS mount, not a real filesystem root -- MSYS bash
    # resolves it to %TEMP% (confirmed via `cygpath -w /tmp`), but a
    # Windows-native Python process has no MSYS path-translation layer and
    # would instead treat "/tmp/..." as drive-relative (e.g. tmp/...),
    # silently missing every sentinel the bash hook can see. tempfile.gettempdir()
    # resolves to the same %TEMP% directory Git Bash's /tmp is mounted to,
    # so this is the portable equivalent, not a behavior change.
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

    message = compose(_NUDGE_PROSE, anchor=_NUDGE_ANCHOR)
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
