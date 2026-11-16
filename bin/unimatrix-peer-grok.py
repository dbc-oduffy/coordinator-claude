#!/usr/bin/env python3
"""Grok adapter for the unimatrix peer router: registry discovery and one cwd-pinned headless resume.

Discovery reads <grok home>/active_sessions.json (no hooks). Delivery runs
`grok -p <text> -r <session> --cwd <session cwd> --output-format json` and returns the reply
text. Grok home: $GROK_HOME, else ~/.grok. Stdlib only: the script is vendored with no venv.
"""
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

TURN_TIMEOUT = 600
NO_REPLY = "[unimatrix-peer-grok] no reply before timeout"


def grok_home() -> Path:
    """Grok state dir: $GROK_HOME, else ~/.grok."""
    return Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")


def grok_binary(home=None):
    """The GROK_BIN environment variable, else grok on PATH, else <grok home>/bin/grok(.exe)."""
    configured = os.environ.get("GROK_BIN")
    if configured:
        return shutil.which(configured) or configured
    found = shutil.which("grok")
    if found:
        return found
    name = "grok.exe" if os.name == "nt" else "grok"
    return str(Path(home) if home else grok_home()) + os.sep + "bin" + os.sep + name


def _default_pid_alive(pid):
    spec = importlib.util.spec_from_file_location(
        "unimatrix_roster", Path(__file__).resolve().with_name("unimatrix-roster.py"))
    roster = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roster)
    return roster.pid_alive(pid)


def _contract() -> "ModuleType":
    """The peer contract module (box_id), loaded from the sibling script."""
    spec = importlib.util.spec_from_file_location(
        "unimatrix_peer_contract", Path(__file__).resolve().with_name("unimatrix-peer-contract.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clean(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")


def peer_name(session_id, cwd) -> str:
    """grok-<repo>-<first 8 of session id>-on-<box>; repo is the enclosing git root's name, else the cwd's."""
    base = str(cwd).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    path = Path(cwd)
    if path.is_absolute():
        try:
            root = next((p for p in (path, *path.parents) if (p / ".git").exists()), None)
        except OSError:
            root = None
        if root is not None and root.name:
            base = root.name
    return f"grok-{_clean(base) or 'session'}-{session_id[:8]}-on-{_clean(_contract().local_box())}"


def discover_peers(home=None, pid_alive=None, taken_names=(), taken_targets=()):
    """Peers for every live row of active_sessions.json: vendor grok, target the session id, cwd the row's.

    A row with a dead pid, a missing or malformed field, or a name or session already `taken_*`
    is skipped. An absent, unreadable or malformed registry yields no peers.
    """
    try:
        rows = json.loads((Path(home) if home else grok_home()).joinpath("active_sessions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    alive = pid_alive or _default_pid_alive
    peers, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid, cwd, pid = row.get("session_id"), row.get("cwd"), row.get("pid")
        if (not isinstance(sid, str) or not sid or not isinstance(cwd, str) or not cwd
                or type(pid) is not int or sid in taken_targets or sid in seen or not alive(pid)):
            continue
        name = peer_name(sid, cwd)
        if name in taken_names:
            continue
        seen.add(sid)
        peers.append({"name": name, "vendor": "grok", "target": sid, "cwd": cwd})
    return peers


def parent_pid(pid):
    """Parent pid of `pid`, else None. Linux /proc, Windows toolhelp snapshot, else `ps` (macOS/BSD)."""
    if os.name == "nt":
        return _parent_pid_windows(pid)
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        pass
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=5).stdout.strip()
        return int(out) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _parent_pid_windows(pid):
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for fn in (k32.Process32FirstW, k32.Process32NextW):
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        fn.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.th32ProcessID == pid:
                return entry.th32ParentProcessID or None
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return None


def own_session(home=None, pid_alive=None, parent_of=None, start=None, max_depth: int = 16):
    """Which Grok session is this shell? The live registry peer whose pid is an ancestor of `start`
    (default this process), else None. An empty registry skips the process walk."""
    try:
        rows = json.loads((Path(home) if home else grok_home()).joinpath("active_sessions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    by_pid = {}
    live = {p["target"]: p for p in discover_peers(home, pid_alive)}
    for row in rows:
        if isinstance(row, dict) and type(row.get("pid")) is int and row.get("session_id") in live:
            by_pid[row["pid"]] = live[row["session_id"]]
    if not by_pid:
        return None
    step = parent_of or parent_pid
    pid, seen = os.getpid() if start is None else start, set()
    for _ in range(max_depth):
        if pid in by_pid:
            return by_pid[pid]
        if pid is None or pid in seen:
            return None
        seen.add(pid)
        pid = step(pid)
    return None


def resume_argv(binary, session_id, text, cwd):
    """The headless resume argv: pinned to the session cwd, never --add-dir or --fork-session."""
    return [binary, "-p", text, "-r", session_id, "--cwd", cwd,
            "--output-format", "json", "--permission-mode", "dontAsk"]


def parse_reply(stdout):
    """The reply text of a `--output-format json` run, else None."""
    try:
        obj = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    text = obj.get("text") if isinstance(obj, dict) else None
    return text if isinstance(text, str) else None


async def grok_turn(session_id, cwd, text, timeout=TURN_TIMEOUT, binary=None, runner=subprocess.run):
    """One user turn into the grok session via headless resume; returns the reply or NO_REPLY.

    A timeout, non-zero exit, launch failure or unparsable stdout returns NO_REPLY.
    """
    argv = resume_argv(binary or grok_binary(), session_id, text, cwd)
    try:
        proc = await asyncio.to_thread(
            runner, argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (subprocess.TimeoutExpired, OSError):
        return NO_REPLY
    if proc.returncode != 0:
        return NO_REPLY
    reply = parse_reply(proc.stdout)
    return reply if reply else NO_REPLY


def main(argv=None) -> int:
    """`unimatrix-peer-grok.py <session-id> <cwd> <text>`: one turn into the session; prints the reply."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 3:
        sys.exit("usage: unimatrix-peer-grok.py <session-id> <cwd> <text>")
    print(asyncio.run(grok_turn(*argv)))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-peer-grok [-h]\nunimatrix Grok peer")
        raise SystemExit(0)
    sys.exit(main())
