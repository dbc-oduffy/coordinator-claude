"""Pure, OS-free layer of the governor's report-only disk signal.

Types, the saturation streak and the line formatter. OS readers live beside
these and return `disk_sample()`'s shape. Nothing here pauses, kills or blocks.
"""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:  # the full command line then stays unknown
    psutil = None

IDLE_MAX_PCT = 5.0
QUEUE_MIN = 4.0
DISK_TICKS = 2
TOP_N = 3
_MB = 1024 * 1024


@dataclass(frozen=True)
class DiskStat:
    name: str
    idle_pct: float
    queue: float
    pressured: bool = True  # False when the host's PSI io gate says no stall (Linux)


def saturated(stat: DiskStat, idle_max: float = IDLE_MAX_PCT, queue_min: float = QUEUE_MIN) -> bool:
    """True when the disk is near 0% idle AND its queue is high (and PSI, where read, agrees)."""
    return stat.pressured and stat.idle_pct <= idle_max and stat.queue >= queue_min


@dataclass
class DiskEpisode:
    """Flag-once streak: trips after `ticks` consecutive saturated samples, re-arms on recovery."""
    ticks: int = DISK_TICKS
    streak: int = 0
    flagged: bool = field(default=False)

    def observe(self, is_saturated: bool) -> bool:
        """Feed one tick; True exactly on the tick the episode trips."""
        if not is_saturated:
            self.streak = 0
            self.flagged = False
            return False
        self.streak += 1
        if self.flagged or self.streak < self.ticks:
            return False
        self.flagged = True
        return True


def top_by_bytes(prev: dict[int, int], cur: dict[int, int], n: int = TOP_N) -> list[tuple[int, int]]:
    """Rank pids by transferred-bytes delta between two ticks (never op counts).

    A pid absent from `prev` is skipped: its first sample has no baseline.
    """
    deltas = [(pid, b - prev[pid]) for pid, b in cur.items() if pid in prev and b > prev[pid]]
    deltas.sort(key=lambda t: (-t[1], t[0]))
    return deltas[:n]


def _mb(nbytes: int) -> int:
    return nbytes // _MB


def _worst(stats: list[DiskStat], idle_max: float, queue_min: float) -> Optional[DiskStat]:
    hot = [s for s in stats if saturated(s, idle_max, queue_min)]
    if not hot:
        return None
    return min(hot, key=lambda s: (s.idle_pct, -s.queue, s.name))


def format_disk_lines(stats: list[DiskStat], top: list[tuple[int, int]], cmds: dict[int, str],
                      idle_max: float = IDLE_MAX_PCT, queue_min: float = QUEUE_MIN) -> list[str]:
    """DISK line for the box-wide top-IO pid beside the worst saturated disk, then one DISK-STAT per disk.

    `top` is [(pid, bytes_delta)] ranked descending over all disks; the readers carry no per-disk
    pid IO, so the line says the pid is not proven to write that disk. `cmds` maps pid -> command line.
    """
    top_txt = ",".join(f"{pid}:{_mb(b)}MB" for pid, b in top)
    lines: list[str] = []
    worst = _worst(stats, idle_max, queue_min)
    if worst is not None:
        if top:
            pid, nbytes = top[0]
            who = f"pid={pid} io={_mb(nbytes)}MB"
            cmd = cmds.get(pid, "")
        else:
            who, cmd = "pid=none io=0MB", ""
        lines.append(f"GOVERNOR DISK {who} disk={worst.name} idle={worst.idle_pct:.0f}% "
                     f"queue={worst.queue:g} attribution=box-wide-top-io "
                     f"(pid not proven to write this disk) cmd={cmd}")
    for s in stats:
        lines.append(f"GOVERNOR DISK-STAT disk={s.name} idle={s.idle_pct:.0f}% "
                     f"queue={s.queue:g} top={top_txt}")
    return lines


# ---- Windows reader: PDH PhysicalDisk counters + NT-buffer transfer counts, in-process, no spawn ----

_PDH_FMT_DOUBLE = 0x200
_PDH_MORE_DATA = 0x800007D2
_PDH_ITEM_LEN = 24  # PDH_FMT_COUNTERVALUE_ITEM_W x64: name ptr, CStatus + pad, double
_IDLE_PATH = r"\PhysicalDisk(*)\% Idle Time"
_QUEUE_PATH = r"\PhysicalDisk(*)\Current Disk Queue Length"


