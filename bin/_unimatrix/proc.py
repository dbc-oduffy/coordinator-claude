"""Spawn-free cross-platform process liveness, parent-pid, and host-session holder checks.

Stdlib-only and inert on import.
- macOS: ctypes libproc `proc_pidinfo(PROC_PIDTBSDINFO)` (offset 16 = pbi_ppid, offset 120 = pbi_start_tvsec).
- Linux: /proc/<pid>/stat + /proc/stat.
- Windows: kernel32 OpenProcess/GetProcessTimes/GetExitCodeProcess/CreateToolhelp32Snapshot.
"""
import json
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _unimatrix import transport as _transport_mod
from _unimatrix.paths import settings_home, state_dir

CACHE_NAME = "autolink-boxes.json"
CACHE_MAX_AGE = 24 * 3600
BACKOFF_BASE = 60
BACKOFF_CAP = 3600
KEYLESS_CAP = 6 * 3600
ROLES = ("bridge", "inbox")
STILL_ACTIVE = 259
_PROC_PIDTBSDINFO = 3
_BSDINFO_SIZE = 136
_BSDINFO_PPID_OFFSET = 16
_BSDINFO_TVSEC_OFFSET = 120
AGY_SESSION_GRACE_SECONDS = 60
CODEX_FACE_GRACE_SECONDS = 600


def _lstart(epoch) -> str:
    t = time.localtime(epoch)
    return time.strftime("%a %b ", t) + f"{t.tm_mday:2d}" + time.strftime(" %H:%M:%S %Y", t)


def _darwin_bsdinfo(pid) -> bytes:
    import ctypes
    import ctypes.util
    lib = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib", use_errno=True)
    buf = ctypes.create_string_buffer(_BSDINFO_SIZE)
    got = lib.proc_pidinfo(
        ctypes.c_int(pid), ctypes.c_int(_PROC_PIDTBSDINFO), ctypes.c_uint64(0),
        buf, ctypes.c_int(_BSDINFO_SIZE),
    )
    if got != _BSDINFO_SIZE:
        raise OSError(f"proc_pidinfo({pid}) returned {got}")
    return buf.raw


def _darwin_start(pid) -> str:
    raw = _darwin_bsdinfo(pid)
    (sec,) = struct.unpack_from("<Q", raw, _BSDINFO_TVSEC_OFFSET)
    return _lstart(sec)


def _darwin_parent_pid(pid) -> int | None:
    try:
        raw = _darwin_bsdinfo(pid)
        (ppid,) = struct.unpack_from("<I", raw, _BSDINFO_PPID_OFFSET)
        return int(ppid) if ppid > 0 else None
    except OSError:
        return None


def _linux_start(pid) -> str:
    """Raw /proc/<pid>/stat starttime ticks: the procStart Claude Code records on Linux."""
    with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
        stat = fh.read()
    return str(int(stat[stat.rindex(")") + 2:].split()[19]))


def linux_pid_domain() -> str:
    """`linux:<machine-id>:<pid namespace>`; bare `linux` when either part cannot be read."""
    machine_id = ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="utf-8") as fh:
                machine_id = fh.read().strip()
        except OSError:
            continue
        if machine_id:
            break
    try:
        ns = os.readlink("/proc/self/ns/pid")
    except OSError:
        ns = ""
    return f"linux:{machine_id}:{ns}" if machine_id and ns else "linux"


def _transport():
    return _transport_mod


def _win_filetime(pid) -> str:
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        raise OSError(f"cannot open pid {pid}")
    times = [wintypes.FILETIME() for _ in range(4)]
    ok = k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times])
    k32.CloseHandle(h)
    if not ok:
        raise OSError(f"GetProcessTimes failed for pid {pid}")
    return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)


def _parent_pid_windows(pid) -> int | None:
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260),
        ]

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


