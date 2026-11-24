# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py calls in-process. Never referenced literally in hooks.json.
"""PreToolUse guard: deny a Write/Edit/MultiEdit/NotebookEdit that introduces a NEW literal
absolute path or drive root into any text target, in-repo or out (briefs, scripts, configs,
docs, `.mcp.json`, settings and registry files).

Contract:
  - Detection, the marker rule and the replacement text are `_abs_path_literal`'s; this
    module reconstructs before/after and denies on `new_literals(before, after)` findings
    that are not `is_marked(line, finding)`. A reasoned `abs-path-ok:` line stays allowed; a
    data-root finding is refused even when marked.
  - A JSON registry target (`machine-local` directory or `registry*.json`) cannot carry a
    marker comment, so every finding there is refused and the deny names `machine-local set`.
  - Scope is every text suffix in `ABS_PATH_LITERAL_SCOPE_DESCRIPTOR`, any directory, minus
    `archive/`.
  - Fails open (exit 0, no stdout) only on an unreconstructable payload: bad stdin, a tool
    outside the guarded set, no target, an unreadable existing target, or an Edit whose
    `old_string` is absent from the file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PureWindowsPath

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _abs_path_literal import _RESOLVE_HINT, is_marked, new_literals, replacement_hint  # noqa: E402
from _guard_runner_contract import ABS_PATH_LITERAL_SCOPE_DESCRIPTOR  # noqa: E402
from _sentinel_write_guard import extract_target_path  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_SHOWN = 3


def _parts(target: str) -> tuple:
    return tuple(p.casefold() for p in PureWindowsPath(target).parts)


def is_in_scope(target: str) -> bool:
    """Text target outside `archive/`."""
    return ABS_PATH_LITERAL_SCOPE_DESCRIPTOR.matches(target) and "archive" not in _parts(target)


def is_json_registry(target: str) -> bool:
    """A JSON registry file: no comment syntax, so no marker can sit on its line."""
    path = PureWindowsPath(target)
    if path.suffix.casefold() != ".json":
        return False
    return "machine-local" in _parts(target) or path.stem.casefold().startswith("registry")


def reconstruct_after(tool_name: str, tool_input: dict, before: str) -> "str | None":
    """The written content, or None when the payload cannot be rebuilt."""
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    if tool_name == "NotebookEdit":
        if tool_input.get("edit_mode") == "delete":
            return ""
        source = tool_input.get("new_source")
        return source if isinstance(source, str) else None
    if tool_name == "Edit":
        edits = [tool_input]
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list) or not edits:
            return None
    else:
        return None
    text = before
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        if old == "":
            if text:
                return None
            text = new
            continue
        if old not in text:
            return None
        text = text.replace(old, new) if edit.get("replace_all") is True else text.replace(old, new, 1)
    return text


def _refused(findings: list, registry_json: bool) -> list:
    if registry_json:
        return list(findings)
    return [f for f in findings if not is_marked(f.line_text, f)]


def _reason(target: str, findings: list, registry_json: bool) -> str:
    shown = ", ".join(f"`{f.literal}`" for f in findings[:_SHOWN])
    if len(findings) > _SHOWN:
        shown += f", +{len(findings) - _SHOWN} more"
    head = f"{target}: write introduces {len(findings)} literal absolute path(s): {shown}."
    if registry_json:
        return (
            f"{head} {_RESOLVE_HINT} A JSON registry cannot carry an `abs-path-ok:` "
            "marker: set the row with `machine-local set <key> <value>` and a reasoned "
            "`abs-path-ok: <reason>` marker in that command."
        )
    parts = [head]
    seen = set()
    for f in findings:
        if f.root_class not in seen:
            seen.add(f.root_class)
            parts.append(replacement_hint(f))
    return " ".join(parts)


def denial_for(tool_name: str, tool_input: dict) -> "dict | None":
    if tool_name not in _GUARDED_TOOLS or not isinstance(tool_input, dict):
        return None
    target = extract_target_path(tool_input)
    if not target or not is_in_scope(target):
        return None
    path = Path(target)
    try:
        before = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except Exception:
        return None
    after = reconstruct_after(tool_name, tool_input, before)
    if after is None:
        return None
    registry_json = is_json_registry(target)
    findings = _refused(new_literals(before, after), registry_json)
    if not findings:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _reason(target, findings, registry_json),
        }
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        result = denial_for(payload.get("tool_name", ""), payload.get("tool_input") or {})
    except Exception:
        return 0
    if result:
        sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
