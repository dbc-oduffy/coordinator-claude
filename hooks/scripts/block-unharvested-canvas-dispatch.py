"""PreToolUse hook (matchers: Agent, Workflow): deny a dispatch whose judged text cites a
claude.ai artifact URL without a complete harvest record and a fresh probe from this session.

Contract: coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md.
All judgement lives in `_canvas_harvest_gate.judge`; this file only extracts the text. An
other-account record admitted with drift unchecked is not a deny: the advisory goes out as
`additionalContext` and `systemMessage`.

Judged text: Agent `tool_input.prompt`; Workflow the script (inline `script`, else the file at
`scriptPath`) plus, when the sibling `<script>.emitted.json` receipt names a `plan`, that plan's
text under `docs/plans/`. The probe is bound to the payload `session_id`; a subagent's or a
Workflow stage's payload carries the lead session's id (the SubagentStart/PreToolUse payloads
in test_track_dispatched_agents_identity.py), so nested dispatches are judged too.

Exemption: an Agent whose `description` is exactly `canvas-reader <artifact_id>` is the
harvest's own reader, the dispatch that PRODUCES the record, so it can never cite one. Only
that one artifact's refusals are dropped; any other canvas the prompt cites is still judged.

Fails open on an unparseable payload, an unreadable script, a missing session id, or any
infrastructure error. Deny is JSON on stdout with exit 0 (exit 1 does not block).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


_READER_RE = re.compile(r"canvas-reader ([A-Za-z0-9_-]+)")


def _reader_artifact(tool_name: str, tool_input: dict) -> "str | None":
    """The artifact id an engine-emitted reader dispatch is for, else None."""
    if tool_name != "Agent":
        return None
    description = tool_input.get("description")
    match = _READER_RE.fullmatch(description) if isinstance(description, str) else None
    return match.group(1) if match else None


def _repo_root(payload: dict) -> "Path | None":
    start = payload.get("cwd")
    cur = Path(start if isinstance(start, str) and start else os.getcwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _plan_text(script: Path, root: Path) -> str:
    receipt = script.with_name(script.name + ".emitted.json")
    try:
        plan = json.loads(receipt.read_text(encoding="utf-8")).get("plan")
    except (OSError, ValueError, AttributeError):
        return ""
    if not isinstance(plan, str) or not plan:
        return ""
    plans_dir = (root / "docs" / "plans").resolve()
    target = (root / plan.replace("\\", "/")).resolve()
    try:
        target.relative_to(plans_dir)
    except ValueError:
        return ""
    return _read(target)


def _judged_text(tool_name: str, tool_input: dict, root: Path) -> str:
    if tool_name == "Agent":
        prompt = tool_input.get("prompt")
        return prompt if isinstance(prompt, str) else ""
    script_text = tool_input.get("script")
    if isinstance(script_text, str) and script_text:
        return script_text
    script_path = tool_input.get("scriptPath")
    if not isinstance(script_path, str) or not script_path:
        return ""
    script = Path(script_path)
    if not script.is_absolute():
        script = root / script
    body = _read(script)
    if not body:
        return ""
    return body + "\n" + _plan_text(script, root)


def _decide(payload: dict) -> "tuple[str | None, list]":
    """(deny reason, advisory messages); a deny carries no advisories."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool_name not in ("Agent", "Workflow") or not isinstance(tool_input, dict):
        return None, []
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None, []
    root = _repo_root(payload)
    if root is None:
        return None, []
    text = _judged_text(tool_name, tool_input, root)
    if not text:
        return None, []
    import _canvas_harvest_gate as gate

    refusals, advisories = gate.judge(text, root, session_id=session_id)
    reader_for = _reader_artifact(tool_name, tool_input)
    if reader_for is not None:
        refusals = [r for r in refusals if gate._URL_RE.search(r.url).group(1) != reader_for]
        advisories = [a for a in advisories if gate._URL_RE.search(a.url).group(1) != reader_for]
    if refusals:
        return refusals[0].message, []
    return None, [a.message for a in advisories]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        reason, advisories = _decide(payload)
    except Exception:
        return 0
    if reason is None:
        if advisories:
            note = "\n\n".join(advisories)
            out = {
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note},
                "systemMessage": note,
            }
            sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
            sys.stdout.write("\n")
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
