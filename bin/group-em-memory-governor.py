"""group-em-memory-governor — pause the command that pushed the box into critical memory pressure.

Started from a Claude Code session it detaches itself on start (outside the session's process tree
and job, so the session's low-memory reap cannot kill it), prints `DETACHED ... log=PATH` and exits;
the detached child appends to `--log` (default `<settings home>/scratch/governor.log`).
`group-em-memory-governor-wait.py <log>` is the one-shot wake on that log. Never run it under a
`Monitor`: the Monitor's 30-minute expiry kills the governor, wakes the Group EM for nothing, and
re-arming costs a turn. It samples the kernel's own pressure verdict and
stays silent while the box is anything short of critical. On critical it suspends the youngest
heavy command (a test runner, typecheck, build, dev server, browser run) together with its
descendants, then prints one line. If the box stays critical it suspends the next youngest, up to
`--max-pauses`. Once the verdict has been non-critical for `--resume-after` consecutive samples it
resumes everything it paused, newest first, and prints one line. Every printed line is an action
the Group EM relays to the command's owner; nothing else is printed, so the waiter wakes nobody
for a warn and its output is never filtered.

Independently of pressure, every `--runaway-every` samples it reads each process's full footprint
(resident plus compressed plus swapped) and prints one RUNAWAY line, once per pid, for any process
over `--runaway-mb`. Pausing never frees memory, and a process paging itself out reads as a tiny
RSS, so a single runaway shows up only here. The Group EM decides whether to kill it.

Every sample, from the tick's one process snapshot, it kills each orphaned grep/find/xargs/rg tree
whole (the bash wrapper and every descendant): one whose root's parent has exited (`owner-gone`: the
Bash call that started it ended) or that is older than `REAP_AGE_S` (`age`). It appends one jsonl
record per reap to `--reap-log` and prints one `GOVERNOR REAPED pid=.. reason=..` line. A tree
holding any process that is not a shell or a search tool, or whose launcher registered it with
`--guard PID` (a fresh heartbeat), is never reaped or paused.

Critical, per OS: macOS `kern.memorystatus_vm_pressure_level == 4`; Linux PSI
`/proc/pressure/memory` `full avg10 >= --psi-full`; elsewhere (Windows) available memory under
`--avail-pct` percent of total, read through `host_sampler.avail_mb`.

On a critical sample only, it also reads the tail of the box admission channel
(`admission.jsonl`, the engine's `admission_path()`): a live pid named by a START line is a pause
candidate whatever HEAVY or MIN_RSS_MB say, and its tree loses the project-rag exemption.

Never suspended: harness and editor processes (claude, tsserver, language servers), project-rag
servers (unless launched and noticed on the admission channel), anything in a deploy (Firebase
CLI, `deploy-from-snapshot`, `deploy:`, a `scratch/deploy-` snapshot tree), and this process. Suspending a deploy mid-upload could leave prod half-released;
suspending a language server hangs every LSP call in its session.

On win32 only, the first critical sample of an episode fires the PM-installed on-demand scheduled
task BoxCacheTrim and prints one `GOVERNOR CACHE-TRIM fired <trim.log tail>` line; with no such task
it prints one GOVERNOR CACHE-TRIM-HINT line naming the elevated `trim-file-cache.py --apply`
command. A calm verdict re-arms it, but the fire (or hint) happens at most once per
`TRIM_COOLDOWN_S` and only while the file cache holds at least `CACHE_CAUSE_GIB` (unreadable counts as yes).

When available memory rises `HEADROOM_RISE_GIB` over its low-water mark, or the verdict goes calm
after a PAUSED, it prints one `GOVERNOR HEADROOM available=<GiB>` line so the Group EM wakes.

Hourly (first tick, then every `RETENTION_EVERY` samples) it stamp-checks the engine's
`retention_run` and spawns it detached when due; the governor itself deletes no file. On the same
tick it prints one `GOVERNOR SCRATCH-OVER-BUDGET` line per session whose Temp scratch exceeds
`scratch_budget.per_session_gib` (report only; the engine sweep does the deleting).

NEGATIVE SPEC: suspends and resumes, and kills only whole orphaned grep/find/xargs/rg trees; never
trims the cache itself, never creates or schedules a task (it only fires the existing BoxCacheTrim);
never signals a protected or guarded process; reads the box admission channel and the guard
registrations; writes only stdout, the reap jsonl, its frozen-pid file, and (via `--guard`) a guard
registration. A suspended process it can no longer find
(exited) is dropped silently.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import psutil  # type: ignore
except ImportError:  # POSIX falls back to ps/kill; Windows needs psutil
    psutil = None

HEAVY = re.compile(
    r"vitest|\btsc\b|next build|next-server|next dev|playwright|\btsx\b|jest|turbo run"
    r"|pnpm (?:-r|--recursive|build|test|typecheck)|build:[\w-]+"
)
PROTECTED_HARD = re.compile(
    r"(?:^|/)claude(?:\.exe)?(?:\s|$)|tsserver|language-server|firebase"
    r"|lang(?:uage)?[-_]?server|pyright|(?:^|[^a-z])mcp(?:[^a-z]|$)"
    r"|deploy-from-snapshot|deploy:"
    r"|scratch/deploy-|group-em-memory-governor|(?:^|[/\\])conhost(?:\.exe)?(?:\s|$)"
    # Store and database owners: freezing one mid-write stalls or half-applies every client's write.
    r"|(?:^|[/\\])owner\.ts\b|pglite|(?:^|[/\\\s])postgres(?:\.exe)?\b|\bmysqld\b|\bmongod\b"
    r"|\bredis-server\b|\bsqlite3?(?:\.exe)?\b"
)
PROJECT_RAG = re.compile(r"project_rag")
MIN_RSS_MB = 300
NOTICE_TAIL_BYTES = 65536


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    age_s: float
    rss_mb: float
    cmd: str
    image: str = ""  # image name from the process table; names the program when `cmd` is unreadable


def is_protected(p: Proc, noticed_tree: frozenset = frozenset(),
                 guarded: frozenset = frozenset()) -> bool:
    """Harness, language-server, deploy, self and a tree whose launcher registration is fresh are
    always protected; project-rag is protected unless the process belongs to a launch noticed on
    the admission channel."""
    if p.pid in guarded or PROTECTED_HARD.search(p.cmd):
        return True
    return bool(PROJECT_RAG.search(p.cmd)) and p.pid not in noticed_tree


def is_candidate(p: Proc, self_pid: int, noticed: frozenset = frozenset(),
                 noticed_tree: frozenset = frozenset(), guarded: frozenset = frozenset()) -> bool:
    if p.pid == self_pid or is_protected(p, noticed_tree, guarded):
        return False
    return p.pid in noticed or (p.rss_mb >= MIN_RSS_MB and bool(HEAVY.search(p.cmd)))


def choose_victim(procs: list[Proc], paused: set[int], self_pid: int,
                  noticed: frozenset = frozenset(), tree: frozenset = frozenset(),
                  shortfall_mb: float = 0.0, guarded: frozenset = frozenset()) -> Optional[Proc]:
    """The candidate whose tree frees the most RSS when paused; ties go to the youngest.

    A worker whose parent is itself a candidate is never chosen alone; its parent's tree covers it.
    A tree freeing less than `shortfall_mb` (or MIN_RSS_MB) cannot relieve the pressure and is skipped.
    """
    heavy = {p.pid for p in procs if is_candidate(p, self_pid, noticed, tree, guarded)}
    rss = {p.pid: p.rss_mb for p in procs}
    floor = max(MIN_RSS_MB, shortfall_mb)
    freed = {p.pid: sum(rss.get(t, 0.0) for t in descendants(p.pid, procs))
             for p in procs if p.pid in heavy and p.pid not in paused and p.ppid not in heavy}
    pool = [p for p in procs if freed.get(p.pid, 0.0) >= floor]
    return min(pool, key=lambda p: (-freed[p.pid], p.age_s)) if pool else None


def noticed_tree(noticed: frozenset, procs: list[Proc]) -> frozenset:
    return frozenset(t for root in noticed for t in descendants(root, procs))


def read_noticed_pids(path: Optional[Path], procs: list[Proc]) -> frozenset:
    """Live pids named by START lines in the tail of the box admission channel; empty on any fault."""
    if path is None:
        return frozenset()
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - NOTICE_TAIL_BYTES))
            raw = fh.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if size > NOTICE_TAIL_BYTES:
            lines = lines[1:]  # first line of a mid-file tail is cut
        live = {p.pid for p in procs}
        out: set[int] = set()
        for line in lines:
            try:
                rec = json.loads(line)
                phase = rec.get("phase")
                ids = {int(x) for x in rec.get("pids") or []}
                if phase == "START":
                    out.update(i for i in ids if i in live)
                elif phase == "END":
                    out.difference_update(ids)
            except (ValueError, TypeError, AttributeError):
                continue
        return frozenset(out)
    except OSError:
        return frozenset()


def _place_engine_on_path() -> bool:
    """Put the resolved engine checkout on `sys.path`; False when it is unresolvable."""
    lib = str(Path(__file__).resolve().parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import cc_invoke  # type: ignore
    return cc_invoke.ensure_engine_on_path(__file__) is not None


def resolve_notice_path() -> Optional[Path]:
    """The engine's admission channel path, or None when the engine is unresolvable."""
    try:
        if not _place_engine_on_path():
            return None
        from coordinator_core.group_em.admission_post import admission_path  # type: ignore
        return Path(admission_path())
    except Exception:  # fail open: no notice input, behaviour unchanged
        return None


