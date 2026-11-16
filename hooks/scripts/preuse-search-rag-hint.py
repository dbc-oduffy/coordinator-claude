#!/usr/bin/env python3
"""PreToolUse(Grep|Glob) non-blocking hint: a symbol-style search in a project-rag-indexed repo draws one
`additionalContext` line naming the tier-1 project-rag tools.

Contract:
  stdin   -- PreToolUse JSON (tool_name, tool_input, cwd, ...)
  stdout  -- one hookSpecificOutput envelope (additionalContext only, never a permissionDecision) when
             tool_name is Grep|Glob, a `.project-rag` dir sits at or above cwd, and the Grep pattern looks
             like a code symbol; NOTHING otherwise
  exit 0  -- always; every failure degrades to silence

A glob (`*.py`) and a literal-text pattern are never symbols. Presence gate and hint text live in
`_project_rag_nudge`.
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
        from _project_rag_nudge import hint_text, rag_present

        if not rag_present(payload.get("cwd")):
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": hint_text(sym),
        }}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