def parent_pid(pid, platform=None) -> int | None:
    """Spawn-free parent PID of `pid`, else None (macOS libproc, Linux /proc, Windows Toolhelp)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    plat = platform or sys.platform
    if plat == "win32" or os.name == "nt":
        return _parent_pid_windows(pid)
    if plat == "darwin":
        return _darwin_parent_pid(pid)
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        return ppid if ppid > 0 else None
    except (OSError, ValueError, IndexError):
        return None


def proc_start(pid, platform=None) -> str:
    """Process-start stamp as the harness records it; raises OSError when the pid cannot be read."""
    plat = platform or sys.platform
    try:
        if plat == "win32":
            return _win_filetime(pid)
        if plat == "darwin":
            return _darwin_start(pid)
        return _linux_start(pid)
    except (ValueError, StopIteration, IndexError, AttributeError, struct.error) as ex:
        raise OSError(f"cannot read start of pid {pid}: {type(ex).__name__}") from ex


def pid_alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def supervisor_live(rec) -> bool:
    """True when the recorded pid is alive and is the same process that was started."""
    pid = rec.get("pid") if isinstance(rec, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not pid_alive(pid):
        return False
    try:
        return proc_start(pid) == rec.get("procStart")
    except OSError:
        return False


def holder_proven_dead(d, pid_alive_fn=None, proc_start_fn=None) -> bool:
    """True only on proof the row's holder is gone: no int pid, a dead pid, or a live pid whose start
    stamp differs from the recorded procStart. A missing or unreadable start is not proof."""
    pid = d.get("pid") if isinstance(d, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not (pid_alive_fn or pid_alive)(pid):
        return True
    recorded = d.get("procStart")
    if not isinstance(recorded, str) or not recorded:
        return False
    try:
        return (proc_start_fn or proc_start)(pid) != recorded
    except OSError:
        return False


def entry_live(d, pid_alive_fn=None, proc_start_fn=None) -> bool:
    """True when the entry's pid is alive and, if it records a procStart, is still that process."""
    return not holder_proven_dead(d, pid_alive_fn, proc_start_fn)


def stamp_fresh(d, field, max_age_seconds, now=None) -> bool:
    """True when `d[field]` is an epoch-millisecond stamp no older than `max_age_seconds`."""
    stamp = d.get(field) if isinstance(d, dict) else None
    if not isinstance(stamp, int) or isinstance(stamp, bool):
        return False
    clock_ms = int((time.time() if now is None else now) * 1000)
    return 0 <= clock_ms - stamp <= max_age_seconds * 1000


def _safe_conversation(conversation) -> bool:
    return (isinstance(conversation, str) and bool(conversation) and "/" not in conversation
            and "\\" not in conversation and conversation not in (".", ".."))


def agy_presence_dir() -> Path:
    """Where agy keeps one presence lock per live conversation: next to its brain root (AGY_BRAIN_DIR)."""
    brain = os.environ.get("AGY_BRAIN_DIR")
    return (Path(brain).parent if brain else Path.home() / ".gemini" / "antigravity-cli") / "presence"


def agy_presence_held(conversation, presence_dir=None) -> bool:
    """True while another process holds the conversation's presence lock."""
    if not _safe_conversation(conversation):
        return False
    path = Path(presence_dir if presence_dir is not None else agy_presence_dir()) / f"{conversation}.lock"
    try:
        file = open(path, "r+b" if sys.platform == "win32" else "rb")
    except OSError:
        return False
    with file:
        try:
            if not _transport_mod.lock_file(file):
                return True
            _transport_mod.unlock_file(file)
        except (OSError, ImportError):
            return False
    return False


def _agy_record_age_origin(conversation, rec, home) -> float | None:
    for field in ("startedAt", "ts"):
        stamp = rec.get(field)
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and stamp > 0:
            return stamp / 1000 if stamp > 1e11 else float(stamp)
    if _safe_conversation(conversation):
        try:
            return (state_dir(home) / "agy-legs" / f"{conversation}.json").stat().st_mtime
        except OSError:
            return None
    return None


def agy_session_state(conversation, rec, home=None, now=None) -> str:
    """'live' | 'dead' | 'unknown' for a conversation's agy session."""
    if agy_presence_held(conversation):
        return "live"
    rec = rec if isinstance(rec, dict) else {}
    agy_pid = rec.get("agy_pid")
    if isinstance(agy_pid, int) and not isinstance(agy_pid, bool):
        recorded = rec.get("agy_proc_start")
        probe = {"pid": agy_pid, "procStart": recorded} if isinstance(recorded, str) and recorded else {"pid": agy_pid}
        return "live" if entry_live(probe) else "dead"
    origin = _agy_record_age_origin(conversation, rec, home)
    if origin is None:
        return "unknown"
    return "dead" if (time.time() if now is None else now) - origin > AGY_SESSION_GRACE_SECONDS else "unknown"


