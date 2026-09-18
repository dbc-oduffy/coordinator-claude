"""PreToolUse hook (matcher: Workflow): auto-approve a fire whose script
carries a VERIFYING emission receipt, and stay silent for everything else.

The friction this removes. `/execute-plan` derives a `.mjs` from a ratified
plan spine with `emit-dispatch-workflow.py` (or the engine's `dispatch.emit`
op, which writes the same receipt), then fires it with
`Workflow({scriptPath})`. That fire raises an interactive permission prompt
every time -- on the one path the whole pipeline exists to make routine. The
prompt cannot simply be deleted at the tool level: a blanket `Workflow` allow
cannot tell an EMITTED script from a HAND-ROLLED one, and "workflows are
emitted, not hand-rolled" is precisely the rule worth keeping. Provenance is
what distinguishes them, so provenance -- not the tool name -- is what
approves.

CENTRAL INVARIANT: auto-approval has exactly ONE path, and it is the receipt
verifying. `<script>.emitted.json` must exist, parse, carry a `sha256`, and
that digest must equal the sha256 of the script's bytes on disk right now.
Every other input -- inline `script`, a saved `name`, a missing receipt, a
malformed receipt, a digest mismatch, an unreadable file, an unexpected
exception -- returns NO decision, which falls through to the human prompt
that happens today. The hook therefore cannot make any fire harder than it
already is, and cannot make an unverified one easier.

FAILS OPEN TOWARD THE PROMPT, NEVER TOWARD APPROVAL. `main()`'s whole body
is wrapped: a surprise means the operator is still asked. That direction is
the safety property -- a silent hook costs one keystroke, a wrongly-allowing
one runs bytes nobody authorized.

NEVER DENIES. This hook removes friction on the sanctioned path; it adds no
block. A hook that could deny would become a second, unreviewable gate on
firing, layered under the one that already exists for that job
(`block-workflow-foreign-emission.py`). Pinned by
`test_allow_emitted_workflow_fire.py::test_never_denies_on_any_payload`.

Per-payload-shape decision table (`tool_input` key -> decision):
  - `scriptPath`, receipt verifies      -> allow, reason names plan + emitter
  - `scriptPath`, no/bad/stale receipt  -> silent (normal prompt)
  - `script` (inline text)              -> silent. An inline script has no
    disk file and by construction can carry no receipt: this IS the
    hand-rolled case, and it must never be auto-approved.
  - `name` (a saved workflow)           -> silent. Resolved by the tool from
    its own store, not from an emitted path; nothing to verify here.
  - `resumeFromRunId`                   -> whatever `scriptPath` says. A
    resume that also names the script gets the ordinary receipt check (the
    emitted path is deterministic, so a resume re-reads the same file); a
    resume with no `scriptPath` is silent.

Coherence with the deny-side hook on this same matcher. A sha mismatch is
where the two meet: this hook stays silent and
`block-workflow-foreign-emission.py` denies with the `--restamp` remediation,
so a deliberate edit is re-stamped rather than waved through. The session
legs are kept disjoint the same way -- when the receipt names a DIFFERENT
session than this one, that hook denies, so this one withholds its allow
rather than emitting an approval its neighbour is simultaneously refusing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def _allow(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _session_id(payload: dict) -> "str | None":
    return (
        payload.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
    )


def _compose_allow_reason(plan: str, emitter: str, restamped: bool) -> str:
    """The one prose site, separated from every filesystem read above it so the
    message-budget harness can measure it by direct call. The script is not
    named here -- the tool call being approved already carries its path, and
    the two plan-shaped filenames together doubled the prose for no new fact."""
    stamp = "re-stamped" if restamped else "emitted"
    return (
        f"Receipt verifies: {stamp} from {plan} by session {emitter}. "
        "Hand-rolled or edited scripts prompt."
    )


def _decide(payload: dict) -> "str | None":
    """Return the auto-approval reason, or None to let the prompt happen."""
    if payload.get("tool_name") != "Workflow":
        return None

    tool_input = payload.get("tool_input") or {}
    script_path = tool_input.get("scriptPath")
    if not script_path:
        return None

    script = Path(script_path)
    if not script.is_absolute():
        script = Path(payload.get("cwd") or ".") / script
    if not script.is_file():
        return None

    receipt_path = script.with_name(script.name + ".emitted.json")
    if not receipt_path.is_file():
        return None

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    recorded_sha = receipt.get("sha256")
    if not recorded_sha:
        return None

    if hashlib.sha256(script.read_bytes()).hexdigest() != recorded_sha:
        return None

    recorded_session = receipt.get("session_id")
    session = _session_id(payload)
    if session and recorded_session and session != recorded_session:
        return None

    return _compose_allow_reason(
        str(receipt.get("plan") or "unrecorded"),
        str(recorded_session)[:8] if recorded_session else "unrecorded",
        bool(receipt.get("restamped_from_sha256")),
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        reason = _decide(payload)
    except Exception:
        return 0
    if reason is not None:
        _allow(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
