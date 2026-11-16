"""PostToolUse hook: name each new or changed Python function that declares no return.

After a Write/Edit/MultiEdit of a non-test `.py` file, runs `scripts/declaration_gate.py`'s
`find_undeclared` against the file's own git repo (any repo the plugin loads in) and, when `ty`
resolves on PATH, a bounded `ty check` of that file. Findings return as
`hookSpecificOutput.additionalContext` so the author sees them in the same turn.

Contract: stdin PostToolUse JSON; stdout empty or one JSON envelope; exit 0 on every path. Any
internal error is a one-line stderr note, never a failed tool call. Advisory only; never edits.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "declaration_gate.py"
MIRROR_PREFIXES = ("coordinator/bin/", "coordinator/lib/")
MIRROR_NOTE = "claude-klabauter-authored mirror: declare the return in claude-klabauter, not here"
TY_TIMEOUT_S = 5.0
TY_MAX_LINES = 5


def _load_gate() -> Optional[ModuleType]:
    if not GATE_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_declaration_gate", GATE_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves its own module through sys.modules
    spec.loader.exec_module(module)
    return module


def _anchor_dir(file_path: Path, cwd: Optional[str]) -> Path:
    """The file's own directory when it exists (the file's repo is the one that matters), else cwd."""
    if file_path.parent.is_dir():
        return file_path.parent
    return Path(cwd) if cwd else file_path.parent


def check(file_path: str, cwd: Optional[str] = None) -> Optional[str]:
    """The advisory text for `file_path`, or None when it is clean, out of scope or unreadable."""
    path = Path(file_path)
    if path.suffix != ".py":
        return None
    gate = _load_gate()
    if gate is None:
        return None
    repo_root = gate._repo_root(_anchor_dir(path, cwd))
    if repo_root is None:
        return None
    abs_path = path if path.is_absolute() else repo_root / path
    if not abs_path.is_file():
        return None
    try:
        if not gate._is_scannable(gate._relative(repo_root, abs_path)):
            return None
    except ValueError:
        return None
    findings, _errors = gate.scan(repo_root, [abs_path], "HEAD")
    lines = []
    for f in findings:
        line = gate._render(f)
        if f["path"].startswith(MIRROR_PREFIXES):
            line += f" [{MIRROR_NOTE}]"
        lines.append(line)
    ty = gate.run_ty([abs_path], TY_TIMEOUT_S)
    if ty.ran and ty.returncode not in (0, None) and ty.output:
        lines.append("ty: " + " | ".join(ty.output.splitlines()[:TY_MAX_LINES]))
    if not lines:
        return None
    return "DECLARATION-GATE (A-NEW-PYTHON-FUNCTION-DECLARES-ITS-RETURN):\n" + "\n".join(lines)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if isinstance(file_path, str) and file_path:
            text = check(file_path, cwd if isinstance(cwd, str) else None)
            if text:
                envelope = {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": text,
                    }
                }
                sys.stdout.write(json.dumps(envelope))
    except Exception as exc:  # fail open: an advisory gate must never fail a tool call
        print(f"declaration-gate: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
