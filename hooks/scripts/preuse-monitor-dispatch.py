"""PreToolUse(Monitor) shim -- threshold-watch advisory.

Classifies one Monitor `tool_input.command` string: an unbounded source (`tail -f`,
`while true`/`until false`/`for ((;;))`) piped to a filter that emits only on a threshold
(`grep -m1`, `grep -q`, `head -1`, a numeric compare, an awk compare/exit). That shape wakes the
session at Monitor's 30-minute cap even when nothing tripped; the advisory hands back the
`run_in_background` exit-on-condition Bash loop. Per-occurrence streams (`gh run watch`,
`tail -f app.log | grep ERROR`) pass silently.

Advisory-only: never denies. Pure stdlib; no engine call.

Deliberately NO shebang: hooks.json invokes this file through the `_hook_boot.py` bootstrap.

Contract:
  stdin  -- PreToolUse JSON (tool_name, tool_input.command ...)
  stdout -- hookSpecificOutput.additionalContext, only when the command is a threshold watch
  exit 0 -- every path, including every failure path (fail-open silent pass)

Wiki: docs/wiki/coordinator-tripwires/a-threshold-watch-in-monitor-wakes-every-thirty-minutes.md
"""

from __future__ import annotations

import json
import re
import sys

_UNBOUNDED_SOURCE = re.compile(
    r"""(?x)
    (?<![\w-]) tail \s+ (?:-\w*[fF]\w* | --follow\b | -[-\w=\s]*?\s-\w*[fF]\w*)
    | (?<![\w-]) while \s+ (?: true | : | \[\s*1\s*\] ) \s* [;\n]
    | (?<![\w-]) until \s+ false \s* [;\n]
    | (?<![\w-]) for \s* \(\( \s* ; \s* ; \s* \)\)
    """
)

_THRESHOLD_FILTER = re.compile(
    r"""(?x)
    (?<![\w-]) e?grep \b [^|;\n]*? (?: \s-\w*m\s*\d+ | \s--max-count | \s-\w*q\b | \s--quiet )
    | (?<![\w-]) head \s+ -(?:n\s*)?1\b
    | (?<![\w-]) sed \s [^|;\n]*? \bq\b
    | (?<![\w-]) awk \s [^|;\n]* (?: [<>]=?\s*\d | NR\s*==\s*\d | \bexit\b )
    | \s-(?:gt|ge|lt|le)\s
    | \(\( [^)]*? [<>]=? [^)]* \)\)
    """
)

ADVISORY = (
    "Monitor tripwire shape detected: an unbounded source (tail -f / while true) feeding a filter "
    "that emits only when a threshold trips. Monitor wakes the session at its 30-minute cap even "
    "when nothing tripped. Use a Bash call with run_in_background: true running a loop that (1) "
    "exits on the trip, (2) exits when the watched job ends, and (3) prints its reason as its "
    "last line, so the one completion notification is the whole wake. Example: "
    "`while kill -0 \"$WATCHED_PID\" 2>/dev/null; do "
    "if grep -q 'FAILED' build.log; then echo 'tripped: FAILED in build.log'; exit 0; fi; "
    "sleep 30; done; echo 'watched job ended without a trip'`. "
    "Keep Monitor for per-occurrence streams (CI step results, each log error)."
)


def classify(command: str) -> bool:
    """True when `command` is an unbounded source piped to a threshold-only filter."""
    if not isinstance(command, str) or not command.strip():
        return False
    return bool(_UNBOUNDED_SOURCE.search(command) and _THRESHOLD_FILTER.search(command))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        tool_name = payload.get("tool_name")
        if tool_name is not None and tool_name != "Monitor":
            return 0
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not classify(command):
            return 0
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": ADVISORY,
                    }
                }
            )
        )
        sys.stdout.write("\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
