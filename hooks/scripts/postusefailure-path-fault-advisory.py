#!/usr/bin/env python3
"""PostToolUseFailure advisory: a `command not found` tool error under a non-path PATH.

Fires on a hard tool failure whose `error` carries `command not found` or
`Executable not found in $PATH`. Emits one additionalContext advisory only when the
hook process's own PATH holds an element that cannot be a directory (placeholder
brackets, a literal `$` reference, a relative entry). Any other failure passes silently.

Blind by construction when `python3` itself is unresolvable: this hook then never runs.
Never blocks; always exits 0.
"""

from __future__ import annotations

import json
import os
import re
import sys

_ERROR_RE = re.compile(r"command not found|Executable not found in \$PATH")

ADVISORY = (
    "[path-fault] PATH holds a non-path element ({bad}). Break-class environment fault: "
    "report it, do not work around it silently. Repair in-session: prefix commands with "
    "`export PATH=<real dirs>:/usr/local/bin:/usr/bin:/bin`, or re-run the pin step "
    "(`python3 /root/cloud_setup.py`). Hooks and subagents keep the broken PATH until "
    "`env.PATH` in ~/.claude/settings.json is pinned."
)


def bad_path_elements(path_value: str) -> list[str]:
    """PATH elements that cannot name a directory: empty-string elements are legal and skipped."""
    bad = []
    for el in path_value.split(os.pathsep):
        if not el:
            continue
        if re.search(r"[<>$]", el) or not os.path.isabs(el):
            bad.append(el)
    return bad


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    error = payload.get("error")
    if not isinstance(error, str) or not _ERROR_RE.search(error):
        return 0
    bad = bad_path_elements(os.environ.get("PATH", ""))
    if not bad:
        return 0
    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
            "additionalContext": ADVISORY.format(bad=", ".join(bad[:3])),
        }
    }
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
