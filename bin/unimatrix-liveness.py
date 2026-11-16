#!/usr/bin/env python3
"""Spawn-free liveness for the unimatrix autolink supervisors: stdlib only, no subprocess.

Loaded by path (importlib spec_from_file_location). `proc_start` reproduces `ps -o lstart=` byte
for byte on POSIX (one-digit day space-padded) because recorded procStart strings are compared as text.
Boxes cache `autolink-boxes.json`: a json object with an "aliases" list; its mtime is the cache age.
"""
import json
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CACHE_NAME = "autolink-boxes.json"
CACHE_MAX_AGE = 24 * 3600
BACKOFF_BASE = 60
BACKOFF_CAP = 3600
ROLES = ("bridge", "inbox")
STILL_ACTIVE = 259
_PROC_PIDTBSDINFO = 3
_BSDINFO_SIZE = 136
_BSDINFO_TVSEC_OFFSET = 120


def settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def state_dir(home=None) -> Path:
    return Path(home if home is not None else settings_home()) / "unimatrix"


def _lstart(epoch) -> str:
    t = time.localtime(epoch)
    return time.strftime("%a %b ", t) + f"{t.tm_mday:2d}" + time.strftime(" %H:%M:%S %Y", t)


def _darwin_start(pid) -> str:
    import ctypes
    import ctypes.util
    lib = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib", use_errno=True)
    buf = ctypes.create_string_buffer(_BSDINFO_SIZE)
    got = lib.proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(_PROC_PIDTBSDINFO), ctypes.c_uint64(0),
                           buf, ctypes.c_int(_BSDINFO_SIZE))
    if got != _BSDINFO_SIZE:
        raise OSError(f"proc_pidinfo({pid}) returned {got}")
    (sec,) = struct.unpack_from("<Q", buf.raw, _BSDINFO_TVSEC_OFFSET)
    return _lstart(sec)