def descendants(root: int, procs: list[Proc]) -> list[int]:
    kids: dict[int, list[int]] = {}
    for p in procs:
        kids.setdefault(p.ppid, []).append(p.pid)
    out, stack = [], [root]
    while stack:
        pid = stack.pop()
        out.append(pid)
        stack.extend(kids.get(pid, []))
    return out


def protected_pids(procs: list[Proc], noticed_tree: frozenset = frozenset(),
                   guarded: frozenset = frozenset()) -> set[int]:
    return {p.pid for p in procs if is_protected(p, noticed_tree, guarded)}


def _etime_seconds(etime: str) -> float:
    days, _, rest = etime.rpartition("-")
    parts = [int(x) for x in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return (int(days) if days else 0) * 86400 + h * 3600 + m * 60 + s


_FILETIME_EPOCH_S = 11644473600
#: Images whose command line is read (one psutil call each) after the snapshot; every other pid keeps
#: its image name as `cmd`. A process at or over MIN_RSS_MB is also read, since HEAVY matches
#: (node, tsc, vitest) need arguments. The bound is the few matching pids, never the whole table.
_CMDLINE_IMAGES = frozenset({"bash", "sh", "grep", "egrep", "fgrep", "find", "xargs", "rg", "python",
                             "python3", "pythonw"})


def parse_system_process_information(buf: bytes, base: int, now: float) -> list[Proc]:
    """Procs from one NtQuerySystemInformation(SystemProcessInformation) x64 buffer.

    `base` is the address the buffer lives at: each ImageName.Buffer points into it. `cmd` is the
    image name only; age comes from CreateTime, rss from WorkingSetSize."""
    out: list[Proc] = []
    off = 0
    while True:
        nxt = int.from_bytes(buf[off:off + 4], "little")
        create = int.from_bytes(buf[off + 32:off + 40], "little")
        nlen = int.from_bytes(buf[off + 56:off + 58], "little")
        nptr = int.from_bytes(buf[off + 64:off + 72], "little")
        pid = int.from_bytes(buf[off + 80:off + 88], "little")
        ppid = int.from_bytes(buf[off + 88:off + 96], "little")
        wss = int.from_bytes(buf[off + 144:off + 152], "little")
        start = nptr - base
        name = buf[start:start + nlen].decode("utf-16-le", errors="replace") if nlen and 0 <= start else ""
        if pid and name:
            age = max(0.0, now - (create / 1e7 - _FILETIME_EPOCH_S)) if create else 0.0
            out.append(Proc(pid, ppid, age, wss / 1048576, name, name))
        if not nxt:
            return out
        off += nxt


def _nt_snapshot_buffer() -> tuple[bytes, int]:
    """The raw SystemProcessInformation buffer and its address; grows on STATUS_INFO_LENGTH_MISMATCH."""
    import ctypes
    nt = ctypes.WinDLL("ntdll")
    nt.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                            ctypes.POINTER(ctypes.c_ulong)]
    nt.NtQuerySystemInformation.restype = ctypes.c_long
    size = 1 << 20
    for _ in range(8):
        buf = ctypes.create_string_buffer(size)
        need = ctypes.c_ulong(0)
        status = nt.NtQuerySystemInformation(5, buf, size, ctypes.byref(need))
        if status == 0:
            return buf.raw, ctypes.addressof(buf)
        if status & 0xFFFFFFFF != 0xC0000004:
            raise OSError(f"NtQuerySystemInformation status {status & 0xFFFFFFFF:#x}")
        size = max(size * 2, need.value + (1 << 16))
    raise OSError("NtQuerySystemInformation buffer kept growing")