def parse_pdh_items(buf: bytes, base: int, count: int) -> dict[str, float]:
    """Instance name -> value from a PdhGetFormattedCounterArrayW(PDH_FMT_DOUBLE) buffer.

    `base` is the address the buffer lives at: each name pointer points into it. Items whose
    CStatus is not VALID_DATA/NEW_DATA are dropped, as is the `_Total` aggregate."""
    import struct
    out: dict[str, float] = {}
    for i in range(count):
        ptr, status, value = struct.unpack_from("<QI4xd", buf, i * _PDH_ITEM_LEN)
        start = ptr - base
        if status not in (0, 1) or not 0 <= start < len(buf):
            continue
        name = buf[start:start + 512].decode("utf-16-le", errors="replace").split("\x00", 1)[0]
        if name and name != "_Total":
            out[name] = value
    return out


def build_disk_stats(idle: dict[str, float], queue: dict[str, float]) -> list[DiskStat]:
    """One DiskStat per instance with an idle reading; a missing queue reads 0. Idle is clamped to 0..100."""
    return [DiskStat(name, min(100.0, max(0.0, pct)), queue.get(name, 0.0))
            for name, pct in sorted(idle.items())]


def parse_io_bytes(buf: bytes) -> dict[int, int]:
    """pid -> ReadTransferCount + WriteTransferCount from one SystemProcessInformation x64 buffer.

    Reads only the pid and the two counters of each record: no image name, no age."""
    out: dict[int, int] = {}
    off = 0
    while True:
        nxt = int.from_bytes(buf[off:off + 4], "little")
        pid = int.from_bytes(buf[off + 80:off + 88], "little")
        if pid:
            out[pid] = (int.from_bytes(buf[off + 232:off + 240], "little")
                        + int.from_bytes(buf[off + 240:off + 248], "little"))
        if not nxt:
            return out
        off += nxt


def _nt_process_buffer() -> bytes:
    """The raw SystemProcessInformation buffer; grows on STATUS_INFO_LENGTH_MISMATCH."""
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
            return buf.raw
        if status & 0xFFFFFFFF != 0xC0000004:
            raise OSError(f"NtQuerySystemInformation status {status & 0xFFFFFFFF:#x}")
        size = max(size * 2, need.value + (1 << 16))
    raise OSError("NtQuerySystemInformation buffer kept growing")


