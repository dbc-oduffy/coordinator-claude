"""Shared host layer for the box-memory CLIs.

Stdlib plus optional psutil. Imports cleanly on every OS; Win32 bindings are created lazily
inside the functions that use them. No module-level `coordinator_core` import; available
memory comes from `host_sampler.avail_mb`, imported inside `read_memory_status`.

Family exit codes: 0 ok, 1 operational failure, 2 usage, 3 not elevated, 4 admission HOLD
(`box-memory-snapshot --admit-peak` only), 6 unsupported host.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import types
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3
UNSUPPORTED_HOST_EXIT = 6

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_SET_QUOTA = 0x0100


def unsupported(prog: str, platform: str, reason: str) -> int:
    """Print the one-line unsupported-host message on stderr; return UNSUPPORTED_HOST_EXIT."""
    print(f"{prog}: unsupported host ({platform}): {reason}", file=sys.stderr)
    return UNSUPPORTED_HOST_EXIT


def require_psutil(prog: str) -> int | None:
    """Return None when psutil imports; otherwise print one stderr line and return 1."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        print(f"{prog}: psutil is required (pip install psutil)", file=sys.stderr)
        return 1
    return None


def load_governor(path: Path | None = None) -> types.ModuleType:
    """Load group-em-memory-governor.py by path; the only loader of that file.

    `path` defaults to the governor beside this module's `lib/` directory.
    """
    if path is None:
        path = Path(__file__).resolve().parents[1] / "group-em-memory-governor.py"
    spec = importlib.util.spec_from_file_location("group_em_memory_governor", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load governor from {path}")
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves string annotations through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


@dataclass(frozen=True)
class ProcRow:
    """One process from the system process table; `private_bytes` is PrivatePageCount."""

    pid: int
    ppid: int
    create_time: float
    working_set_bytes: int
    private_bytes: int
    image: str


_SPI_NEXT = struct.Struct("<I")
_SPI_CREATE_TIME = struct.Struct("<q")
_SPI_IMAGE = struct.Struct("<HHxxxxQ")
_SPI_IDS = struct.Struct("<QQ")
_SPI_SIZE = struct.Struct("<Q")
_SPI_OFF_CREATE = 32
_SPI_OFF_IMAGE = 56
_SPI_OFF_PID = 80
_SPI_OFF_WS = 144
_SPI_OFF_PRIVATE = 200
_SPI_MIN_LEN = 208
_FILETIME_EPOCH_DELTA_S = 11644473600


def parse_process_information(buf: bytes, base: int | None = None) -> list[ProcRow]:
    """Parse a 64-bit SYSTEM_PROCESS_INFORMATION chain; pure, no I/O, any OS.

    Walks `NextEntryOffset` until 0. `base` is the buffer's own address: the kernel stores each
    image name as an absolute pointer into the same buffer, so without `base` every `image` is "".
    A truncated or non-advancing chain ends the walk rather than raising.
    """
    rows: list[ProcRow] = []
    size = len(buf)
    off = 0
    while off + _SPI_MIN_LEN <= size:
        (nxt,) = _SPI_NEXT.unpack_from(buf, off)
        (create,) = _SPI_CREATE_TIME.unpack_from(buf, off + _SPI_OFF_CREATE)
        name_len, _max, name_ptr = _SPI_IMAGE.unpack_from(buf, off + _SPI_OFF_IMAGE)
        pid, ppid = _SPI_IDS.unpack_from(buf, off + _SPI_OFF_PID)
        (working_set,) = _SPI_SIZE.unpack_from(buf, off + _SPI_OFF_WS)
        (private,) = _SPI_SIZE.unpack_from(buf, off + _SPI_OFF_PRIVATE)
        image = ""
        if base is not None and name_ptr and name_len:
            start = name_ptr - base
            if 0 <= start and start + name_len <= size:
                image = bytes(buf[start : start + name_len]).decode("utf-16-le", "replace")
        rows.append(
            ProcRow(
                pid=pid,
                ppid=ppid,
                create_time=create / 1e7 - _FILETIME_EPOCH_DELTA_S if create else 0.0,
                working_set_bytes=working_set,
                private_bytes=private,
                image=image,
            )
        )
        if nxt == 0 or off + nxt <= off:
            break
        off += nxt
    return rows


def proc_table() -> list[ProcRow]:
    """Every process via one NtQuerySystemInformation(SystemProcessInformation) read. Windows only.

    Opens no process. Retries with a larger buffer on STATUS_INFO_LENGTH_MISMATCH; raises OSError.
    """
    import ctypes

    if struct.calcsize("P") != 8:
        raise OSError("proc_table requires a 64-bit interpreter")
    nt = ctypes.WinDLL("ntdll")
    nt.NtQuerySystemInformation.restype = ctypes.c_long
    nt.NtQuerySystemInformation.argtypes = [
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    size = 1 << 21
    for _ in range(8):
        buf = ctypes.create_string_buffer(size)
        needed = ctypes.c_ulong(0)
        status = nt.NtQuerySystemInformation(5, buf, size, ctypes.byref(needed))
        if status == 0:
            return parse_process_information(buf.raw, ctypes.addressof(buf))
        if (status & 0xFFFFFFFF) != 0xC0000004:
            raise OSError(f"NtQuerySystemInformation failed: NTSTATUS {status & 0xFFFFFFFF:#x}")
        size = max(size * 2, int(needed.value) + (1 << 16))
    raise OSError("NtQuerySystemInformation: process table kept growing")


def proc_cmdline(pid: int) -> str:
    """Command line of one pid (one open); "" when unreadable or the process is gone."""
    import psutil

    try:
        return " ".join(psutil.Process(pid).cmdline())
    except psutil.Error:
        return ""


@dataclass(frozen=True)
class MemoryStatus:
    """Physical and commit memory, in bytes."""

    avail_phys: int
    total_phys: int
    commit_used: int
    commit_limit: int


def memory_status_darwin(avail_mb_fn=None, vm_fn=None, swap_fn=None) -> MemoryStatus:
    """macOS memory status; raises OSError when available memory is unreadable.

    Available is the kernel figure from `host_sampler.avail_mb` (free + inactive + speculative
    pages). macOS has no commit limit, so commit_limit is physical + current swap capacity and
    commit_used is (physical - available) + swap in use; swap grows on demand, so the limit is a
    floor, not a ceiling. Per-process footprint on macOS is `ri_phys_footprint` (resident +
    compressed + swapped), read by the governor; it exceeds `ps` RSS for a compressed or swapped
    process by design.
    """
    if avail_mb_fn is None:
        from coordinator_core.telemetry import host_sampler

        avail_mb_fn = host_sampler.avail_mb
    if vm_fn is None or swap_fn is None:
        import psutil

        vm_fn = vm_fn or (lambda: psutil.virtual_memory().total)
        swap_fn = swap_fn or (lambda: (lambda s: (s.total, s.used))(psutil.swap_memory()))
    avail_mb, _total_mb = avail_mb_fn()
    if avail_mb is None:
        raise OSError("available physical memory unreadable")
    total = int(vm_fn())
    swap_total, swap_used = swap_fn()
    avail = min(int(avail_mb) * 1048576, total)
    return MemoryStatus(
        avail_phys=avail,
        total_phys=total,
        commit_used=(total - avail) + int(swap_used),
        commit_limit=total + int(swap_total),
    )


def read_memory_status() -> MemoryStatus:
    """Read GlobalMemoryStatusEx (Windows) or the macOS equivalent; raises OSError on failure."""
    if sys.platform == "darwin":
        return memory_status_darwin()
    import ctypes

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_uint32),
            ("dwMemoryLoad", ctypes.c_uint32),
            ("ullTotalPhys", ctypes.c_uint64),
            ("_ull_avail_phys_unread", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    stat = _MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise ctypes.WinError()
    from coordinator_core.telemetry import host_sampler

    avail_mb, _total_mb = host_sampler.avail_mb()
    if avail_mb is None:
        raise OSError("available physical memory unreadable")
    return MemoryStatus(
        avail_phys=int(avail_mb) * 1048576,
        total_phys=int(stat.ullTotalPhys),
        commit_used=int(stat.ullTotalPageFile - stat.ullAvailPageFile),
        commit_limit=int(stat.ullTotalPageFile),
    )


def nonpaged_pool_bytes() -> int:
    """Kernel nonpaged pool size via GetPerformanceInfo. Windows only."""
    import ctypes
    from ctypes import wintypes

    class _PERFORMANCE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("CommitTotal", ctypes.c_size_t),
            ("CommitLimit", ctypes.c_size_t),
            ("CommitPeak", ctypes.c_size_t),
            ("PhysicalTotal", ctypes.c_size_t),
            ("PhysicalAvailable", ctypes.c_size_t),
            ("SystemCache", ctypes.c_size_t),
            ("KernelTotal", ctypes.c_size_t),
            ("KernelPaged", ctypes.c_size_t),
            ("KernelNonpaged", ctypes.c_size_t),
            ("PageSize", ctypes.c_size_t),
            ("HandleCount", wintypes.DWORD),
            ("ProcessCount", wintypes.DWORD),
            ("ThreadCount", wintypes.DWORD),
        ]

    info = _PERFORMANCE_INFORMATION()
    info.cb = ctypes.sizeof(_PERFORMANCE_INFORMATION)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    if not psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(info.KernelNonpaged) * int(info.PageSize)


def empty_working_set(pid: int) -> None:
    """Trim one process's working set. Raises OSError(winerror). Windows only."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_SET_QUOTA, False, pid
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        kernel32.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        if not kernel32.K32EmptyWorkingSet(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)


_ADMISSION_TAIL_BYTES = 1 << 20


def admission_file() -> "Path":
    """Default admission channel: ``<settings-home>/state/group-em/box/admission.jsonl``."""
    import os
    from pathlib import Path

    root = os.environ.get("COORDINATOR_SETTINGS_HOME")
    base = Path(root) if root else Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    return base / "state" / "group-em" / "box" / "admission.jsonl"


def tree_rss_mb(pid: int) -> float:
    """RSS in MB of ``pid`` plus its descendants (psutil)."""
    import psutil

    proc = psutil.Process(pid)
    total = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.Error:
            pass
    return total / (1024 * 1024)


def pid_alive(pid: int) -> bool:
    import psutil

    return psutil.pid_exists(pid)


def reserved_bytes(path, rss_fn=tree_rss_mb, alive_fn=pid_alive) -> int:
    """Sum over live START pids with no matching END of max(0, declared peak - tree RSS), in bytes.

    START and END match on (session_id, run). A START without ``declared_peak_mb``, a dead pid,
    an unreadable file or an unreadable RSS contributes 0. Liveness is pid existence only, so a
    recycled pid of an un-ENDed START over-reserves (fails toward HOLD) until it leaves the tail. Reads only the last 1 MiB of the file.
    """
    import json

    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - _ADMISSION_TAIL_BYTES))
            raw = fh.read()
    except OSError:
        return 0
    starts: dict = {}
    for text in raw.splitlines():
        try:
            line = json.loads(text)
        except ValueError:
            continue
        if not isinstance(line, dict):
            continue
        key = (line.get("session_id"), line.get("run"))
        if line.get("phase") == "END":
            starts.pop(key, None)
        elif line.get("phase") == "START":
            starts[key] = line
    total_mb = 0.0
    for line in starts.values():
        peak = line.get("declared_peak_mb")
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or peak <= 0:
            continue
        for pid in line.get("pids") or []:
            try:
                if not alive_fn(pid):
                    continue
                total_mb += max(0.0, peak - rss_fn(pid))
            except Exception:
                continue
    return int(total_mb * 1024 * 1024)


@dataclass(frozen=True)
class AdmitVerdict:
    """Admission decision with both clauses exposed."""

    admit: bool
    need_avail: float
    avail_ok: bool
    commit_ok: bool


def admit(
    peak: int,
    status: MemoryStatus,
    cushion_pct: float = 25.0,
    cushion_cap: int = 8 * GIB,
    commit_limit: int | None = None,
) -> AdmitVerdict:
    """Pure admission check for a declared peak against a memory snapshot."""
    need_avail = peak + min(peak * cushion_pct / 100, cushion_cap)
    avail_ok = need_avail <= status.avail_phys
    commit_ok = status.commit_used + peak <= (status.commit_limit if commit_limit is None else commit_limit)
    return AdmitVerdict(
        admit=avail_ok and commit_ok,
        need_avail=need_avail,
        avail_ok=avail_ok,
        commit_ok=commit_ok,
    )
