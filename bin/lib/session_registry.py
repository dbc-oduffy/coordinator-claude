"""
coordinator.bin.lib.session_registry -- shared reader for the harness session registry
(``~/.claude/sessions/*.json``), consolidated out of `group-em-nomination.py`,
`resolve-peer-address.py` and `statusline.py`, which each carried a near-identical copy.

Purpose: every `coordinator/bin/` script that needs to know which sessions are live on this
machine -- and whether a given `pid` is one of them -- reads the same on-disk shape. Keeping one
copy means a schema change (e.g. the `sessionId`/`session_id` key drift already observed between
callers) is fixed once, not N times.

NEGATIVE SPEC:

  - It does NOT cache anything. Every call scans or reads fresh; callers that want a memo (e.g.
    `statusline.py`'s long-lived-process `_peer_name` path) build it on top of this module, at
    the layer that knows its own call frequency.
  - It does NOT decide liveness policy beyond "is this pid a running process" -- what a dead pid
    or missing registry row MEANS to a caller (not-live, no-nomination, etc.) is the caller's call.

`find_registry_row` and `is_live` were lifted out of `group-em-nomination.py`
(`coordinator/bin/group-em-nomination.py`'s own negative spec, unchanged by the move): a record's
own `pid` field is never a liveness signal -- a pid written by a CLI subprocess is that
subprocess's own, dead on exit -- so liveness comes ONLY from joining a record's `session_id`
against THIS registry's own published `pid` for that session, fresh on every call, never cached
at any layer. `group-em-nomination.py` and `coordinator/bin/navi-singleton.py` both import these
rather than each carrying their own copy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NamedTuple, Optional


class RegistryRow(NamedTuple):

    session_id: str
    name: str
    pid: int
    cwd: str
    status: str
    path: Optional[Path] = None


def registry_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    root = Path(override) if override else Path.home() / ".claude"
    return root / "sessions"


def parse_row(path: Path) -> Optional[RegistryRow]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    session_id = data.get("sessionId") or data.get("session_id")
    if not session_id:
        return None
    try:
        pid = int(data.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    return RegistryRow(
        session_id=str(session_id),
        name=str(data.get("name") or ""),
        pid=pid,
        cwd=str(data.get("cwd") or ""),
        status=str(data.get("status") or ""),
        path=path,
    )


def read_rows(directory: Optional[Path] = None) -> list[RegistryRow]:
    directory = directory or registry_dir()
    rows: list[RegistryRow] = []
    try:
        entries = sorted(directory.glob("*.json"))
    except OSError:
        return rows
    for path in entries:
        row = parse_row(path)
        if row is not None:
            rows.append(row)
    return rows


def _pid_alive_windows(pid: int) -> bool:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return True
    finally:
        kernel32.CloseHandle(handle)


def _pid_alive_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    arm = _pid_alive_windows if os.name == "nt" else _pid_alive_posix
    return arm(pid)


def find_registry_row(
    session_id: str, directory: Optional[Path] = None
) -> Optional[RegistryRow]:
    for row in read_rows(directory):
        if row.session_id == session_id:
            return row
    return None


def is_live(
    record: dict, registry_dir: Optional[Path] = None
) -> tuple[bool, Optional[RegistryRow]]:
    session_id = str(record.get("session_id") or "")
    if not session_id:
        return False, None
    row = find_registry_row(session_id, registry_dir)
    if row is None:
        return False, None
    return pid_alive(row.pid), row


def liveness_annotation(
    record: dict, registry_dir: Optional[Path] = None
) -> tuple[bool, str, str]:
    live, row = is_live(record, registry_dir)
    if live:
        return True, "live", "live"
    if row is None:
        return False, "no_registry_record", "not live (no registry record for this session)"
    return False, "pid_not_running", "not live (registry record present, process not running)"
