"""Classify unimatrix relay sessions (sshd forced-command children) as live, stale or mismatched, and reap.

Pure over its arguments: ps text, script timestamps, parent liveness and the kill callable are injected.
"""
from __future__ import annotations

import ntpath
import os
import signal
import subprocess
import time
from typing import NamedTuple

RELAY_SCRIPTS = ("unimatrix-relay.py", "unimatrix-file-relay.py")
PS_ARGV = ["ps", "-axo", "pid,ppid,lstart,command"]
PS_ENV_OVERRIDE = {"LC_ALL": "C"}

STALE = "stale"
MISMATCHED = "mismatched"
LIVE = "live"

_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


class RelaySession(NamedTuple):
    pid: int
    ppid: int
    started: float
    script: str
    command: str


def _parse_lstart(tokens: list[str]) -> float | None:
    """`Wed Nov 11 21:38:02 2026` (LC_ALL=C, local time) to epoch seconds."""
    try:
        _dow, mon, day, hms, year = tokens
        hh, mm, ss = (int(x) for x in hms.split(":"))
        return time.mktime((int(year), _MONTHS[mon], int(day), hh, mm, ss, 0, 0, -1))
    except (ValueError, KeyError):
        return None


def _relay_script(argv: list[str]) -> str | None:
    """The relay script basename when argv is `<script> ...` or `<python> <script> ...`; else None."""
    for i, tok in enumerate(argv[:2]):
        base = ntpath.basename(tok)
        if base in RELAY_SCRIPTS and (i == 0 or ntpath.basename(argv[0]).lower().startswith("python")):
            return base
    return None


def list_relay_sessions(ps_out: str) -> list[RelaySession]:
    """Relay sessions in `ps -axo pid,ppid,lstart,command` text; malformed lines are skipped."""
    sessions = []
    for line in ps_out.splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        started = _parse_lstart(parts[2:7])
        argv = parts[7:]
        script = _relay_script(argv)
        if started is None or script is None:
            continue
        sessions.append(RelaySession(pid, ppid, started, script, " ".join(argv)))
    return sessions


def classify_relay_sessions(sessions, relay_script_mtime, parent_alive, key=None) -> dict[str, list[RelaySession]]:
    """Split sessions into stale (orphaned: ppid 1 or parent gone, or superseded), mismatched (started
    before the installed script's timestamp, so it loaded replaced code) and live.

    `relay_script_mtime` is a float, or a mapping of script basename to float; callers pass the script's
    `st_ctime` (the install's copy sets it; copy2 preserves mtime). A script absent from the mapping
    cannot be judged mismatched. `parent_alive(ppid)` is a callable.

    `key(session)`, when given, groups sessions; every session but the newest of a group (latest
    `started`, highest pid on a tie) is stale: a successor with the same key supersedes it.
    """
    out: dict[str, list[RelaySession]] = {STALE: [], MISMATCHED: [], LIVE: []}
    newest: dict = {}
    if key is not None:
        for s in sessions:
            k = key(s)
            if k is not None and (k not in newest or (s.started, s.pid) > (newest[k].started, newest[k].pid)):
                newest[k] = s
    for s in sessions:
        stamp = relay_script_mtime.get(s.script) if isinstance(relay_script_mtime, dict) else relay_script_mtime
        k = key(s) if key is not None else None
        if s.ppid <= 1 or not parent_alive(s.ppid) or (k is not None and newest[k] is not s):
            out[STALE].append(s)
        elif stamp is not None and s.started < stamp:
            out[MISMATCHED].append(s)
        else:
            out[LIVE].append(s)
    return out


def reap(sessions, kill=None, release=None) -> tuple[list[int], list[int]]:
    """SIGTERM each session's pid via `kill(pid)`; returns (reaped, failed). An already-gone pid counts reaped.

    `release(session)`, when given, runs for each reaped session so the caller unlinks only the socket
    inode that session bound; a raising release never fails the reap.
    """
    kill = kill or (lambda pid: os.kill(pid, signal.SIGTERM))
    reaped, failed = [], []
    for s in sessions:
        try:
            kill(s.pid)
        except ProcessLookupError:
            pass
        except OSError:
            failed.append(s.pid)
            continue
        reaped.append(s.pid)
        if release is not None:
            try:
                release(s)
            except OSError:
                pass
    return reaped, failed


def ps_snapshot(run=subprocess.run) -> str:
    """One `ps` spawn with LC_ALL=C so lstart parses identically on every locale; empty text on failure."""
    try:
        res = run(PS_ARGV, capture_output=True, text=True, timeout=5,
                  env={**os.environ, **PS_ENV_OVERRIDE},
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout if res.returncode == 0 else ""
