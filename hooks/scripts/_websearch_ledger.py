"""Machine-local WebSearch spend ledger: append one row per WebSearch call, read counts back.

Contract: coordinator/contract/websearch-ledger.md. Fail-open invariant: `record` swallows every
exception so a ledger fault never touches a host hook's output or exit code. Trap: this module spawns
no child process of any kind; the spawn census walks it transitively from its hosts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LEDGER_REL = ("state", "websearch-ledger.jsonl")
ROW_VERSION = 1
TOOL_NAME = "WebSearch"
ROW_KEYS = ("v", "ts", "session_id", "agent_id", "outcome", "cwd")


def ledger_path() -> Path:
    """Return `<settings_home>/state/websearch-ledger.jsonl`."""
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    home = Path(env) if env else Path.home() / ".coordinator-claude-settings"
    return home.joinpath(*LEDGER_REL)


def record(payload: dict, outcome: str) -> None:
    """Append one row for a WebSearch payload; no-op otherwise. Never raises."""
    try:
        if payload.get("tool_name") != TOOL_NAME:
            return
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return
        row = {
            "v": ROW_VERSION,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": session_id,
            "agent_id": payload.get("agent_id"),
            "outcome": outcome,
            "cwd": payload.get("cwd"),
        }
        line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:
        return


def read_rows(path: Path | None = None) -> list[dict]:
    """Return parsed rows; absent file gives []; torn or non-dict lines are skipped."""
    path = path or ledger_path()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def count_by_session(path: Path | None = None) -> dict[str, int]:
    """Count rows per session_id, ok and failure alike."""
    counts: dict[str, int] = {}
    for row in read_rows(path):
        sid = row.get("session_id")
        if isinstance(sid, str):
            counts[sid] = counts.get(sid, 0) + 1
    return counts