def parse_ps(raw: str) -> list[Proc]:
    """Procs from `ps -axo pid=,ppid=,etime=,rss=,command=` output."""
    out = []
    for line in raw.splitlines():
        f = line.split(None, 4)
        if len(f) == 5:
            out.append(Proc(int(f[0]), int(f[1]), _etime_seconds(f[2]), int(f[3]) / 1024, f[4]))
    return out


def _with_cmdlines(procs: list[Proc]) -> list[Proc]:
    """Replace the image-name `cmd` with the real command line for the bounded set of pids that need it."""
    if psutil is None:
        return procs
    out = []
    for p in procs:
        if _exe(p) in _CMDLINE_IMAGES or p.rss_mb >= MIN_RSS_MB:
            try:
                cmd = " ".join(psutil.Process(p.pid).cmdline())
                if cmd:
                    p = Proc(p.pid, p.ppid, p.age_s, p.rss_mb, cmd, p.image)
            except Exception:  # exited, or access denied: the image name stands
                pass
        out.append(p)
    return out


def snapshot_procs() -> list[Proc]:
    """The whole process table in one system call: NtQuerySystemInformation on Windows, one `ps` spawn
    elsewhere. No per-pid psutil read of size, parent or age; falls back to `list_procs` on a fault."""
    try:
        if sys.platform == "win32":
            raw, base = _nt_snapshot_buffer()
            return _with_cmdlines(parse_system_process_information(raw, base, time.time()))
        return parse_ps(subprocess.run(
            ["ps", "-axo", "pid=,ppid=,etime=,rss=,command="], capture_output=True, text=True,
            check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout)
    except Exception:
        return list_procs()


def tree_rss_mb(pids: list[int]) -> float:
    """Summed resident MB of `pids`; a pid that is gone counts 0."""
    total = 0.0
    for pid in pids:
        try:
            total += psutil.Process(pid).memory_info().rss / 1048576
        except Exception:
            pass
    return total


def list_procs() -> list[Proc]:
    if psutil is not None:
        now = time.time()
        out = []
        for pr in psutil.process_iter(["pid", "ppid", "create_time", "memory_info", "cmdline", "name"]):
            info = pr.info
            if info.get("memory_info") is None:
                continue
            out.append(Proc(info["pid"], info["ppid"] or 0, now - (info["create_time"] or now),
                            info["memory_info"].rss / 1048576,
                            " ".join(info["cmdline"] or []) or info.get("name") or "",
                            info.get("name") or ""))
        return out
    return parse_ps(subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,rss=,command="],
                                   capture_output=True, text=True, check=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout)


def shortfall_mb(avail_pct: float) -> float:
    """MB of available memory missing below the `avail_pct` floor; 0 when unreadable or not short."""
    try:
        from coordinator_core.telemetry import host_sampler

        avail, total = host_sampler.avail_mb()
    except Exception:
        return 0.0
    if avail is None or not total:
        return 0.0
    return max(0.0, total * avail_pct / 100 - avail)


def critical(psi_full: float, avail_pct: float) -> bool:
    if sys.platform == "darwin":
        lv = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                            capture_output=True, text=True, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        return lv == "4"
    psi = Path("/proc/pressure/memory")
    if psi.exists():
        for line in psi.read_text().splitlines():
            if line.startswith("full"):
                return float(re.search(r"avg10=([\d.]+)", line).group(1)) >= psi_full
    from coordinator_core.telemetry import host_sampler

    avail, total = host_sampler.avail_mb()
    if avail is not None and total:
        return avail * 100 / total < avail_pct
    raise SystemExit("group-em-memory-governor: no pressure source on this host (available memory unreadable)")


_RUSAGE_INFO_V2 = 2
_RUSAGE_V2_BYTES = 256
_PHYS_FOOTPRINT_OFFSET = 72  # rusage_info_v2: 16-byte uuid, then seven u64 counters, then ri_phys_footprint
_TOP_N = 15


def footprint_mb_from_rusage(buf: bytes) -> float:
    """MB of ri_phys_footprint (resident + compressed + swapped) in a rusage_info_v2 buffer."""
    import struct
    return struct.unpack_from("<Q", buf, _PHYS_FOOTPRINT_OFFSET)[0] / 1048576


def _darwin_footprints(top_n: int = _TOP_N) -> dict[int, float]:
    """Spawn-free: libproc proc_listallpids + proc_pid_rusage, the largest `top_n` by footprint."""
    import ctypes
    # Trap: ctypes.util.find_library spawns /sbin/ldconfig on Python 3.15; the dyld shared cache serves the absolute path.
    lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    count = lib.proc_listallpids(None, 0)
    if count <= 0:
        return {}
    pids = (ctypes.c_int * (count + 64))()
    count = lib.proc_listallpids(pids, ctypes.sizeof(pids))
    buf = ctypes.create_string_buffer(_RUSAGE_V2_BYTES)
    sizes: dict[int, float] = {}
    for i in range(max(count, 0)):
        pid = pids[i]
        if pid > 0 and lib.proc_pid_rusage(pid, _RUSAGE_INFO_V2, buf) == 0:
            sizes[pid] = footprint_mb_from_rusage(buf.raw)
    return dict(sorted(sizes.items(), key=lambda kv: -kv[1])[:top_n])


def footprints() -> dict[int, float]:
    """pid -> MB of resident + compressed + swapped memory, for the largest processes."""
    out: dict[int, float] = {}
    if sys.platform == "darwin":
        try:
            return _darwin_footprints()
        except Exception:  # libproc unavailable: no runaway read this tick
            return out
    if psutil is None:
        return out
    for pr in psutil.process_iter(["pid"]):
        try:
            if sys.platform.startswith("linux"):
                full = pr.memory_full_info()
                out[pr.pid] = (full.uss + full.swap) / 1048576
            else:  # Windows: private commit covers resident and paged-out pages
                out[pr.pid] = getattr(pr.memory_info(), "private", 0) / 1048576
        except Exception:  # exited or access denied
            pass
    return out


def signal_tree(pids: list[int], stop: bool) -> None:
    for pid in pids:
        try:
            if psutil is not None:
                proc = psutil.Process(pid)
                proc.suspend() if stop else proc.resume()
            else:
                os.kill(pid, signal.SIGSTOP if stop else signal.SIGCONT)
        except Exception:  # exited between listing and signalling
            pass


def kill_tree(pids: list[int]) -> None:
    for pid in pids:
        try:
            if psutil is not None:
                psutil.Process(pid).kill()
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception:  # exited between listing and killing
            pass


#: A search tree older than this is reaped whatever its owner is doing.
REAP_AGE_S = 1800.0
_SEARCH_TOOL = re.compile(r"(?:grep|egrep|fgrep|find|xargs|rg)")
_SHELL = re.compile(r"(?:bash|sh)")
_SEARCH_WORD = re.compile(r"(?<![\w.-])(?:grep|egrep|fgrep|find|xargs|rg)(?![\w-])")


_WIN_EXE_HEAD = re.compile(r'\s*(?:"([^"]*)"|([A-Za-z]:[\\/].*?\.exe)(?=\s|$))', re.IGNORECASE)


def _exe(p: Proc) -> str:
    """Lower-cased program name of `p`, without directory or `.exe`. A quoted head or a drive path
    ending `.exe` may contain spaces (a joined psutil cmdline carries no quotes)."""
    cmd = p.cmd if p.cmd.strip() else p.image
    m = _WIN_EXE_HEAD.match(cmd)
    if m:
        head = m.group(1) if m.group(1) is not None else m.group(2)
    else:
        head = cmd.split(None, 1)[0] if cmd.strip() else ""
    name = head.strip('"').replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _is_search_tool(p: Proc) -> bool:
    return bool(_SEARCH_TOOL.fullmatch(_exe(p)))


def _is_search_wrapper(p: Proc) -> bool:
    return bool(_SHELL.fullmatch(_exe(p))) and bool(_SEARCH_WORD.search(p.cmd))


def orphan_trees(procs: list[Proc], guarded: frozenset = frozenset()) -> list[tuple[Proc, str]]:
    """(root, reason) for each reapable search tree.

    A root is a bash/sh wrapper whose command runs grep/find/xargs/rg, or a bare search tool whose
    parent is not such a wrapper; every process in its tree must be a shell or a search tool, so a
    wrapper around a build or test run is never a root. `owner-gone`: the root's parent is absent
    from the snapshot. `age`: older than REAP_AGE_S. A guarded or protected root is skipped.
    """
    by_pid = {p.pid: p for p in procs}
    out: list[tuple[Proc, str]] = []
    for p in procs:
        parent = by_pid.get(p.ppid)
        if _is_search_wrapper(p):
            pass
        elif not _is_search_tool(p) or (parent is not None and _is_search_wrapper(parent)):
            continue
        if p.pid in guarded or PROTECTED_HARD.search(p.cmd):
            continue
        tree = descendants(p.pid, procs)
        if any(t in guarded or not (_is_search_tool(by_pid[t]) or _SHELL.fullmatch(_exe(by_pid[t]))
                                    or _exe(by_pid[t]) == "conhost") for t in tree):
            continue
        if parent is None:
            out.append((p, "owner-gone"))
        elif p.age_s > REAP_AGE_S:
            out.append((p, "age"))
    return out


def reap_orphans(procs: list[Proc], guarded: frozenset, log_path: Path,
                 emit: Callable[[str], None], kill_fn: Callable[[list[int]], None],
                 self_pid: int, rss_fn: Optional[Callable[[list[int]], float]] = None) -> set[int]:
    """Kill each orphaned search tree whole, append one jsonl record per root to `log_path`, and
    return the pids killed. A log that cannot be written never stops the kill."""
    killed: set[int] = set()
    rss = {p.pid: p.rss_mb for p in procs}
    for root, reason in orphan_trees(procs, guarded):
        tree = descendants(root.pid, procs)
        if self_pid in tree:
            continue
        size = rss_fn(tree) if rss_fn is not None else sum(rss.get(t, 0.0) for t in tree)
        kill_fn(tree)
        killed.update(tree)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pid": root.pid,
               "cmd_head": root.cmd[:200], "age_s": round(root.age_s),
               "rss_mb": round(size), "reason": reason}
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError:
            pass
        emit(f"GOVERNOR REAPED pid={root.pid} reason={reason}")
    return killed


