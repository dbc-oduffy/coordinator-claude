"""PreToolUse hook (matcher: Workflow): refuse to fire a script this session
did not emit.

The window this closes. `emit-dispatch-workflow.py` writes its `.mjs` to a
path that is a deterministic function of the plan alone, so every session
emitting that plan targets the same file. `/execute-plan` then fires it with
`Workflow({scriptPath})` from the EM's own loop -- a SEPARATE read of the
file, minutes after the emit in a busy session. A peer writing that path in
between is invisible: the run executes their wave map under this session's
handle, and neither the tool result nor the run handle says so.

Measured 2026-08-30: a fired script had grown a `Wave 1: C10, C11` phase ahead
of the intended C12 wave; a scratch re-emit produced `Wave 1: C12` only,
proving the overwrite. C10's disposition was explicitly NO MEMO OWED, so the
silent re-dispatch put an external-facing send to a sibling repo back in play.
That is the cost that makes this a gate rather than a warning.

Why the emitter's own guards do not cover it. `_guard_against_foreign_
overwrite` binds the EMIT leg (do not clobber a peer) and
`_guard_against_fired_drift` binds the in-process `--fire` leg. Both live in a
process that holds the emitted bytes. The interactive fire is a different
process that never sees them, so the provenance has to travel on disk -- the
`<script>.emitted.json` receipt this hook reads.

Negative spec: does NOT make the script path unique. `Workflow({resumeFrom
RunId})` re-reads the script by its deterministic name, so a session-scoped
path breaks resume; the check is on provenance, never on the filename. Does
NOT re-emit to compare -- an emit materializes briefs and is far too heavy for
a tool-boundary hook.

Fail-open guards (all exit 0 silent):
  - tool_name != "Workflow".
  - No `scriptPath` (an inline `script:` carries its own bytes in the call --
    there is no disk read for a peer to race).
  - No receipt beside the script. A hand-authored or checked-in workflow
    (`coordinator/workflows/*.mjs`) was never emitted and has no provenance to
    check; absence is not evidence of tampering.
  - Receipt unreadable or malformed. A guard that cannot read its own input
    denies nothing -- it is not the integrity oracle for its own sidecar.
  - This session's id is undetectable, or the receipt recorded none. Denying
    every launch in a session whose id the platform did not inject would wedge
    legitimate work over a condition the operator cannot fix.

DENIES (Form A permissionDecision:"deny") on exactly two conditions, both of
which mean the bytes about to run are not the bytes this session emitted:
  1. sha mismatch -- the file changed after it was emitted, by any route.
  2. session mismatch -- the receipt names a DIFFERENT session as emitter.

The sha leg has one sanctioned exit, and it must stay named in the deny text.
`/execute-plan`'s documented recovery from a halted run is to EDIT the halting
phase's agent step and resume -- resume serves the longest unchanged prefix of
`agent()` calls from cache, so an unedited relaunch replays the cached
refusal. That edit changes the sha this hook checks, and the re-emit this hook
would otherwise be recommending is the move that skill explicitly forbids
(`read_spine` excludes landed chunks, so the re-emitted script is silently
narrower). Without an exit, the two documented recoveries contradict and a
halted run is unrecoverable. The exit is
`emit-dispatch-workflow --restamp <script>`, which re-stamps the receipt
only when it already names the CURRENT session as emitter -- so the peer-
overwrite case this hook exists for still cannot be laundered through it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from pathlib import Path


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _session_id(payload: dict) -> "str | None":
    return (
        payload.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
    )


def _emitter_invocation() -> tuple[str, str]:
    """A COPY-PASTEABLE emitter invocation, absolute wherever possible, plus the
    shell family it will be pasted into (`"posix"`, `"cmd"`, or `"ps1"`) --
    `_reemit_command` needs that to quote its trailing argv in a syntax the
    target shell actually parses (Review: coordinator-code-reviewer 2026-09-22
    -- `shlex.quote`'s POSIX single-quotes are not quoting syntax to cmd.exe at
    all).

    `emit-dispatch-workflow` is served from the settings-home launcher (no DoE-local
    copy as of the slice-1 fence-switch, coordinator-claude#47) -- resolved the same
    way every coordinator CLI is, per `snippets/resolve-coordinator-bin.md`, never
    against `CLAUDE_PLUGIN_ROOT` or a `.content-root` pointer.
    """
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    base = Path(settings_home) / "bin" / "emit-dispatch-workflow"
    exe_candidate = base.with_suffix(".exe")
    if exe_candidate.is_file():
        return '"' + str(exe_candidate) + '"', "cmd"
    if base.is_file():
        return '"' + str(base) + '"', "posix"
    return (
        '"' + str(base) + '"  # launcher not found -- reinstall coordinator-claude, then rerun'
    ), "posix"


def _quote_arg_for_shell(arg: str, shell: str) -> str:
    """`shlex.quote` (POSIX single-quoting) is correct for `posix` and `ps1`
    but is not quoting syntax to cmd.exe at all. cmd.exe quotes with a
    doubled double-quote; there is no escape for a literal trailing
    backslash immediately before the closing quote, so that case is named
    rather than fabricated."""
    if shell != "cmd":
        return shlex.quote(arg)
    if not arg or any(ch.isspace() for ch in arg) or '"' in arg:
        if arg.endswith("\\"):
            return f'"{arg}"  # unquotable for cmd.exe: trailing backslash'
        return '"' + arg.replace('"', '""') + '"'
    return arg


def _reemit_command(receipt: dict) -> str:
    """A queue-emitted receipt carries its own `reemit` argv; `--plan
    <plan-path>` is wrong advice there since it has no plan to name. A
    receipt predating the `reemit` key still gets the `--plan` line."""
    invocation, shell = _emitter_invocation()
    reemit = receipt.get("reemit")
    if isinstance(reemit, list) and reemit:
        args = " ".join(_quote_arg_for_shell(str(arg), shell) for arg in reemit)
        return f"{invocation} {args}"
    return f"{invocation} --plan <plan-path>"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Workflow":
        return 0

    tool_input = payload.get("tool_input") or {}
    script_path = tool_input.get("scriptPath")
    if not script_path:
        return 0

    script = Path(script_path)
    if not script.is_absolute():
        script = Path(payload.get("cwd") or ".") / script
    if not script.is_file():
        return 0

    receipt_path = script.with_name(script.name + ".emitted.json")
    if not receipt_path.is_file():
        return 0

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        recorded_sha = receipt["sha256"]
        recorded_session = receipt.get("session_id")
    except Exception:
        return 0

    actual_sha = hashlib.sha256(script.read_bytes()).hexdigest()
    if actual_sha != recorded_sha:
        _deny(
            f"{script.name} changed after it was emitted -- refusing to fire.\n\n"
            f"Its receipt ({receipt_path.name}) records sha256 {recorded_sha[:12]}; "
            f"the file on disk is {actual_sha[:12]}. Something wrote this script "
            "outside the emitter, so the wave map about to run is not the one that "
            "was derived from the plan.\n\n"
            "If YOU edited it -- the documented recovery from a halted run is to "
            "edit the halting phase's agent step, and no earlier one -- an edited "
            "completed step loses its cache and re-runs -- and an unedited resume "
            "replays the cached refusal -- re-stamp the receipt over your own edit:\n"
            f"  {_emitter_invocation()[0]} --restamp "
            f'"{script}"\n'
            "It prints the phase spine it is authorizing, and refuses unless the "
            "receipt names this session, so a peer's emission cannot be laundered "
            "through it.\n\n"
            "If you did NOT edit it, re-emit before firing --\n"
            f"  {_reemit_command(receipt)}\n"
            "then read the wave map it produces. Rows that changed may carry "
            "dispositions this run was never authorized for. A re-emit against a "
            "plan whose early chunks have landed narrows the script silently "
            "(A-SECOND-EMIT-AFTER-A-PARTIAL-RUN-NARROWS-SILENTLY), so it is the "
            "wrong move for a deliberate edit."
        )

    session = _session_id(payload)
    if session is None or recorded_session is None:
        return 0
    if session != recorded_session:
        _deny(
            f"{script.name} was emitted by a DIFFERENT session -- refusing to fire.\n\n"
            f"Its receipt names session {recorded_session[:8]}; this session is "
            f"{session[:8]}. The emitted path is a deterministic function of the plan, "
            "so a peer working the same plan targets the same file. Firing it would "
            "run THEIR wave map under your handle, and nothing in the handle would "
            "say so.\n\n"
            "Fix: re-emit before firing --\n"
            f"  {_reemit_command(receipt)}\n"
            "The emitter refuses to overwrite a differing emission, so a refusal "
            "there means coordinate with that session rather than --force past it."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
