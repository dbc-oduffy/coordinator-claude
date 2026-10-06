"""PostToolUseFailure advisory: a `command not found` tool error under a non-path PATH.

Fires on a hard tool failure whose `error` carries `command not found` or
`Executable not found in $PATH`. Emits one additionalContext advisory only when the
hook process's own PATH holds an element that cannot be a directory (placeholder
brackets, a literal `$` reference). Any other failure passes silently.

Blind by construction when `python3` itself is unresolvable: this hook then never runs.
Never blocks; always exits 0.

Second duty: a failed WebSearch call appends one `failure` row to the machine-local spend ledger
(coordinator/contract/websearch-ledger.md), independent of the advisory.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_ERROR_RE = re.compile(r"command not found|Executable not found in \$PATH")

_CLOUD_SETUP = "/root/cloud_setup.py"

ADVISORY = (
    "[path-fault] PATH holds a non-path element ({bad}). Break-class environment fault: "
    "report it, do not work around it silently. Repair PATH for this shell{pin}; hooks and "
    "subagents keep the broken PATH until `env.PATH` in ~/.claude/settings.json is pinned."
)


def _pin_hint() -> str:
    return f", or re-run `python3 {_CLOUD_SETUP}`" if os.path.isfile(_CLOUD_SETUP) else ""


def bad_path_elements(path_value: str) -> list[str]:
    """PATH elements that are unexpanded placeholders (`<dir>`, `$VAR`). Empty and relative elements
    (`.`, `node_modules/.bin`) are legitimate developer PATH entries and are skipped."""
    bad = []
    for el in path_value.split(os.pathsep):
        if not el:
            continue
        if re.search(r"[<>$]", el):
            bad.append(el)
    return bad


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") == "WebSearch":
        try:
            import _websearch_ledger

            _websearch_ledger.record(payload, "failure")
        except Exception:
            pass
    error = payload.get("error")
    if not isinstance(error, str) or not _ERROR_RE.search(error):
        return 0
    bad = bad_path_elements(os.environ.get("PATH", ""))
    if not bad:
        return 0
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
            "additionalContext": ADVISORY.format(bad=", ".join(bad[:3]), pin=_pin_hint()),
        }
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