class PdhDiskReader:
    """One PDH query with wildcard idle and queue counters, held open across ticks.

    Construction collects once so the first `read()` already spans an interval."""

    def __init__(self) -> None:
        import ctypes
        self._ct = ctypes
        pdh = ctypes.WinDLL("pdh")
        for fn in (pdh.PdhOpenQueryW, pdh.PdhAddEnglishCounterW, pdh.PdhCollectQueryData,
                   pdh.PdhGetFormattedCounterArrayW):
            fn.restype = ctypes.c_ulong
        pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        self._pdh = pdh
        self._query = ctypes.c_void_p()
        self._check(pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)), "PdhOpenQuery")
        self._idle = self._add(_IDLE_PATH)
        self._queue = self._add(_QUEUE_PATH)
        self._check(pdh.PdhCollectQueryData(self._query), "PdhCollectQueryData")

    @staticmethod
    def _check(status: int, what: str) -> None:
        if status & 0xFFFFFFFF != 0:
            raise OSError(f"{what} status {status & 0xFFFFFFFF:#x}")

    def _add(self, path: str):
        handle = self._ct.c_void_p()
        self._check(self._pdh.PdhAddEnglishCounterW(self._query, path, None, self._ct.byref(handle)),
                    "PdhAddEnglishCounter")
        return handle

    def _array(self, handle) -> dict[str, float]:
        ct = self._ct
        size, count = ct.c_ulong(0), ct.c_ulong(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(handle, _PDH_FMT_DOUBLE, ct.byref(size),
                                                        ct.byref(count), None) & 0xFFFFFFFF
        if status != _PDH_MORE_DATA:
            self._check(status, "PdhGetFormattedCounterArray")
            return {}
        buf = ct.create_string_buffer(size.value)
        self._check(self._pdh.PdhGetFormattedCounterArrayW(handle, _PDH_FMT_DOUBLE, ct.byref(size),
                                                           ct.byref(count), buf),
                    "PdhGetFormattedCounterArray")
        return parse_pdh_items(buf.raw, ct.addressof(buf), count.value)

    def read(self) -> list[DiskStat]:
        """Collect once and return every physical disk's idle % and queue length."""
        self._check(self._pdh.PdhCollectQueryData(self._query), "PdhCollectQueryData")
        return build_disk_stats(self._array(self._idle), self._array(self._queue))

    def close(self) -> None:
        """Release the PDH query and its counters; safe to call twice."""
        query, self._query = self._query, None
        if query is not None:
            self._pdh.PdhCloseQuery.argtypes = [self._ct.c_void_p]
            self._pdh.PdhCloseQuery(query)


_reader: Optional[PdhDiskReader] = None


def _windows_sample() -> tuple[list[DiskStat], dict[int, int]]:
    global _reader
    try:
        if _reader is None:
            _reader = PdhDiskReader()
        stats = _reader.read()
    except Exception:
        stale, _reader = _reader, None  # rebuild next tick rather than hold a broken query
        if stale is not None:
            try:
                stale.close()
            except Exception:
                pass
        raise
    return stats, parse_io_bytes(_nt_process_buffer())


# ---- Linux reader: /proc/diskstats, /proc/<pid>/io, PSI io gate; every parser takes text ----

PSI_IO_FULL_MIN = 5.0  # /proc/pressure/io `full avg10` below this holds the trigger off
_WHOLE_DISK = re.compile(r"^(?:sd[a-z]+|hd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)$")


def parse_diskstats(text: str) -> dict[str, tuple[int, int]]:
    """Whole disk name -> (io_ticks ms, in-flight IOs) from /proc/diskstats text.

    Partitions, loop, ram and device-mapper rows are skipped: a partition's counters
    repeat its disk's, so only the whole disk is a saturation signal."""
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 13 or not _WHOLE_DISK.match(parts[2]):
            continue
        try:
            out[parts[2]] = (int(parts[12]), int(parts[11]))
        except ValueError:
            continue
    return out


def diskstats_to_stats(prev: dict[str, tuple[int, int]], cur: dict[str, tuple[int, int]],
                       elapsed_ms: float, pressured: bool = True) -> list[DiskStat]:
    """DiskStat per disk seen on both ticks: idle% = 100 - busy share of the interval (io_ticks delta)."""
    if elapsed_ms <= 0:
        return []
    out = []
    for name in sorted(cur):
        if name not in prev:
            continue
        busy = max(0.0, min(100.0, (cur[name][0] - prev[name][0]) * 100.0 / elapsed_ms))
        out.append(DiskStat(name, 100.0 - busy, float(cur[name][1]), pressured))
    return out


def parse_psi_full_avg10(text: str) -> float:
    """`full avg10` of a /proc/pressure/* text; 0.0 when the line is absent."""
    for line in text.splitlines():
        if line.startswith("full"):
            m = re.search(r"avg10=([\d.]+)", line)
            if m:
                return float(m.group(1))
    return 0.0


def parse_proc_io(text: str) -> int:
    """read_bytes + write_bytes of one /proc/<pid>/io text: bytes that reached the block layer."""
    total = 0
    for line in text.splitlines():
        key, _, val = line.partition(":")
        if key in ("read_bytes", "write_bytes"):
            try:
                total += int(val)
            except ValueError:
                pass
    return total


def proc_io_bytes(proc_root: Path) -> dict[int, int]:
    """pid -> cumulative IO bytes for every readable <proc_root>/<pid>/io; denied or exited pids are skipped."""
    out: dict[int, int] = {}
    try:
        entries = [e for e in os.listdir(proc_root) if e.isdigit()]
    except OSError:
        return out
    for name in entries:
        try:
            out[int(name)] = parse_proc_io((proc_root / name / "io").read_text())
        except OSError:
            continue
    return out


_linux_prev: Optional[tuple[dict[str, tuple[int, int]], float]] = None


def _linux_sample(proc_root: Path = Path("/proc"), now=time.monotonic):
    """(stats, pid bytes); stats is empty on the first call, which only sets the io_ticks baseline."""
    global _linux_prev
    cur = parse_diskstats((proc_root / "diskstats").read_text())
    t = now()
    try:
        pressured = parse_psi_full_avg10((proc_root / "pressure" / "io").read_text()) >= PSI_IO_FULL_MIN
    except OSError:
        pressured = True  # no PSI on this kernel: the idle/queue test stands alone
    prev, _linux_prev = _linux_prev, (cur, t)
    stats = diskstats_to_stats(prev[0], cur, (t - prev[1]) * 1000.0, pressured) if prev else []
    return stats, proc_io_bytes(proc_root)


def disk_sample() -> Optional[tuple[list[DiskStat], dict[int, int]]]:
    """(per-disk stats, pid -> cumulative IO bytes) now; None on a host with no reader (macOS).

    Raises on a reader fault; the caller treats that as no sample for the tick."""
    if sys.platform == "win32":
        return _windows_sample()
    if sys.platform.startswith("linux"):
        return _linux_sample()
    return None


def cmdline_of(pid: int) -> str:
    """Full, untruncated command line of one pid; "" when it exited, is denied, or psutil is absent."""
    if psutil is None:
        return ""
    try:
        return " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return ""
