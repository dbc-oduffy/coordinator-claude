"""group-em-memory-governor — pause the command that pushed the box into critical memory pressure.

Runs as the Group EM's session-long `run_in_background` shell, `python -u` appending to a log;
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

On win32 only, the first critical sample of an episode also prints one GOVERNOR CACHE-TRIM-HINT line
naming the elevated `trim-file-cache.py --apply` command; a calm verdict re-arms it.

NEGATIVE SPEC: suspends and resumes only; never runs a cache trim; never kills, never signals a protected process; reads the
box admission channel but never writes outside stdout. A suspended process it can no longer find
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
    r"|deploy-from-snapshot|deploy:"
    r"|scratch/deploy-|group-em-memory-governor|(?:^|[/\\])conhost(?:\.exe)?(?:\s|$)"
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


def is_protected(p: Proc, noticed_tree: frozenset = frozenset()) -> bool:
    """Harness, language-server, deploy and self are always protected; project-rag is protected
    unless the process belongs to a launch noticed on the admission channel."""
    if PROTECTED_HARD.search(p.cmd):
        return True
    return bool(PROJECT_RAG.search(p.cmd)) and p.pid not in noticed_tree


def is_candidate(p: Proc, self_pid: int, noticed: frozenset = frozenset(),
                 noticed_tree: frozenset = frozenset()) -> bool:
    if p.pid == self_pid or is_protected(p, noticed_tree):
        return False
    return p.pid in noticed or (p.rss_mb >= MIN_RSS_MB and bool(HEAVY.search(p.cmd)))


def choose_victim(procs: list[Proc], paused: set[int], self_pid: int,
                  noticed: frozenset = frozenset(), tree: frozenset = frozenset()) -> Optional[Proc]:
    """Youngest heavy-or-noticed, unprotected, not-yet-paused command: the likeliest cause of the spike.

    A worker whose parent is itself a candidate is never chosen alone; its parent's tree covers it.
    """
    heavy = {p.pid for p in procs if is_candidate(p, self_pid, noticed, tree)}
    rss = {p.pid: p.rss_mb for p in procs}
    pool = [p for p in procs if p.pid in heavy and p.pid not in paused and p.ppid not in heavy
            and sum(rss.get(t, 0.0) for t in descendants(p.pid, procs)) >= MIN_RSS_MB]
    return min(pool, key=lambda p: p.age_s) if pool else None


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


def protected_pids(procs: list[Proc], noticed_tree: frozenset = frozenset()) -> set[int]:
    return {p.pid for p in procs if is_protected(p, noticed_tree)}


def _etime_seconds(etime: str) -> float:
    days, _, rest = etime.rpartition("-")
    parts = [int(x) for x in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return (int(days) if days else 0) * 86400 + h * 3600 + m * 60 + s


def list_procs() -> list[Proc]:
    if psutil is not None:
        now = time.time()
        out = []
        for pr in psutil.process_iter(["pid", "ppid", "create_time", "memory_info", "cmdline"]):
            info = pr.info
            if info.get("memory_info") is None:
                continue
            out.append(Proc(info["pid"], info["ppid"] or 0, now - (info["create_time"] or now),
                            info["memory_info"].rss / 1048576, " ".join(info["cmdline"] or [])))
        return out
    raw = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,rss=,command="],
                         capture_output=True, text=True, check=False,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    out = []
    for line in raw.splitlines():
        f = line.split(None, 4)
        if len(f) == 5:
            out.append(Proc(int(f[0]), int(f[1]), _etime_seconds(f[2]), int(f[3]) / 1024, f[4]))
    return out


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


def _write_frozen(pidfile: Optional[Path], paused: list[tuple[Proc, list[int]]],
                  start_times_fn: Callable[[list[int]], dict[int, Optional[float]]] = process_start_times) -> None:
    """Persist {governor_pid, governor_start_time, frozen:[{pid, start_time}]}, or remove the file
    when no pid remains frozen."""
    if pidfile is None:
        return
    try:
        pids = [t for _, tree in paused for t in tree]
        if pids:
            me = os.getpid()
            times = start_times_fn(pids + [me])
            frozen = [{"pid": p, "start_time": times[p]} for p in pids if times.get(p) is not None]
            pidfile.write_text(json.dumps({"governor_pid": me,
                                           "governor_start_time": times.get(me),
                                           "frozen": frozen}), encoding="utf-8")
        else:
            pidfile.unlink(missing_ok=True)
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


def cache_trim_hint(bin_dir: Path) -> str:
    """The hint line for the elevated cache trim; the unavailable form when the sibling is absent."""
    sibling = Path(bin_dir) / "trim-file-cache.py"
    if not sibling.is_file():
        return "GOVERNOR CACHE-TRIM-HINT unavailable: trim-file-cache.py not beside the governor"
    return f'GOVERNOR CACHE-TRIM-HINT run elevated: python "{sibling.as_posix()}" --apply'


def run(args: argparse.Namespace, emit: Callable[[str], None] = print,
        sample: Optional[Callable[[], bool]] = None, procs_fn: Callable[[], list[Proc]] = list_procs,
        signal_fn: Callable[[list[int], bool], None] = signal_tree,
        sleep: Callable[[float], None] = time.sleep, max_ticks: Optional[int] = None,
        footprint_fn: Callable[[], dict[int, float]] = footprints,
        notice_path: Optional[Path] = None,
        notice_fn: Callable[[Optional[Path], list[Proc]], frozenset] = read_noticed_pids,
        bin_dir: Optional[Path] = None, pidfile: Optional[Path] = None,
        start_time_fn: Optional[Callable[[int], Optional[float]]] = None) -> None:
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
    calm = crit_streak = ticks = 0
    gave_up = False
    # A governor that exits (session end, SIGTERM) must never leave a peer's command frozen.
    # A hard kill (Windows TerminateProcess, SIGKILL) skips this finally; the pids are in `pidfile`
    # before the freeze signal, and the next governor or waiter start thaws them.
    try:
        while max_ticks is None or ticks < max_ticks:
            ticks += 1
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
                if hint_armed and sys.platform == "win32":
                    emit(cache_trim_hint(bin_dir))
                hint_armed = False
                # First pause on the first critical sample; each further pause waits two more.
                due = not paused or crit_streak >= 3
                if due and len(paused) < args.max_pauses:
                    procs = procs_fn()
                    noticed = notice_fn(notice_path, procs)
                    ntree = noticed_tree(noticed, procs)
                    victim = choose_victim(procs, {p.pid for p, _ in paused}, self_pid, noticed, ntree)
                    if victim:
                        prot = protected_pids(procs, ntree)
                        # A pid with no readable start time cannot be recorded, so it is never frozen:
                        # an unrecorded freeze is one no later thaw can find.
                        tree = [t for t in descendants(victim.pid, procs)
                                if t not in prot and start_time_fn(t) is not None]
                        _write_frozen(pidfile, paused + [(victim, tree)], start_times_fn)
                        signal_fn(tree, True)
                        paused.append((victim, tree))
                        crit_streak = 0
                        emit(f"GOVERNOR PAUSED pid={victim.pid} rss={victim.rss_mb:.0f}MB "
                             f"tree={len(tree)} cmd={victim.cmd[:160]}")
                elif due and not gave_up:
                    gave_up = True
                    emit(f"GOVERNOR STILL-CRITICAL after {len(paused)} pause(s); nothing left it may pause")
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
    args = ap.parse_args(argv)
    getattr(sys.stdout, "reconfigure", lambda **_: None)(line_buffering=True)
    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
        if sig is not None:
            signal.signal(sig, lambda *_: sys.exit(0))
    run(args, notice_path=resolve_notice_path(), pidfile=default_pidfile())


if __name__ == "__main__":
    main()