def agy_face_unbacked(d, home=None) -> bool:
    """True for a peer-router face of an agy session whose agy process is gone or whose leg is pending."""
    if (not isinstance(d, dict) or d.get("vendor") != "agy" or not d.get("unimatrixRouterPid")
            or d.get("unimatrixMirror") or d.get("macSocketPath") or d.get("unimatrixRemote")):
        return False
    base = state_dir(home)
    try:
        peers = json.loads((base / "peers.json").read_text(encoding="utf-8"))
        row = next((p for p in peers if isinstance(p, dict) and p.get("name") == d.get("name")), None)
    except (OSError, ValueError, TypeError):
        return False
    if row is None:
        return True
    target = row.get("target")
    if not isinstance(target, str) or not target or "/" in target or "\\" in target:
        return False
    try:
        rec = json.loads((base / "agy-legs" / f"{target}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False
    if not isinstance(rec, dict):
        return False
    if rec.get("mode", "live") != "live":  # a pending leg only spools: its face is not served; absent mode reads live
        return True
    return agy_session_state(target, rec, home) == "dead"


def _peer_rows(peers_file):
    try:
        with open(peers_file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("peers") if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def agy_peer_rows_orphaned(home=None) -> list:
    """[(name, target)] for agy peers.json rows whose leg is gone.

    Gone: `agy-legs/<target>.json` does not exist, or it records an int `pid` that is dead or no
    longer the process that stamped `procStart` (pid reused: the leg was replaced). A record that
    is unreadable or carries no pid is not proof of death and keeps its row."""
    base = state_dir(home)
    rows = _peer_rows(base / "peers.json")

    def leg_gone(target) -> bool:
        record = base / "agy-legs" / f"{target}.json"
        if not record.exists():
            return True
        try:
            rec = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        pid = rec.get("pid") if isinstance(rec, dict) else None
        return isinstance(pid, int) and not isinstance(pid, bool) and holder_proven_dead(rec)

    return [
        (r.get("name"), r["target"]) for r in rows
        if r.get("vendor") == "agy" and isinstance(r.get("target"), str) and r["target"]
        and "/" not in r["target"] and "\\" not in r["target"]
        and leg_gone(r["target"])
    ]


def codex_holder_live(row):
    """Liveness of the Codex process a peer row recorded as `codexPid`/`codexProcStart`."""
    pid = row.get("codexPid") if isinstance(row, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    if entry_live({"pid": pid, "procStart": row.get("codexProcStart")}):
        return True
    target = row.get("target")
    if row.get("vendor") != "codex" or not isinstance(target, str):
        return False
    code_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    return agy_presence_held(target, presence_dir=code_home / "thread-writer-locks")


def _codex_peer_rows(home=None) -> "list | None":
    """The `peers.json` rows as a list; None when the file is unreadable or not a row list."""
    try:
        data = json.loads((state_dir(home) / "peers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = data.get("peers") if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else None


def _codex_peer_row(d, rows) -> "dict | None":
    target = d.get("target")
    return next((r for r in rows or () if isinstance(r, dict) and r.get("vendor") == "codex"
                 and (r.get("target") == target if isinstance(target, str) else r.get("name") == d.get("name"))),
                None)


def codex_face_holder(d, home=None, peers=False) -> "str | None":
    """'live' | 'dead' | 'unknown' for a local Codex peer face's recorded holder; None when `d` is not
    a local Codex peer face or its `peers.json` row cannot be found or read (nothing provable).
    Trap: reads and parses `peers.json` on every call unless `peers` (a `_codex_peer_rows` result) is given."""
    sid = d.get("sessionId") if isinstance(d, dict) else None
    if (not isinstance(sid, str) or not sid.startswith("peer-") or d.get("vendor") != "codex"
            or d.get("unimatrixMirror") or d.get("macSocketPath") or d.get("unimatrixRemote")):
        return None
    row = _codex_peer_row(d, _codex_peer_rows(home) if peers is False else peers)
    if row is None:
        return None
    verdict = codex_holder_live(row)
    return "unknown" if verdict is None else ("live" if verdict else "dead")


def codex_holder_key(d, peers) -> "tuple | None":
    """Identity of the Codex session a local face fronts: ("pid", codexPid, codexProcStart) from its
    `peers.json` row, else ("target", thread id), else ("name", name). None for a non-local or non-Codex
    entry and for a face with none of the three (such faces are never collapsed)."""
    if (not isinstance(d, dict) or d.get("vendor") != "codex" or d.get("unimatrixMirror") or d.get("macSocketPath")
            or d.get("unimatrixRemote")):
        return None
    row = _codex_peer_row(d, peers) or {}
    pid = row.get("codexPid")
    if isinstance(pid, int) and not isinstance(pid, bool):
        return ("pid", pid, row.get("codexProcStart"))
    target = d.get("target")
    if isinstance(target, str) and target:
        return ("target", target)
    name = d.get("name")
    return ("name", name) if isinstance(name, str) and name else None


def _face_rank(e) -> tuple:
    """Survivor order: a sessionId face before a `peer-<name>-<pid>` transport face, then least name.

    Neither the pid nor `startedAt` is in it: both change when a face re-registers."""
    sid = e.get("sessionId")
    return (isinstance(sid, str) and sid.startswith("peer-"), str(e.get("name")), str(sid))


def codex_survivors(faces, peers) -> dict:
    """{id(face): surviving face} for every face that shares a holder key with the survivor of its key.

    Survivor per key: `_face_rank` least, so the same face is kept every tick and across its own
    re-registration. A face with no pid, thread or name is never collapsed."""
    groups = {}
    for e in faces:
        key = codex_holder_key(e, peers)
        if key is not None:
            groups.setdefault(key, []).append(e)
    out = {}
    for group in groups.values():
        best = min(group, key=_face_rank)
        out.update({id(e): best for e in group if e is not best})
    return out


def codex_superseded_faces(rows, home=None, now=None) -> dict:
    """{id(face): surviving face} for every live, backed local Codex face another face of its holder outranks.

    Reads `peers.json` once for the whole `rows` set."""
    peers = _codex_peer_rows(home)
    return codex_survivors([e for e in rows if entry_live(e)
                            and not codex_holder_unbacked(codex_face_holder(e, home, peers), e, now)], peers)


def codex_holder_unbacked(state, d, now=None):
    if state == "dead":
        return True
    started = d.get("startedAt") if isinstance(d, dict) else None
    return (state == "unknown" and isinstance(started, int) and not isinstance(started, bool)
            and not stamp_fresh(d, "startedAt", CODEX_FACE_GRACE_SECONDS, now))


def far_codex_row_unbacked(d, now=None):
    if not isinstance(d, dict) or d.get("vendor") != "codex":
        return False
    holder = d.get("codexHolder")
    return codex_holder_unbacked(holder if holder in ("live", "dead", "unknown") else "unknown", d, now)


def codex_face_unbacked(d, home=None, now=None):
    return codex_holder_unbacked(codex_face_holder(d, home), d, now)


def codex_thread_holder(codex_home, thread_id):
    import re
    import sqlite3
    from contextlib import closing
    best = None
    for db in sorted(Path(codex_home).glob("logs_*.sqlite")):
        try:
            with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as conn:
                row = conn.execute(
                    "SELECT ts, ts_nanos, process_uuid FROM logs WHERE thread_id = ? "
                    "AND process_uuid IS NOT NULL ORDER BY ts DESC, ts_nanos DESC LIMIT 1",
                    (thread_id,),
                ).fetchone()
        except (sqlite3.Error, ValueError, OSError):
            continue
        if row and (best is None or row[:2] > best[:2]):
            best = row
    match = re.match(r"pid:(\d+):", best[2]) if best else None
    if not match or int(match.group(1)) <= 0:
        return {}
    pid = int(match.group(1))
    holder = {"codexPid": pid}
    try:
        holder["codexProcStart"] = proc_start(pid)
    except OSError:
        pass
    return holder


def codex_locks_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "thread-writer-locks"


def codex_probe_lines(peers_file, locks_dir):
    lines, seen = [], set()
    for row in _peer_rows(peers_file):
        if row.get("vendor") != "codex":
            continue
        target = str(row.get("target", ""))
        seen.add(target)
        pid = row.get("codexPid")
        shown = pid if isinstance(pid, int) and not isinstance(pid, bool) else "-"
        verdict = "live" if codex_holder_live(row) is True else "stale"
        lines.append(f"{row.get('name', '-')} {target or '-'} {shown} {row.get('cwd') or '-'} {verdict}")
    try:
        names = sorted(os.listdir(locks_dir))
    except OSError:
        names = []
    for f in names:
        ident = f[:-len(".lock")]
        if f.startswith(".") or not f.endswith(".lock") or not ident or ident in seen:
            continue
        lines.append(f"codex-{ident} {ident} - - stale")
    return lines


def read_record(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _slug(alias):
    return alias.replace("@", "_at_")


def healthy(sdir, now=None, probe=None):
    sdir = Path(sdir)
    cache = sdir / CACHE_NAME
    now = time.time() if now is None else now
    try:
        age = now - cache.stat().st_mtime
    except OSError:
        return False
    if age >= CACHE_MAX_AGE:
        return False
    aliases = read_record(cache).get("aliases")
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        return False
    for alias in aliases:
        rec = read_record(sdir / f"autolink-{_slug(alias)}.json")
        if not all(supervisor_live(rec.get(role) or {}) for role in ROLES):
            return False
    if probe is not None:
        if not aliases:
            return True
        with ThreadPoolExecutor(max_workers=min(len(aliases), 8)) as pool:
            answers = list(pool.map(probe, aliases))
        return all(a is None for a in answers)
    return True


def _backoff_path(sdir, alias) -> Path:
    return Path(sdir) / f"autolink-{_slug(alias)}.backoff.json"


def backoff_until(sdir, alias):
    until = read_record(_backoff_path(sdir, alias)).get("until")
    return float(until) if isinstance(until, (int, float)) and not isinstance(until, bool) else 0.0


def _store_record(path, rec) -> None:
    """Write `rec` atomically, or remove the file when `rec` is empty."""
    if not rec:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    os.replace(tmp, path)


def _park_fields(rec) -> dict:
    return {k: rec[k] for k in ("parked", "parkedAt", "reason") if k in rec} if rec.get("parked") is True else {}


def _charge(sdir, alias, now, base, cap) -> None:
    """Double the alias's backoff delay; a recorded `until` that is later is kept, and a park is carried over."""
    path = _backoff_path(sdir, alias)
    now = time.time() if now is None else now
    rec = read_record(path)
    prior = rec.get("failures")
    failures = (prior if isinstance(prior, int) and not isinstance(prior, bool) and prior > 0 else 0) + 1
    until = now + min(base * 2 ** min(failures - 1, 40), cap)
    held = rec.get("until")
    if isinstance(held, (int, float)) and not isinstance(held, bool):
        until = max(until, float(held))
    _store_record(path, {"failures": failures, "until": until, **_park_fields(rec)})


def note_probe(sdir, alias, ok, now=None) -> None:
    """Record a probe outcome: success removes the backoff, failure doubles it (60s base, 3600s cap).

    A PM-held park survives both outcomes; a recorded `until` later than the computed one is never shortened."""
    if ok:
        path = _backoff_path(sdir, alias)
        _store_record(path, _park_fields(read_record(path)))
        return
    _charge(sdir, alias, now, BACKOFF_BASE, BACKOFF_CAP)


def note_keyless(sdir, alias, now=None) -> None:
    """Charge a far box that has no local key: the same doubling from 60s, bounded by KEYLESS_CAP."""
    _charge(sdir, alias, now, BACKOFF_BASE, KEYLESS_CAP)


def is_parked(sdir, alias) -> bool:
    """True while a PM-held park is recorded for `alias`; only `release` ends it."""
    return read_record(_backoff_path(sdir, alias)).get("parked") is True


def park(sdir, alias, reason=None, now=None) -> None:
    """Hold `alias` out of every autolink pass, the boot and restart passes included, until `release`."""
    path = _backoff_path(sdir, alias)
    rec = read_record(path)
    rec.update({"parked": True, "parkedAt": time.time() if now is None else now})
    if reason:
        rec["reason"] = reason
    Path(sdir).mkdir(parents=True, exist_ok=True)
    _store_record(path, rec)


def release(sdir, alias) -> bool:
    """End a park; the rest of the backoff record stays. False when `alias` was not parked."""
    path = _backoff_path(sdir, alias)
    rec = read_record(path)
    if rec.get("parked") is not True:
        return False
    _store_record(path, {k: v for k, v in rec.items() if k not in ("parked", "parkedAt", "reason")})
    return True
