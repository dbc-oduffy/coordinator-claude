"""PreToolUse(Grep|Glob) rag-first guard: a symbol-style search in a project-rag-indexed repo.

Contract:
  stdin   -- PreToolUse JSON (tool_name, tool_input, cwd, session_id, agent_id, agent_type, ...)
  stdout  -- one hookSpecificOutput envelope when tool_name is Grep|Glob, a `.project-rag` dir sits at or
             above cwd, and the pattern looks like a code symbol; NOTHING otherwise. The envelope is:
             a `permissionDecision: deny` for a Grep from a CODE_QUESTION_AGENTS agent whose
             (session_id, agent_id) ledger state is none; an allow carrying `DEGRADED: project-rag is
             down` (also on stderr) when the state is down; nothing when it is ok; a non-blocking hint
             for every other caller and for Glob
  exit 0  -- always; any exception allows, with one stderr line

A glob (`*.py`) and a literal-text pattern are never symbols. Presence gate, texts and the agent set live
in `_project_rag_nudge`; the call ledger in `_rag_call_ledger`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

_DEF_KEYWORDS = r"(?:def|class|fn|func|function|struct|interface|enum|trait|impl|type)"
_DEF_FORM = re.compile(rf"^{_DEF_KEYWORDS}\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_BARE_IDENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\\?\(\)?)?$")


def symbol_in(pattern: object) -> str:
    """The code symbol a Grep pattern names, or "" when it reads as literal text or a glob."""
    if not isinstance(pattern, str):
        return ""
    pat = pattern.strip()
    if not pat:
        return ""
    m = _DEF_FORM.match(pat)
    if m:
        return m.group(1)
    m = _BARE_IDENT.match(pat)
    if not m:
        return ""
    ident = m.group(1)
    snake = "_" in ident.strip("_") and ident.lower() == ident
    camel = ident[0].isupper() and any(c.islower() for c in ident) and any(c.isupper() for c in ident[1:])
    return ident if snake or camel else ""


def main(stdin_text: str | None = None) -> int:
    try:
        payload = json.loads(stdin_text if stdin_text is not None else sys.stdin.read())
        if not isinstance(payload, dict) or payload.get("tool_name") not in ("Grep", "Glob"):
            return 0
        tool_input = payload.get("tool_input")
        sym = symbol_in(tool_input.get("pattern") if isinstance(tool_input, dict) else None)
        if not sym:
            return 0
        from _project_rag_nudge import (
            degraded_text, deny_text, hint_text, is_code_question_agent, rag_present,
        )

        if not rag_present(payload.get("cwd")):
            return 0
        out: dict = {"hookEventName": "PreToolUse", "additionalContext": hint_text(sym)}
        session_id = payload.get("session_id")
        if (
            payload.get("tool_name") == "Grep"
            and is_code_question_agent(payload.get("agent_type"))
            and isinstance(session_id, str)
            and session_id
        ):
            import _rag_call_ledger

            state = _rag_call_ledger.state_for(session_id, payload.get("agent_id"))
            if state == _rag_call_ledger.STATE_OK:
                from _project_rag_nudge import bump_search_count, nag_every, nag_text

                if bump_search_count(session_id, payload.get("agent_id")) % nag_every(payload.get("cwd")):
                    return 0
                out["additionalContext"] = nag_text(sym)
            elif state == _rag_call_ledger.STATE_DOWN:
                warn = degraded_text()
                sys.stderr.write(warn + "\n")
                out["additionalContext"] = warn
            else:
                out = {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": deny_text(sym, payload.get("cwd")),
                }
        sys.stdout.write(json.dumps({"hookSpecificOutput": out}))
    except Exception as exc:
        sys.stderr.write(f"rag-first-guard fail-open: {type(exc).__name__}: {exc}\n")
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