_PIDFILE_NAME = "group-em-memory-governor.frozen.json"


def _temp_layout():
    """The engine's `temp_layout` module, or None when the engine is unresolvable.

    The waiter loads this module without the engine on `sys.path`, so a failed import places the
    engine and retries.
    """
    try:
        from coordinator_core import temp_layout  # type: ignore
    except ImportError:
        if not _place_engine_on_path():
            return None
        from coordinator_core import temp_layout  # type: ignore
    return temp_layout


def _managed_dir() -> Path:
    """The fleet-scoped managed Temp dir; the stdlib `cli_shared` mirror when the engine is
    unresolvable, so the governor and the waiter always agree on the directory."""
    layout = _temp_layout()
    if layout is not None:
        return layout.managed_tempdir()
    lib = str(Path(__file__).resolve().parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import cli_shared  # type: ignore
    return Path(cli_shared.managed_temp_root())


def default_pidfile() -> Path:
    """Where the governor records the pids it holds frozen: the fleet-scoped managed Temp dir."""
    return _managed_dir() / _PIDFILE_NAME


def legacy_pidfile() -> Path:
    """The pre-managed-layout pidfile (top level of the OS Temp dir), read so an upgrade over an
    outstanding freeze still thaws what the old governor stopped."""
    layout = _temp_layout()
    if layout is not None:
        return layout.legacy_top_level_path(_PIDFILE_NAME)
    return _managed_dir().parent.parent / _PIDFILE_NAME  # <tmp>/coordinator/_fleet -> <tmp>


START_TIME_TOLERANCE_S = 2.0


def _psutil_start_time(pid: int) -> Optional[float]:
    """In-process start time of `pid` via psutil, None when absent or unreadable."""
    try:
        if not psutil.pid_exists(pid):
            return None
        return float(psutil.Process(pid).create_time())
    except Exception:
        return None


def process_start_time(pid: int) -> Optional[float]:
    """Epoch start time of a live `pid`, or None when it does not exist (or cannot be read)."""
    if psutil is not None:
        return _psutil_start_time(pid)
    try:
        # `etime` ([[dd-]hh:]mm:ss) is the portable spelling; BSD/macOS ps has no `etimes`.
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        if not out:
            return None
        days, _, clock = out.rpartition("-")
        secs = 0
        for part in clock.split(":"):
            secs = secs * 60 + int(part)
        return time.time() - (secs + (int(days) * 86400 if days else 0))
    except Exception:
        return None


def process_start_times(pids: list[int]) -> dict[int, Optional[float]]:
    """Epoch start time per pid in `pids` (None for one that does not exist or cannot be read),
    from at most one `ps` spawn for the whole list."""
    if psutil is not None:
        return {p: _psutil_start_time(p) for p in pids}
    if not pids:
        return {}
    out: dict[int, Optional[float]] = {p: None for p in pids}
    try:
        text = subprocess.run(["ps", "-o", "pid=,etime=", "-p", ",".join(str(p) for p in pids)],
                              capture_output=True, text=True, timeout=5,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        now = time.time()
        for line in text.splitlines():
            pid_text, _, etime = line.strip().partition(" ")
            days, _, clock = etime.strip().rpartition("-")
            secs = 0
            for part in clock.split(":"):
                secs = secs * 60 + int(part)
            out[int(pid_text)] = now - (secs + (int(days) * 86400 if days else 0))
    except Exception:
        pass
    return out


def _declared_writes():
    """Context manager yielding a `declare(path)` callable that records the governor's own file writes
    through the engine's declare-write seam; a no-op pair when the engine is unresolvable (the waiter
    loads this module without it, and the governor must keep running)."""
    import contextlib

    try:
        from coordinator_core.cli_entry import recording_declared_writes  # type: ignore
        from coordinator_core.session.declared_writes import declare_write  # type: ignore
    except ImportError:
        return contextlib.nullcontext(lambda _path: None)

    @contextlib.contextmanager
    def _scope():
        with recording_declared_writes():
            yield declare_write

    return _scope()


def _write_frozen(pidfile: Optional[Path], paused: list[tuple[Proc, list[int]]],
                  start_times_fn: Callable[[list[int]], dict[int, Optional[float]]] = process_start_times) -> None:
    """Persist {governor_pid, governor_start_time, frozen:[{pid, start_time}]}, or remove the file
    when no pid remains frozen."""
    if pidfile is None:
        return
    try:
        pids = [t for _, tree in paused for t in tree]
        with _declared_writes() as declared:
            if pids:
                me = os.getpid()
                times = start_times_fn(pids + [me])
                frozen = [{"pid": p, "start_time": times[p]} for p in pids if times.get(p) is not None]
                pidfile.write_text(json.dumps({"governor_pid": me,
                                               "governor_start_time": times.get(me),
                                               "frozen": frozen}), encoding="utf-8")
            else:
                pidfile.unlink(missing_ok=True)
            declared(pidfile)
    except OSError:  # an unwritable pidfile must not stop the governor
        pass


def _same_process(pid: int, recorded: object,
                  start_time_fn: Callable[[int], Optional[float]]) -> bool:
    if not isinstance(recorded, (int, float)):
        return False
    now = start_time_fn(pid)
    return now is not None and abs(now - float(recorded)) <= START_TIME_TOLERANCE_S


def _thaw_one(pidfile: Optional[Path],
                   signal_fn: Callable[[list[int], bool], None] = signal_tree,
                   start_time_fn: Callable[[int], Optional[float]] = process_start_time) -> list[int]:
    """Resume the pids a DEAD governor recorded in `pidfile`, then clear it.

    A live recorded governor (pid exists
    and start time matches) owns the file: nothing is thawed and the file is kept. With a dead owner
    only recorded pids whose start time still matches are signalled; a reused pid is skipped. A
    missing, legacy or malformed file thaws nothing and is cleared. Returns the pids signalled.
    """
    if pidfile is None:
        return []
    path = Path(pidfile)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        owner = int(raw["governor_pid"])
        owner_start = raw["governor_start_time"]
        entries = [(int(e["pid"]), e["start_time"]) for e in raw["frozen"]]
    except (OSError, ValueError, TypeError, KeyError):
        owner, owner_start, entries = None, None, []
    if owner is not None and _same_process(owner, owner_start, start_time_fn):
        return []
    pids = [p for p, st in entries if _same_process(p, st, start_time_fn)]
    if pids:
        signal_fn(pids, False)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return pids


def thaw_leftovers(pidfile: Optional[Path],
                   signal_fn: Callable[[list[int], bool], None] = signal_tree,
                   start_time_fn: Callable[[int], Optional[float]] = process_start_time) -> list[int]:
    """Thaw `pidfile` (see `_thaw_one`); for the default managed pidfile, also the legacy one.

    The legacy file is what a pre-managed-layout governor wrote, so an upgrade over an outstanding
    freeze still resumes its pids. An injected `pidfile` reads nothing else.
    """
    thawed = _thaw_one(pidfile, signal_fn, start_time_fn)
    if pidfile is not None and Path(pidfile) == default_pidfile():
        thawed += _thaw_one(legacy_pidfile(), signal_fn, start_time_fn)
    return thawed


#: A launcher heartbeats its registration well inside this window; a registration older than it
#: belongs to a launcher that died or hung, so its tree stops being exempt rather than staying
#: immune forever.
GUARD_FRESH_S = 120.0
GUARD_PRUNE_S = 5 * GUARD_FRESH_S
_GUARD_DIR_NAME = "guarded-trees"


def guard_dir() -> Path:
    """Where guarded launchers register: one `<root pid>.json` each."""
    return _managed_dir() / _GUARD_DIR_NAME


def write_guard(pid: int, directory: Optional[Path] = None, now: Optional[float] = None) -> Path:
    """(Re)write the registration for guarded root `pid` with a fresh heartbeat; the launcher calls
    this on start and again inside GUARD_FRESH_S. Raises ValueError when `pid` is not a live process."""
    created = process_start_time(pid)
    if created is None:
        raise ValueError(f"pid {pid} is not a live process")
    target = Path(directory) if directory is not None else guard_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{pid}.json"
    tmp = path.with_name(f"{pid}.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"pid": pid, "create_time": created,
                               "heartbeat": time.time() if now is None else now}), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_guarded(directory: Optional[Path], procs: list[Proc], now: float) -> frozenset:
    """Pids of every tree whose registration is fresh and whose root is still the registered process.

    One directory read per call. A missing, unreadable or malformed registration is skipped; a
    root whose start time differs from the snapshot's (pid reuse) or is not live is skipped.
    """
    if directory is None:
        return frozenset()
    by_pid = {p.pid: p for p in procs}
    out: set[int] = set()
    try:
        entries = list(Path(directory).glob("*.json"))
    except OSError:
        return frozenset()
    for entry in entries:
        try:
            rec = json.loads(entry.read_text(encoding="utf-8"))
            pid = int(rec["pid"])
            created = float(rec["create_time"])
            heartbeat = float(rec["heartbeat"])
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if now - heartbeat > GUARD_PRUNE_S:  # a launcher long dead; do not re-read it every tick
            try:
                entry.unlink()
            except OSError:
                pass
            continue
        root = by_pid.get(pid)
        if root is None or not (0 <= now - heartbeat <= GUARD_FRESH_S):
            continue
        if abs((now - root.age_s) - created) > START_TIME_TOLERANCE_S:
            continue
        out.update(descendants(pid, procs))
    return frozenset(out)


HEADROOM_RISE_GIB = 8.0


def avail_gib() -> Optional[float]:
    """Kernel-available memory in GiB, or None when it cannot be read."""
    try:
        from coordinator_core.telemetry import host_sampler

        avail, _total = host_sampler.avail_mb()
        return None if avail is None else avail / 1024
    except Exception:
        return None


def headroom_line(avail: Optional[float], low: Optional[float], recovered: bool) -> tuple[Optional[str], Optional[float]]:
    """(line or None, new low-water mark). Fires on a rise of HEADROOM_RISE_GIB over the low-water
    mark since the last line, or on `recovered` (calm again after a PAUSED); a fall lowers the mark."""
    if avail is None:
        return None, low
    if low is None:
        return None, avail
    if recovered or avail - low >= HEADROOM_RISE_GIB:
        return f"GOVERNOR HEADROOM available={avail:.1f}", avail
    return None, min(low, avail)


def cache_trim_hint(bin_dir: Path) -> str:
    """The hint line for the elevated cache trim; the unavailable form when the sibling is absent."""
    sibling = Path(bin_dir) / "trim-file-cache.py"
    if not sibling.is_file():
        return "GOVERNOR CACHE-TRIM-HINT unavailable: trim-file-cache.py not beside the governor"
    return f'GOVERNOR CACHE-TRIM-HINT run elevated: python "{sibling.as_posix()}" --apply'


TRIM_COOLDOWN_S = 600.0
CACHE_CAUSE_GIB = 8.0
#: Extraction header reads refill the cache at ~8 GiB/min; a 10-min cooldown starves its guard.
LOW_TRIM_CACHE_GB = 20.0
LOW_TRIM_AVAIL_GIB = 16.0
LOW_TRIM_COOLDOWN_S = 120.0


def append_trim_record(path: Optional[Path], record: dict) -> None:
    """Append one jsonl line for a trim; a write failure never stops the governor."""
    if path is None:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def cache_gib(bin_dir: Path) -> Optional[float]:
    """System file-cache size in GiB (win32 PDH counter, in-process), or None when unreadable."""
    lib = str(Path(bin_dir) / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        from file_cache_win32 import Win32FileCacheHost

        return Win32FileCacheHost().read_memory().cache_bytes / 1024 ** 3
    except Exception:
        return None


def fire_cache_trim(bin_dir: Path) -> Optional[str]:
    """Fire the PM-installed BoxCacheTrim task; the trim.log tail line, or None when the task is
    absent or would not start."""
    lib = str(Path(bin_dir) / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        from file_cache_trim import fire_box_cache_trim
    except ImportError:
        return None
    return fire_box_cache_trim()


def run(args: argparse.Namespace, emit: Callable[[str], None] = print,
        sample: Optional[Callable[[], bool]] = None, procs_fn: Callable[[], list[Proc]] = snapshot_procs,
        signal_fn: Callable[[list[int], bool], None] = signal_tree,
        sleep: Callable[[float], None] = time.sleep, max_ticks: Optional[int] = None,
        footprint_fn: Callable[[], dict[int, float]] = footprints,
        notice_path: Optional[Path] = None,
        notice_fn: Callable[[Optional[Path], list[Proc]], frozenset] = read_noticed_pids,
        guard_path: Optional[Path] = None,
        guard_fn: Callable[[Optional[Path], list[Proc], float], frozenset] = read_guarded,
        reap_path: Optional[Path] = None,
        scan_fn: Callable[[], list[Proc]] = snapshot_procs,
        rss_fn: Optional[Callable[[list[int]], float]] = None,
        kill_fn: Callable[[list[int]], None] = kill_tree,
        bin_dir: Optional[Path] = None, pidfile: Optional[Path] = None,
        start_time_fn: Optional[Callable[[int], Optional[float]]] = None,
        avail_fn: Optional[Callable[[], Optional[float]]] = None,
        retention_fn: Optional[Callable[[], object]] = None,
        scratch_fn: Optional[Callable[[], "dict[str, int]"]] = None,
        trim_fn: Optional[Callable[[], Optional[str]]] = None,
        shortfall_fn: Optional[Callable[[], float]] = None,
        cache_gib_fn: Optional[Callable[[], Optional[float]]] = None,
        trim_log_path: Optional[Path] = None,
        clock: Callable[[], float] = time.monotonic) -> None:
    last_trim: Optional[float] = None
    bin_dir = bin_dir if bin_dir is not None else Path(__file__).resolve().parent
    start_times_fn = process_start_times if start_time_fn is None else (
        lambda pids: {p: start_time_fn(p) for p in pids})
    start_time_fn = start_time_fn or process_start_time
    thaw_leftovers(pidfile, signal_fn, start_time_fn)
    hint_armed = True
    sample = sample or (lambda: critical(args.psi_full, args.avail_pct))
    self_pid = os.getpid()
    paused: list[tuple[Proc, list[int]]] = []
    flagged: set[int] = set()
    scratch_flagged: set[str] = set()
    calm = crit_streak = ticks = 0
    gave_up = False
    low_gib: Optional[float] = None
    pause_recovery = False
    # A governor that exits (session end, SIGTERM) must never leave a peer's command frozen.
    # A hard kill (Windows TerminateProcess, SIGKILL) skips this finally; the pids are in `pidfile`
    # before the freeze signal, and the next governor or waiter start thaws them.
    try:
        while max_ticks is None or ticks < max_ticks:
            ticks += 1
            if ticks % RETENTION_EVERY == 1 % RETENTION_EVERY:
                if retention_fn is not None:
                    try:
                        retention_fn()
                    except Exception:  # housekeeping never stops the governor
                        pass
                if scratch_fn is not None:
                    try:
                        over_sessions = scratch_fn()
                        scratch_flagged &= set(over_sessions)  # re-report a session that falls under then re-offends
                        for sess, nbytes in over_sessions.items():
                            if sess not in scratch_flagged:
                                scratch_flagged.add(sess)
                                emit(f"GOVERNOR SCRATCH-OVER-BUDGET session={sess} "
                                     f"size={nbytes / 1024 ** 3:.1f}GiB")
                    except Exception:  # a report failure never stops the governor
                        pass
            if reap_path is not None and ticks % REAP_EVERY == 1 % REAP_EVERY:
                scan = scan_fn()  # light snapshot: the full one costs seconds of process time
                reap_orphans(scan, guard_fn(guard_path, scan, time.time()), reap_path, emit, kill_fn,
                             self_pid, rss_fn)
            if args.runaway_mb > 0 and ticks % max(args.runaway_every, 1) == 1 % max(args.runaway_every, 1):
                over = {pid: mb for pid, mb in footprint_fn().items()
                        if mb >= args.runaway_mb and pid not in flagged and pid != self_pid}
                if over:
                    cmds = {p.pid: p.cmd for p in procs_fn()}
                    for pid, mb in sorted(over.items(), key=lambda kv: -kv[1]):
                        flagged.add(pid)
                        emit(f"GOVERNOR RUNAWAY pid={pid} footprint={mb:.0f}MB "
                             f"cmd={cmds.get(pid, '?')[:160]}")
            if sample():
                calm = 0
                crit_streak += 1
                fire_trim = hint_armed and sys.platform == "win32"
                hint_armed = False
                # First pause on the first critical sample; each further pause waits two more.
                due = not paused or crit_streak >= 3
                if due and len(paused) < args.max_pauses:
                    procs = procs_fn()
                    guarded = guard_fn(guard_path, procs, time.time())
                    noticed = notice_fn(notice_path, procs)
                    ntree = noticed_tree(noticed, procs)
                    victim = choose_victim(procs, {p.pid for p, _ in paused}, self_pid, noticed, ntree,
                                           shortfall_fn() if shortfall_fn else 0.0, guarded)
                    if victim:
                        prot = protected_pids(procs, ntree, guarded)
                        # A pid with no readable start time cannot be recorded, so it is never frozen:
                        # an unrecorded freeze is one no later thaw can find.
                        tree = [t for t in descendants(victim.pid, procs)
                                if t not in prot and start_time_fn(t) is not None]
                        _write_frozen(pidfile, paused + [(victim, tree)], start_times_fn)
                        signal_fn(tree, True)
                        paused.append((victim, tree))
                        crit_streak = 0
                        pause_recovery = True
                        emit(f"GOVERNOR PAUSED pid={victim.pid} rss={victim.rss_mb:.0f}MB "
                             f"tree={len(tree)} cmd={victim.cmd[:160]}")
                elif due and not gave_up:
                    gave_up = True
                    emit(f"GOVERNOR STILL-CRITICAL after {len(paused)} pause(s); nothing left it may pause")
                if fire_trim and (last_trim is None or clock() - last_trim >= TRIM_COOLDOWN_S):
                    cache = (cache_gib_fn or (lambda: cache_gib(bin_dir)))()
                    fire_trim = cache is None or cache >= CACHE_CAUSE_GIB
                    if fire_trim:
                        last_trim = clock()
                else:
                    fire_trim = False
                if fire_trim:  # after the pause: the fire can block for seconds on schtasks and the log wait
                    try:
                        tail = (trim_fn or (lambda: fire_cache_trim(bin_dir)))()
                    except Exception:  # a trim failure falls back to the hint
                        tail = None
                    emit(cache_trim_hint(bin_dir) if tail is None
                         else f"GOVERNOR CACHE-TRIM fired {tail}".rstrip())
            else:
                crit_streak = 0
                hint_armed = True
                calm += 1
                if paused and calm >= args.resume_after:
                    for victim, tree in reversed(paused):
                        signal_fn(tree, False)
                    emit("GOVERNOR RESUMED " + " ".join(f"pid={v.pid}" for v, _ in reversed(paused)))
                    paused.clear()
                    _write_frozen(pidfile, paused, start_times_fn)
                    gave_up = False
            avail = avail_fn() if avail_fn is not None else None
            # The critical floor (avail_pct) sits far under the 8 GiB heavy-admission floor; between the
            # two a cache-bound box starves admissions while the critical branch above never trims.
            if (avail is not None and avail < LOW_TRIM_AVAIL_GIB and sys.platform == "win32"
                    and (last_trim is None or clock() - last_trim >= LOW_TRIM_COOLDOWN_S)):
                read_cache = cache_gib_fn or (lambda: cache_gib(bin_dir))
                cache = read_cache()
                if cache is not None and cache >= LOW_TRIM_CACHE_GB:
                    t0 = last_trim = clock()
                    emit(f"GOVERNOR LOW available={avail:.1f} cache={cache:.1f}")
                    try:
                        tail = (trim_fn or (lambda: fire_cache_trim(bin_dir)))()
                    except Exception:  # a trim failure falls back to the hint
                        tail = None
                    emit(cache_trim_hint(bin_dir) if tail is None
                         else f"GOVERNOR CACHE-TRIM fired {tail}".rstrip())
                    try:
                        cache_after, avail_after = read_cache(), avail_fn()
                    except Exception:
                        cache_after = avail_after = None
                    append_trim_record(trim_log_path, {
                        "ts": time.time(), "cache_before_gb": cache, "avail_before_gib": avail,
                        "cache_after_gb": cache_after, "avail_after_gib": avail_after,
                        "elapsed_s": clock() - t0,
                        "reason": f"cache>={LOW_TRIM_CACHE_GB:g}GB and avail<{LOW_TRIM_AVAIL_GIB:g}GiB",
                        "fired": tail is not None})
            if avail_fn is not None:
                line, low_gib = headroom_line(avail, low_gib, pause_recovery and not paused)
                if line:
                    pause_recovery = False
                    emit(line)
            sleep(args.interval)
    finally:
        if paused:
            for _, tree in reversed(paused):
                signal_fn(tree, False)
            paused_ids = " ".join(f"pid={v.pid}" for v, _ in reversed(paused))
            paused.clear()
            _write_frozen(pidfile, paused, start_times_fn)
            try:
                emit("GOVERNOR RESUMED-ON-EXIT " + paused_ids)
            except Exception:  # stdout's reader may already be gone
                pass


RETENTION_EVERY = 360
#: The reap scan runs once per this many ticks.
REAP_EVERY = 6


def spawn_retention_if_due() -> bool:
    """Stamp-check the engine's retention run and spawn it detached when due; never raises."""
    try:
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from coordinator_core.ops import retention_run

        return retention_run.spawn_if_due(str(root))
    except Exception:
        return False


def scratch_over_budget() -> "dict[str, int]":
    """Session temp dirs over the per-session scratch budget (report only); never raises."""
    try:
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from coordinator_core.ops import prune_claude_temp

        return prune_claude_temp.over_budget_sessions()
    except Exception:
        return {}


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def open_log_or_exit(path: Path):
    """An append stream on `path`; exit 2 with one stderr line when it cannot be opened."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return open(path, "a", encoding="utf-8", buffering=1)
    except OSError as exc:
        print(f"governor: cannot write --log {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between samples")
    ap.add_argument("--max-pauses", type=int, default=3)
    ap.add_argument("--resume-after", type=int, default=6, help="non-critical samples before resume")
    ap.add_argument("--psi-full", type=float, default=10.0, help="Linux PSI full avg10 threshold")
    ap.add_argument("--avail-pct", type=float, default=5.0, help="fallback available-memory floor")
    ap.add_argument("--runaway-mb", type=float, default=12288.0,
                    help="footprint that flags one process as a runaway; 0 disables")
    ap.add_argument("--runaway-every", type=int, default=6, help="samples between footprint reads")
    ap.add_argument("--log", type=Path, default=None,
                    help="log the detached governor appends to (default <settings home>/scratch/governor.log)")
    ap.add_argument("--reap-log", type=Path, default=None,
                    help="jsonl the governor appends one record per reaped search tree to "
                         "(default governor-reaps.jsonl beside --log)")
    ap.add_argument("--guard", type=int, default=None, metavar="PID",
                    help="register or heartbeat PID as a guarded tree the governor never pauses, then exit")
    args = ap.parse_args(argv)
    if args.guard is not None:
        try:
            print(write_guard(args.guard))
        except (ValueError, OSError) as exc:
            print(f"governor: cannot register guard for pid {args.guard}: {exc}", file=sys.stderr)
            sys.exit(2)
        return
    lib = str(Path(__file__).resolve().parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import session_detach  # type: ignore
    log = args.log or _settings_home() / "scratch" / "governor.log"
    child_argv = list(sys.argv[1:] if argv is None else argv)
    if "--log" not in child_argv:
        child_argv += ["--log", str(log)]
    rc = session_detach.ensure_detached("group-em-memory-governor", child_argv, log)
    if rc is not None:
        sys.exit(rc)
    if args.log is not None:
        # Inline under a launcher, stdout is the launcher's log; a waiter tailing --log would go blind.
        sys.stdout = open_log_or_exit(args.log)
    getattr(sys.stdout, "reconfigure", lambda **_: None)(line_buffering=True)
    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if sig is not None:
            signal.signal(sig, lambda *_: sys.exit(0))
    run(args, notice_path=resolve_notice_path(), guard_path=guard_dir(),
        reap_path=args.reap_log or log.parent / "governor-reaps.jsonl",
        trim_log_path=log.parent / "governor-trims.jsonl", pidfile=default_pidfile(), avail_fn=avail_gib, rss_fn=tree_rss_mb,
        retention_fn=spawn_retention_if_due, scratch_fn=scratch_over_budget,
        shortfall_fn=lambda: shortfall_mb(args.avail_pct))


if __name__ == "__main__":
    main()
