#!/usr/bin/env python3
"""strip-worktree-isolation.py -- PreToolUse hook, matcher: Workflow.

Makes `isolation: "worktree"` unreachable on a `Workflow` dispatch by
STRIPPING the key out of `tool_input` before the call proceeds, rather than
denying the whole dispatch. Global doctrine (design-as-offers,
`~/.claude/CLAUDE.md § Implementation Standards -- Extensions`): "Design
agent-facing tooling as offers, not nags -- lead with the better alternative,
not the violation." A deny here would punish the dispatching agent for one
bad field and force a full retry of an otherwise-correct dispatch; stripping
the field lets the dispatch SUCCEED without the worktree, which is exactly
the intended behaviour -- git-worktree-per-dispatch is banned outright (see
`docs/wiki/... shared-tree stash/worktree discipline`), not merely
discouraged, so there is no legitimate value the strip destroys.

Single-emitter fix (2026-07-31): this hook used to ALSO cover `Agent`
(matcher `Agent|Workflow`), racing in parallel against
`enforce-agent-dispatch-mode.py`'s own `updatedInput` emission on the same
`Agent` tool call -- Claude Code runs same-event hooks concurrently with
undefined completion order, and `updatedInput` is last-writer-wins, so
exactly one of the two rewrites was silently clobbered on any Agent dispatch
carrying both `isolation: "worktree"` and a mode-elevation/sidecar/
role-framing trigger (confirmed live on harness 2.1.220). Fix: `Agent`'s
worktree-isolation strip now lives INSIDE `enforce-agent-dispatch-mode.py`
(the sole `updatedInput` emitter for `Agent`), sharing this hook's strip
computation via `_worktree_isolation_strip.compute_strip` rather than
re-implementing it. This hook is narrowed to `Workflow` only -- `Workflow`'s
`tool_input` has no `prompt` key (it carries `script`/`scriptPath`), so it
cannot fold into `enforce-agent-dispatch-mode.py`'s Agent-only merge path
and must stay a standalone hook for that tool. The strip and override logic
itself is NOT duplicated between the two call sites -- both import
`compute_strip` / `sentinel_override_active` from
`_worktree_isolation_strip.py`, so the merge-and-emit path exists exactly
once per matcher, not copy-pasted to "agree".

The strip is surfaced visibly via a sibling
`hookSpecificOutput.additionalContext` string (the same advisory-message key
`block-workflow-unmodeled-agent.py` uses for its WARN case, ~line 644)
rather than appending to `tool_input.prompt` -- `Workflow`'s `tool_input` has
no `prompt` key at all, so an `additionalContext` note is the one surfacing
mechanism available for this tool.

Only the literal value "worktree" is banned. `isolation: "remote"` (and any
other value) is a legitimate, unrelated isolation mode and passes through
byte-identical -- this hook must never touch it.

Override: a repo-root sentinel file only, `.coordinator-override-worktree-
guard` -- deliberately NOT an env-var leg (see `_worktree_isolation_strip.py`
for the full rationale, shared with `enforce-agent-dispatch-mode.py`'s
Agent-side strip).

Fail-open on every detection-failure leg: unreadable stdin, unparsable JSON,
non-dict tool_input, unresolvable/non-"Workflow" tool_name. This hook exits 0
unconditionally; allow/mutation is conveyed via stdout only, never via exit
code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _worktree_isolation_strip import compute_strip  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0

    try:
        data: Any = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0

    tool_name = data.get("tool_name")
    if tool_name != "Workflow":
        return 0

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    result = compute_strip(tool_input)
    if result is None:
        return 0
    merged, note = result

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": merged,
            "additionalContext": note,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
