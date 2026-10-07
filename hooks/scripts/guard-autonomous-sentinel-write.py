"""PreToolUse guard: deny Write/Edit/MultiEdit/NotebookEdit against the
session-scoped autonomous sentinel `<gettempdir()>/coordinator/_fleet/autonomous-run-<sid>`
(and the legacy bare `<gettempdir()>/autonomous-run-<sid>` during the dual-read window).

The shared `_sentinel_write_guard` helper matches fixed basenames only, so
this consumer resolves the session-scoped name itself (basename prefix
`autonomous-run-` AND parent equal to the resolved temp directory) and then
delegates the denial to `sentinel_write_denial`.

Contract:
  - Deletion stays reachable (not a guarded tool); the Bash `autonomous-verb`
    writer is never blocked (Bash is not a guarded tool).
  - The sentinel is posture, not authority; the fleet grant is the
    authorization of record. This guard does not cover the Bash leg.
  - `/tmp` and `%TEMP%` are one path: on Windows a tool-call path beginning
    `/tmp/` maps to `tempfile.gettempdir()`; both sides pass through
    `realpath` and `normcase`.
  - Any failure fails open (exit 0, no stdout).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _coordinator_temp import coordinator_temp_root  # noqa: E402
from _sentinel_write_guard import extract_target_path, sentinel_write_denial  # noqa: E402

SENTINEL_PREFIX = "autonomous-run-"

_REASON = (
    "The autonomous sentinel is written only by `autonomous-sentinel "
    "enable` (the /autonomous verb); a direct file write is refused. "
    "Run /autonomous instead."
)


def _canon(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _map_tmp(path: str) -> str:
    """Map a POSIX-spelled `/tmp/` path to the real temp dir on Windows."""
    if os.name == "nt":
        norm = path.replace("\\", "/")
        if norm == "/tmp" or norm.startswith("/tmp/"):
            return os.path.join(tempfile.gettempdir(), norm[len("/tmp/"):])
    return path


def is_autonomous_sentinel(target_path: str) -> bool:
    """True when target_path is `autonomous-run-<sid>` directly inside the temp dir."""
    if not target_path:
        return False
    resolved = _canon(_map_tmp(target_path))
    base = os.path.basename(resolved)
    if not base.startswith(os.path.normcase(SENTINEL_PREFIX)) or base == os.path.normcase(
        SENTINEL_PREFIX
    ):
        return False
    parent = os.path.dirname(resolved)
    return parent in (_canon(tempfile.gettempdir()), _canon(str(coordinator_temp_root("_fleet"))))


def denial_for(tool_input: dict) -> "dict | None":
    target = extract_target_path(tool_input)
    if not is_autonomous_sentinel(target):
        return None
    name = os.path.basename(_canon(_map_tmp(target)))
    return sentinel_write_denial(_canon(_map_tmp(target)), name, _REASON)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        if payload.get("tool_name") not in (
            "Write", "Edit", "MultiEdit", "NotebookEdit"
        ):
            return 0
        result = denial_for(payload.get("tool_input") or {})
    except Exception:
        return 0
    if result:
        sys.stdout.write(json.dumps(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
