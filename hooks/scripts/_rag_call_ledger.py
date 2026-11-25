"""Machine-local project-rag call ledger: append one row per project-rag tool call, read the state back.

Contract: coordinator/contract/rag-call-ledger.md. Fail-open invariant: `record` swallows every
exception so a ledger fault never touches a host hook's output or exit code. Trap: this module spawns
no child process of any kind; the spawn census walks it transitively from its hosts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LEDGER_REL = ("state", "rag-call-ledger.jsonl")
ROW_VERSION = 1
MAX_LEDGER_BYTES = 1_048_576
ROTATED_SUFFIX = ".old"
ROW_KEYS = ("v", "ts", "session_id", "agent_id", "tool", "outcome")
OUTCOMES = ("ok", "down")
STATE_NONE = "none"
STATE_OK = "ok"
STATE_DOWN = "down"


def ledger_path() -> Path:
    """Return `<settings_home>/state/rag-call-ledger.jsonl`."""
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    home = Path(env) if env else Path.home() / ".coordinator-claude-settings"
    return home.joinpath(*LEDGER_REL)


def is_rag_tool(tool_name: object) -> bool:
    """True for an MCP tool name served by a project-rag server (hyphen or underscore form)."""
    if not isinstance(tool_name, str) or not tool_name.startswith("mcp__"):
        return False
    return "project-rag" in tool_name or "project_rag" in tool_name


def _rotate_if_large(path: Path) -> None:
    """Bound the ledger: past MAX_LEDGER_BYTES, replace `<ledger>.old` with the live file. Never raises.

    `state_for` reads the `.old` file too, so one rotation never erases a session's rows; two rotations in one session would.
    """
    try:
        if path.stat().st_size > MAX_LEDGER_BYTES:
            os.replace(path, path.with_name(path.name + ROTATED_SUFFIX))
    except OSError:
        return


def record(payload: dict, outcome: str) -> None:
    """Append one row for a project-rag tool_use payload; no-op otherwise. Never raises."""
    try:
        if outcome not in OUTCOMES:
            return
        tool = payload.get("tool_name")
        if not is_rag_tool(tool):
            return
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return
        row = {
            "v": ROW_VERSION,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": session_id,
            "agent_id": payload.get("agent_id"),
            "tool": tool,
            "outcome": outcome,
        }
        line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_large(path)
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


def state_for(session_id: str, agent_id: str | None = None, path: Path | None = None) -> str:
    """Return `ok`, `down` or `none` for rows of this session and agent_id (None = main thread).

    Any `ok` row wins; else any `down` row gives `down`; else `none`. Never raises.
    """
    try:
        seen_down = False
        live = path or ledger_path()
        for row in (*read_rows(live.with_name(live.name + ROTATED_SUFFIX)), *read_rows(live)):
            if row.get("session_id") != session_id or row.get("agent_id") != agent_id:
                continue
            outcome = row.get("outcome")
            if outcome == STATE_OK:
                return STATE_OK
            if outcome == STATE_DOWN:
                seen_down = True
        return STATE_DOWN if seen_down else STATE_NONE
    except Exception:
        return STATE_NONE
