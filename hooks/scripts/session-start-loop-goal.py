"""session-start-loop-goal.py -- re-surface the session's `/loop` goal after a compaction (SessionStart leg).

A StartGuard in `sessionstart-dispatch.py`, `compact` only. Reads the payload's `transcript_path`,
finds the session's last `/loop` invocation (a user turn carrying `<command-name>/loop</command-name>`),
and emits its goal plus one line keeping the loop goal-style: it persists, re-surfaces after a
compaction, and re-wakes at the `LOOP_DEFAULT_CADENCE_HOURS` default, never a sub-hour wakeup.
Silent when the session set no goal. Fail-open; exit 0.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Optional

#: The n-hour default `/loop` cadence; `coordinator/snippets/em-operating-doctrine.md` states the same value.
LOOP_DEFAULT_CADENCE_HOURS = 4
#: Goal text bytes; the leg output stays under the per-leg ceiling in
#: tests/baselines/sessionstart-injection-budget.json (default 1300).
GOAL_MAX_BYTES = 500

_MARKER = "<command-name>/loop</command-name>"
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_INTERVAL = re.compile(r"^(?:every\s+)?\d+\s*(?:s|sec|m|min|h|hr|hrs|hour|hours|d|day|days)\b\s*", re.I)


def _goal_from_content(content) -> Optional[str]:
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    if not isinstance(content, str) or _MARKER not in content:
        return None
    m = _ARGS.search(content)
    args = (m.group(1) if m else "").strip()
    return _INTERVAL.sub("", args, count=1).strip() or None


def last_loop_goal(transcript_path: str) -> Optional[str]:
    """The goal of the transcript's last user `/loop` invocation; None when there is none."""
    goal = None
    with open(transcript_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if _MARKER not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "user":
                continue
            msg = obj.get("message")
            found = _goal_from_content(msg.get("content") if isinstance(msg, dict) else None)
            if found:
                goal = found
    return goal


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore").rstrip() + "..."


def build(raw_stdin: str) -> str:
    """The context text for a compact payload whose session set a `/loop` goal; "" otherwise."""
    try:
        payload = json.loads(raw_stdin) if raw_stdin else {}
    except ValueError:
        return ""
    path = payload.get("transcript_path") if isinstance(payload, dict) else None
    if not path:
        return ""
    goal = last_loop_goal(path)
    if not goal:
        return ""
    n = LOOP_DEFAULT_CADENCE_HOURS
    return (f"Session loop goal (set by this session's /loop): {_clip(goal, GOAL_MAX_BYTES)}\n"
            f"Keep the /loop goal-style: the goal persists and re-surfaces after a compaction; "
            f"re-wake at the {n}h default cadence (`/loop {n}h <goal>`), never a sub-hour "
            f"self-paced wakeup.")


def main(argv=None) -> int:
    try:
        text = build(sys.stdin.read())
        if text:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
            sys.stdout.write("\n")
    except Exception:  # noqa: BLE001 -- fail open: a session start is never blocked by this leg
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
