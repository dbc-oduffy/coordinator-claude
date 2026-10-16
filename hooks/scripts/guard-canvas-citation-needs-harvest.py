# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py); this basename is
# deliberately never referenced literally in hooks.json text.
"""PreToolUse guard (Write|Edit|MultiEdit): denies a write to a `docs/plans/**/*.md` file
that fails either of two judgments.

1. Intersect check (`_design_registry_gate.check`): the plan's touched files fall under a
   registered design entry without citing its harvest record or a ratified design-deviation.
   It judges the whole plan text on every write, not only what the write introduced.
2. Canvas citation: the write introduces a claude.ai artifact URL without a passing harvest
   record cited in the text. Judges only `new_citations(before, after)`; the verdict is
   `_canvas_harvest_gate.check`.

Fails open on an unparseable payload, an out-of-scope path, an unreconstructable edit, or an
unimportable or raising registry module (the canvas judgment still runs).
Contracts: coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md and
design-registry.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _canvas_harvest_gate as gate  # noqa: E402
from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")


def _repo_root_of(target: Path):
    """Parent of the `docs/plans` directory holding `target`, or None when out of scope."""
    if target.suffix != ".md":
        return None
    parts = target.parts
    for i in range(len(parts) - 2, 0, -1):
        if parts[i] == "plans" and parts[i - 1] == "docs":
            return Path(*parts[: i - 1]) if i - 1 > 0 else None
    return None


def _deny(text: str) -> None:
    """PreToolUse deny envelope around the already-rendered refusal text."""
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": text,
        }
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")))


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else None
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_name = payload.get("tool_name", "")
    if tool_name not in _GUARDED_TOOLS:
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    target_raw = extract_target_path(tool_input)
    if not target_raw:
        return 0
    try:
        target = Path(target_raw).resolve()
        repo_root = _repo_root_of(target)
        if repo_root is None:
            return 0
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return 0

    after = reconstruct_after(tool_name, tool_input, before)
    if after is None:
        return 0
    try:
        import _design_registry_gate as registry  # noqa: E402

        refusals = registry.check(after, repo_root)
    except Exception as exc:
        sys.stderr.write(f"design-registry leg skipped: {type(exc).__name__}: {exc}\n")
        refusals = []
    if refusals:
        _deny("\n\n".join(r.message for r in refusals))
        return 0
    introduced = gate.new_citations(before, after)
    if not introduced:
        return 0
    for refusal in gate.check(after, repo_root):
        if refusal.url in introduced:
            _deny(refusal.message)
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