def _linux_start(pid) -> str:
    with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
        stat = fh.read()
    ticks = int(stat[stat.rindex(")") + 2:].split()[19])
    with open("/proc/stat", encoding="utf-8") as fh:
        btime = next(int(ln.split()[1]) for ln in fh if ln.startswith("btime "))
    return _lstart(btime + ticks // os.sysconf("SC_CLK_TCK"))


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


def pid_alive(pid):
    if pid <= 0:  # os.kill(0|-n, 0) would signal a process group
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


def supervisor_live(rec):
    """True when the recorded pid is alive and is the same process that was started."""
    pid = rec.get("pid") if isinstance(rec, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not pid_alive(pid):
        return False
    try:
        return proc_start(pid) == rec.get("procStart")
    except OSError:
        return False


def entry_live(d):
    """True when the entry's pid is alive and, if it records a procStart, is still that process.

    No recorded procStart, or an unreadable start, never proves staleness: pid liveness decides."""
    pid = d.get("pid") if isinstance(d, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or not pid_alive(pid):
        return False
    recorded = d.get("procStart")
    if not isinstance(recorded, str) or not recorded:
        return True
    try:
        return proc_start(pid) == recorded
    except OSError:
        return True


def stamp_fresh(d, field, max_age_seconds, now=None):
    """True when `d[field]` is an epoch-millisecond stamp no older than `max_age_seconds`.

    A missing, non-integer or future-dated stamp is not fresh."""
    stamp = d.get(field) if isinstance(d, dict) else None
    if not isinstance(stamp, int) or isinstance(stamp, bool):
        return False
    clock_ms = int((time.time() if now is None else now) * 1000)
    return 0 <= clock_ms - stamp <= max_age_seconds * 1000


def agy_face_unbacked(d, home=None):
    """True for a peer-router face of an agy session whose agy process is gone.

    The face is a proxy registered for `peers.json`'s `target` conversation; the agent behind it is
    the `agy_pid` its `agy-legs/<target>.json` record names. A face with no `peers.json` row has no
    conversation behind it and is unbacked. Anything else (not an agy router face, unreadable peers
    or leg record) is not provably unbacked and answers False."""
    if not isinstance(d, dict) or d.get("vendor") != "agy" or not d.get("unimatrixRouterPid"):
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
    agy_pid = rec.get("agy_pid") if isinstance(rec, dict) else None
    return not (isinstance(agy_pid, int) and not isinstance(agy_pid, bool) and pid_alive(agy_pid))


def agy_peer_rows_orphaned(home=None):
    """[(name, target)] for agy peers.json rows whose `agy-legs/<target>.json` record does not exist.

    Targets that are not safe file names are skipped; an unreadable peers.json answers []."""
    base = state_dir(home)
    rows = _peer_rows(base / "peers.json")
    return [(r.get("name"), r["target"]) for r in rows
            if r.get("vendor") == "agy" and isinstance(r.get("target"), str) and r["target"]
            and "/" not in r["target"] and "\\" not in r["target"]
            and not (base / "agy-legs" / f"{r['target']}.json").exists()]


def codex_holder_live(row):
    """Liveness of the Codex process a peer row recorded as `codexPid`/`codexProcStart`.

    True: holder alive and still that process. False: holder dead or its pid reused.
    None: the row records no holder, so liveness is unknown. An unreadable start is not staleness."""
    pid = row.get("codexPid") if isinstance(row, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    return entry_live({"pid": pid, "procStart": row.get("codexProcStart")})


CODEX_FACE_GRACE_SECONDS = 600


def codex_face_holder(d, home=None):
    """"live" | "dead" | "unknown" for a local Codex peer face's recorded holder; None when `d` is not
    a local Codex peer face or its `peers.json` row cannot be found or read (nothing provable).
    Trap: reads and parses `peers.json` on every call, uncached; keep callers to one call per face."""
    sid = d.get("sessionId") if isinstance(d, dict) else None
    if (not isinstance(sid, str) or not sid.startswith("peer-") or d.get("vendor") != "codex"
            or d.get("unimatrixMirror") or d.get("macSocketPath") or d.get("unimatrixRemote")):
        return None
    try:
        data = json.loads((state_dir(home) / "peers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = data.get("peers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None
    target = d.get("target")
    row = next((r for r in rows if isinstance(r, dict) and r.get("vendor") == "codex"
                and (r.get("target") == target if isinstance(target, str) else r.get("name") == d.get("name"))),
               None)
    if row is None:
        return None
    verdict = codex_holder_live(row)
    return "unknown" if verdict is None else ("live" if verdict else "dead")


def codex_holder_unbacked(state, d, now=None):
    """True when a Codex peer face has no live attached holder: its holder is dead, or none was ever
    recorded and the face is older than `CODEX_FACE_GRACE_SECONDS` (the session hook records it at start)."""
    if state == "dead":
        return True
    started = d.get("startedAt") if isinstance(d, dict) else None
    return (state == "unknown" and isinstance(started, int) and not isinstance(started, bool)
            and not stamp_fresh(d, "startedAt", CODEX_FACE_GRACE_SECONDS, now))


def far_codex_row_unbacked(d, now=None):
    """True for a far Codex row with no live holder: the far box reported "dead" or "unknown", or reported
    nothing (a box that never stamps `codexHolder` cannot prove life), and the row is past
    `CODEX_FACE_GRACE_SECONDS`. A row without an int `startedAt` is unprovable and answers False."""
    if not isinstance(d, dict) or d.get("vendor") != "codex":
        return False
    holder = d.get("codexHolder")
    return codex_holder_unbacked(holder if holder in ("live", "dead", "unknown") else "unknown", d, now)


def codex_face_unbacked(d, home=None, now=None):
    """True for a local Codex peer face with no live attached holder; anything unprovable answers False."""
    return codex_holder_unbacked(codex_face_holder(d, home), d, now)


def codex_thread_holder(codex_home, thread_id):
    """The `codexPid`/`codexProcStart` of the Codex process that last logged `thread_id`; {} when unknown.

    Reads the newest `process_uuid` ("pid:<n>:<uuid>") for the thread across `logs_*.sqlite`, read-only."""
    import re
    import sqlite3
    from contextlib import closing
    best = None
    for db in sorted(Path(codex_home).glob("logs_*.sqlite")):
        try:
            with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as conn:
                row = conn.execute("SELECT ts, ts_nanos, process_uuid FROM logs WHERE thread_id = ? "
                                   "AND process_uuid IS NOT NULL ORDER BY ts DESC, ts_nanos DESC LIMIT 1",
                                   (thread_id,)).fetchone()
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


def _peer_rows(peers_file):
    try:
        with open(peers_file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("peers") if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def codex_probe_lines(peers_file, locks_dir):
    """One `name target holder-pid cwd live|stale` line per Codex peer row, then per lock-only thread.

    Lock-only threads have no peers-file row, hence no recorded holder: they print stale."""
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


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "codex-probe":
        print("usage: unimatrix-liveness.py codex-probe [--peers FILE] [--locks-dir DIR]", file=sys.stderr)
        return 2
    opts = {"--peers": state_dir() / "peers.json", "--locks-dir": codex_locks_dir()}
    rest = args[1:]
    while rest:
        if rest[0] not in opts or len(rest) < 2:
            print(f"unimatrix-liveness.py codex-probe: bad argument {rest[0]!r}", file=sys.stderr)
            return 2
        opts[rest[0]] = Path(rest[1])
        rest = rest[2:]
    for line in codex_probe_lines(opts["--peers"], opts["--locks-dir"]):
        print(line)
    return 0


def read_record(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _slug(alias):
    return alias.replace("@", "_at_")


def healthy(state_dir, now=None, probe=None):
    """True only when the boxes cache is under 24h old and every listed alias has both supervisors live.

    A fresh cache listing zero aliases is healthy; a missing or unreadable cache is not.
    `probe(alias)` is an optional far-end check returning None (answered) or a reason string; it runs
    only after every local supervisor check passed, and any reason makes the result False. The probe
    owns its own short deadline: healthy() adds none."""
    sdir = Path(state_dir)
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
        # Concurrent: wall time is the slowest probe, not N*deadline; no short-circuit, every dead far end is recorded.
        with ThreadPoolExecutor(max_workers=min(len(aliases), 8)) as pool:
            answers = list(pool.map(probe, aliases))
        return all(a is None for a in answers)
    return True


def _backoff_path(state_dir, alias) -> Path:
    return Path(state_dir) / f"autolink-{_slug(alias)}.backoff.json"


def backoff_until(state_dir, alias):
    """Epoch before which `alias` is not probed; 0 when no backoff is recorded."""
    until = read_record(_backoff_path(state_dir, alias)).get("until")
    return float(until) if isinstance(until, (int, float)) and not isinstance(until, bool) else 0.0


def note_probe(state_dir, alias, ok, now=None) -> None:
    """Record a probe outcome: success removes the backoff, failure doubles it (60s base, 3600s cap)."""
    path = _backoff_path(state_dir, alias)
    if ok:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    now = time.time() if now is None else now
    prior = read_record(path).get("failures")
    failures = (prior if isinstance(prior, int) and not isinstance(prior, bool) and prior > 0 else 0) + 1
    delay = min(BACKOFF_BASE * 2 ** (failures - 1), BACKOFF_CAP)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"failures": failures, "until": now + delay}), encoding="utf-8")
    os.replace(tmp, path)


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-liveness [-h]\nunimatrix peer liveness probe")
        raise SystemExit(0)
    sys.exit(main())
