"""Shared host layer for the box-memory CLIs.

Stdlib plus optional psutil. Imports cleanly on every OS; Win32 bindings are created lazily
inside the functions that use them. No module-level `coordinator_core` import; available
memory comes from `host_sampler.avail_mb`, imported inside `read_memory_status`.

Family exit codes: 0 ok, 1 operational failure, 2 usage, 3 not elevated, 4 admission HOLD
(`box-memory-snapshot --admit-peak` only), 5 cannot leave the Claude Code session's job
(`session_detach.ensure_detached` refusal), 6 unsupported host.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import re
import struct
import sys
import types
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3
CANNOT_DETACH_EXIT = 5
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
    except (psutil.Error, OSError):
        return ""


@dataclass(frozen=True)
class MemoryStatus:
    """Physical and commit memory, in bytes."""

    avail_phys: int
    total_phys: int
    commit_used: int
    commit_limit: int


def _host_sampler(repo_root: Path | None = None) -> types.ModuleType:
    """Import `coordinator_core.telemetry.host_sampler` (see `_engine_module`)."""
    return _engine_module("coordinator_core.telemetry.host_sampler", repo_root)


def _engine_module(name: str, repo_root: Path | None = None) -> types.ModuleType:
    """Import the engine module ``name``, falling back to this checkout's root.

    A bare system interpreter has no installed coordinator_core; the checkout root (resolved from
    this file) is tried before giving up. An ambient coordinator_core lacking the module stays
    cached in `sys.modules` after the first miss and shadows the checkout, so the miss evicts it
    before the retry (restored if the retry fails too). Raises OSError naming the missing module.
    """
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pass
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    evicted: dict[str, types.ModuleType] = {}
    if (root / "coordinator_core").is_dir():
        for mod in [m for m in sys.modules if m == "coordinator_core" or m.startswith("coordinator_core.")]:
            evicted[mod] = sys.modules.pop(mod)
    importlib.invalidate_caches()
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        for mod in [m for m in sys.modules if m == "coordinator_core" or m.startswith("coordinator_core.")]:
            del sys.modules[mod]
        sys.modules.update(evicted)
        raise OSError(f"cannot import {name} (missing module {exc.name!r}; looked in {root})") from exc


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
        avail_mb_fn = _host_sampler().avail_mb
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


def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo as {field: bytes}; every field is kB there, a line without a numeric value is skipped."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[key.strip()] = int(parts[0]) * 1024
    return out


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def memory_status_linux(meminfo_text: str | None = None) -> MemoryStatus:
    """Linux memory status from /proc/meminfo; raises OSError when MemTotal or MemAvailable is unreadable.

    Same shape as `memory_status_darwin`: available is the kernel's MemAvailable (capped at MemTotal),
    commit_limit is physical + swap capacity, commit_used is (physical - available) + swap in use.
    """
    info = parse_meminfo(_read_text("/proc/meminfo") if meminfo_text is None else meminfo_text)
    if "MemTotal" not in info or "MemAvailable" not in info:
        raise OSError("MemTotal or MemAvailable missing from /proc/meminfo")
    total = info["MemTotal"]
    avail = min(info["MemAvailable"], total)
    swap_total = info.get("SwapTotal", 0)
    swap_used = max(0, swap_total - info.get("SwapFree", 0))
    return MemoryStatus(
        avail_phys=avail,
        total_phys=total,
        commit_used=(total - avail) + swap_used,
        commit_limit=total + swap_total,
    )


def linux_cached_bytes(meminfo_text: str | None = None) -> int | None:
    """`Cached` of /proc/meminfo in bytes; None when absent."""
    return parse_meminfo(_read_text("/proc/meminfo") if meminfo_text is None else meminfo_text).get("Cached")


def read_psi_memory(psi_text: str | None = None) -> dict[str, float] | None:
    """Memory pressure from /proc/pressure/memory: {"some_avg10": .., "full_avg10": ..}; None when unreadable.

    Linux has no macOS `memory_pressure`; PSI is its pressure signal."""
    try:
        text = _read_text("/proc/pressure/memory") if psi_text is None else psi_text
    except OSError:
        return None
    out: dict[str, float] = {}
    for line in text.splitlines():
        kind, _, rest = line.partition(" ")
        for field in rest.split():
            name, _, value = field.partition("=")
            if kind in ("some", "full") and name == "avg10":
                try:
                    out[f"{kind}_avg10"] = float(value)
                except ValueError:
                    pass
    return out or None


def read_memory_status() -> MemoryStatus:
    """Read GlobalMemoryStatusEx (Windows), /proc/meminfo (Linux) or the macOS equivalent; raises OSError on failure."""
    if sys.platform == "darwin":
        return memory_status_darwin()
    if sys.platform.startswith("linux"):
        return memory_status_linux()
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
    avail_mb, _total_mb = _host_sampler().avail_mb()
    if avail_mb is None:
        raise OSError("available physical memory unreadable")
    return MemoryStatus(
        avail_phys=int(avail_mb) * 1048576,
        total_phys=int(stat.ullTotalPhys),
        commit_used=int(stat.ullTotalPageFile - stat.ullAvailPageFile),
        commit_limit=int(stat.ullTotalPageFile),
    )


def _group_em_live() -> bool:
    """True when a live box-wide group-em holder exists; any failure reads as not live."""
    try:
        _host_sampler()  # puts this checkout's root on sys.path when coordinator_core is not installed
        from coordinator_core.group_em import gem_home

        return gem_home.gem_holder() is not None
    except Exception:
        return False


def trim_file_cache() -> str | None:
    """Fire the PM-installed BoxCacheTrim task once (Windows only), gated on a live group-em as the
    governor's trims are; this run's result line, or None when nothing was fired. Bounded by
    `file_cache_trim.GOVERNOR_WAIT_SECONDS`. Callers fire it only on a breach, never per admit."""
    if sys.platform != "win32":
        return None
    lib = str(Path(__file__).resolve().parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        from file_cache_trim import fire_box_cache_trim
    except ImportError:
        return None
    return fire_box_cache_trim(live_fn=_group_em_live)


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
    """Trim one process's working set; a no-op when the handle is denied or the trim fails. Windows only."""
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
        return
    try:
        kernel32.K32EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        kernel32.K32EmptyWorkingSet(handle)
    finally:
        kernel32.CloseHandle(handle)


_ADMISSION_TAIL_BYTES = 1 << 20


def admission_file() -> Path:
    """Default admission channel: ``<settings-home>/state/group-em/box/admission.jsonl``."""
    import os

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


_CREATE_TIME_TOLERANCE_S = 1.0


def pid_create_time(pid: int) -> float | None:
    """Process create_time (epoch seconds) of ``pid``, or None when unreadable or gone."""
    import psutil

    try:
        return float(psutil.Process(pid).create_time())
    except Exception:
        return None


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


_UNSTAMPED_MAX_AGE_S = 6 * 3600.0


def pid_image(pid: int) -> str | None:
    """Executable name of ``pid`` (lower-case), or None when unreadable or gone."""
    import psutil

    try:
        return str(psutil.Process(pid).name()).lower()
    except Exception:
        return None


def _image_is_declared_command(image: str | None, line: dict) -> bool:
    """True when ``image`` is a python-family interpreter or contains the run key's command token."""
    if not image:
        return False
    stem = image.rsplit(".", 1)[0] if image.endswith(".exe") else image
    if stem.startswith(("python", "py")):
        return True
    token = str(line.get("run") or "").split(":", 1)[0].split("-", 1)[0]
    return bool(token) and token in stem


def _pid_holds(line: dict, pid, alive_fn, create_time_fn, image_fn=None, now_fn=None) -> bool:
    """True while ``pid`` is still the process the START ``line`` was written for.

    Dead pid: no. Stamped ``create_time``: the live create_time must match it. Unstamped line
    (no ``create_time``): needs a ``ts`` no older than ``_UNSTAMPED_MAX_AGE_S`` (no ``ts`` never
    holds), a live create_time not later than ``ts`` (a later one is a recycled pid) and, when
    ``image_fn`` is given, a process image that is the declared command.
    """
    if not alive_fn(pid):
        return False
    stamped, ts = _num(line.get("create_time")), _num(line.get("ts"))
    current = create_time_fn(pid)
    if stamped is not None:
        return current is not None and abs(current - stamped) <= _CREATE_TIME_TOLERANCE_S
    if ts is None:
        return False
    if now_fn is not None and now_fn() - ts > _UNSTAMPED_MAX_AGE_S:
        return False
    if current is not None and current > ts + _CREATE_TIME_TOLERANCE_S:
        return False
    return image_fn is None or _image_is_declared_command(image_fn(pid), line)


def _safe_holds(line, pid, alive_fn, create_time_fn, image_fn=None, now_fn=None) -> bool:
    try:
        return _pid_holds(line, pid, alive_fn, create_time_fn, image_fn, now_fn)
    except Exception:
        return False


_SLOT_GRANT_KIND = "group-em-slot-grant"
_SLOT_GRANT_TTL_CEILING_S = 240 * 60


def slot_grants_dir(admission_path) -> Path:
    """Slot-grant store, a sibling of the ``box/`` channel dir: ``<group-em>/slot-grants``."""
    return Path(admission_path).parent.parent / "slot-grants"


def _iso_epoch(value) -> float | None:
    from datetime import datetime, timezone

    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _grant_holdings(grants_dir, covered: set, now: float) -> list[dict]:
    """One entry per unexpired slot grant whose (grantee, run) has no START or END in the ledger.

    Pure file reads (one listing per issuer, one read per grant), no spawn. The issuer's
    holder-liveness is not checked, so a grant counts until it expires, is revoked, or its job
    writes an END. The full declared peak counts: a grant names no pid to take an RSS from.
    """
    import json

    out = []
    try:
        files = list(Path(grants_dir).glob("*/*.json"))
    except OSError:
        return out
    for file in files:
        try:
            rec = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or rec.get("kind") != _SLOT_GRANT_KIND:
            continue
        issued, expires = _iso_epoch(rec.get("issued_at")), _iso_epoch(rec.get("expires_at"))
        peak = rec.get("declared_peak_mb")
        if issued is None or expires is None or isinstance(peak, bool) or not isinstance(peak, (int, float)):
            continue
        if peak <= 0 or not issued <= now < expires or expires - issued > _SLOT_GRANT_TTL_CEILING_S:
            continue
        key = (rec.get("grantee_session_id"), rec.get("run"))
        if key in covered:
            continue
        out.append({
            "session_id": key[0], "run": key[1], "pid": None, "image": None,
            "grant_issuer_session_id": file.parent.name,
            "bytes": int(peak * 1024 * 1024),
        })
    return out


def _ledger_starts(path) -> tuple[dict, set]:
    """Last START per (session, run), closed by END; read only the bounded ledger tail."""
    import json

    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - _ADMISSION_TAIL_BYTES))
            raw = fh.read()
    except OSError:
        raw = b""
    starts: dict = {}
    covered: set = set()
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
            covered.add(key)
        elif line.get("phase") == "START":
            starts[key] = line
            covered.add(key)
    return starts, covered


def _verified_pool_line(line, alive_fn, create_time_fn, image_fn, now_fn) -> bool:
    """Selected pools need an explicit reliable birth stamp, not only a surviving PID."""
    import math

    stamp = _num(line.get("create_time"))
    pids = line.get("pids")
    return (stamp is not None and math.isfinite(stamp) and stamp > 0 and isinstance(pids, list)
            and len(pids) == 1 and _safe_holds(line, pids[0], alive_fn, create_time_fn, image_fn, now_fn))


def _holdings(path, rss_fn, alive_fn, create_time_fn, image_fn, now_fn) -> list[dict]:
    """Live process/grant holdings; valid linked allocations share their active parent's pool."""
    starts, covered = _ledger_starts(path)
    # Pool links are allocation accounting within one registered budget. Without
    # a live birth-verified parent or with malformed/oversized allocations, keep
    # the old additive reservation instead (strict failure direction).
    pooled = set()
    by_pool = {}
    for key, line in starts.items():
        pool = (line.get("pool_session_id"), line.get("pool_run"))
        if all(isinstance(value, str) and value for value in pool):
            by_pool.setdefault(pool, []).append((key, line))
    for parent_key, parent in starts.items():
        if parent_key not in by_pool:
            continue
        if parent.get("pool_session_id") or parent.get("pool_run"):
            continue  # Nested/cyclic pool declarations remain additively reserved.
        if not _verified_pool_line(parent, alive_fn, create_time_fn, image_fn, now_fn):
            continue
        peak = _num(parent.get("declared_peak_mb"))
        if peak is None or not 0 < peak <= 1048576:
            continue
        children = [(key, line) for key, line in by_pool.get(parent_key, []) if key != parent_key
                    and _verified_pool_line(line, alive_fn, create_time_fn, image_fn, now_fn)]
        allocations = [_num(line.get("declared_peak_mb")) for _, line in children]
        if all(value is not None and 0 < value <= peak for value in allocations) and sum(allocations) <= peak:
            pooled.update(key for key, _ in children)
    out = _grant_holdings(slot_grants_dir(path), covered, now_fn())
    for key, line in starts.items():
        if key in pooled:
            continue
        peak = line.get("declared_peak_mb")
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or peak <= 0:
            continue
        for pid in line.get("pids") or []:
            if not _safe_holds(line, pid, alive_fn, create_time_fn, image_fn, now_fn):
                continue
            try:
                held = max(0.0, peak - rss_fn(pid))
            except Exception:
                continue
            try:
                image = image_fn(pid) if image_fn else None
            except Exception:
                image = None
            out.append({
                "session_id": line.get("session_id"), "run": line.get("run"), "pid": pid,
                "image": image, "bytes": int(held * 1024 * 1024),
            })
    return out


def reserved_bytes(
    path, rss_fn=tree_rss_mb, alive_fn=pid_alive, create_time_fn=pid_create_time,
    image_fn=pid_image, now_fn=None,
) -> int:
    """Sum over holding START pids with no matching END of max(0, declared peak - tree RSS), in bytes.

    Plus the full declared peak of each unexpired slot grant (``slot_grants_dir``) whose
    (grantee session, run) has no START or END row.
    START and END match on (session_id, run). A START without ``declared_peak_mb``, a pid that
    does not hold (see ``_pid_holds``: dead, recycled, unstamped and stale or without ``ts``, or
    an image that is not the declared command), an unreadable file or an unreadable RSS
    contributes 0. Reads only the last 1 MiB of the file.
    """
    import time

    rows = _holdings(path, rss_fn, alive_fn, create_time_fn, image_fn, now_fn or time.time)
    return sum(r["bytes"] for r in rows)


CONTROL_PLANE_CORE_RESERVE = 2
_CORE_RESERVE_ENV = "COORDINATOR_ADMISSION_CORE_RESERVE"


def _line_cores(line: dict) -> int:
    """Declared cores of a START row; a missing, non-integer or sub-1 value counts as 1."""
    value = line.get("declared_cores")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else 1


def _agent_identity(key) -> str | None:
    """The ``<backend>-workflow-<16 hex>`` run of a workflow agent's supervisor or child row, else None."""
    run = key[1] if isinstance(key, tuple) and len(key) == 2 else None
    match = re.fullmatch(r"([a-z]+-workflow-[0-9a-f]{16})(?::\d+)?", run) if isinstance(run, str) else None
    return match.group(1) if match else None


def physical_cores() -> int:
    """Physical core count (psutil), falling back to the logical count, then 1."""
    try:
        import psutil

        cores = psutil.cpu_count(logical=False)
        if cores:
            return int(cores)
    except ImportError:
        pass
    import os

    return os.cpu_count() or 1


def default_cpu_budget() -> int:
    """Box CPU budget in cores: physical cores minus the control-plane reserve, at least 1.

    The reserve is ``CONTROL_PLANE_CORE_RESERVE`` unless ``COORDINATOR_ADMISSION_CORE_RESERVE``
    holds a non-negative integer.
    """
    import os

    raw = os.environ.get(_CORE_RESERVE_ENV, "")
    reserve = int(raw) if raw.isascii() and raw.isdigit() else CONTROL_PLANE_CORE_RESERVE
    return max(1, physical_cores() - reserve)


def reserved_cores(
    path, alive_fn=pid_alive, create_time_fn=pid_create_time, image_fn=pid_image, now_fn=None,
    *, exclude_key=None, exclude_pid=None,
) -> int:
    """Sum of declared cores (absent = 1) over START rows with no END that still hold a pid.

    A row counts on the same terms as ``reserved_bytes`` (positive ``declared_peak_mb``, a holding
    pid); one row counts once however many pids it names. One workflow leg is one reservation, so
    two rows never charge it twice: a driver shadow row (``box-memory-snapshot`` / ``<run>:<pid>``)
    is dropped once the leg's own row (``<run>``) is live, and rows held by the same pid set count
    once at their widest. ``exclude_key`` is a (session_id, run) to leave out, for a caller
    re-checking its own row; ``exclude_pid`` leaves out every row held by that pid, for a stage
    admitting under its driver's reservation. Slot grants name no cores and count 0.

    A workflow agent holds two rows, the supervisor's ``<run>:<pid>`` and the child's ``<run>``
    (``_agent_identity``); together they count the larger of their declared cores once.
    """
    import time

    now_fn = now_fn or time.time
    starts, _ = _ledger_starts(path)
    skip = _agent_identity(exclude_key) if exclude_key else None
    live: dict = {}
    for key, line in starts.items():
        unit = _agent_identity(key) or key
        if key == exclude_key or (skip is not None and unit == skip):
            continue
        peak = line.get("declared_peak_mb")
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or peak <= 0:
            continue
        held = frozenset(pid for pid in line.get("pids") or [] if _safe_holds(line, pid, alive_fn, create_time_fn, image_fn, now_fn))
        if held and not (exclude_pid is not None and exclude_pid in held):
            live[key] = (held, _line_cores(line), unit)
    runs = {run for _, run in live}
    by_unit: dict = {}
    for (session, run), (held, cores, unit) in live.items():
        base, sep, _tail = str(run).rpartition(":")
        if session == "box-memory-snapshot" and sep and base in runs and unit == (session, run):  # a workflow agent folds by unit instead
            continue
        prev = by_unit.get(unit)
        by_unit[unit] = (held | prev[0] if prev else held, max(prev[1] if prev else 0, cores))
    by_pids: dict = {}
    for held, cores in by_unit.values():
        by_pids[held] = max(by_pids.get(held, 0), cores)
    return sum(by_pids.values())


def top_holders(
    path, limit: int = 5, rss_fn=tree_rss_mb, alive_fn=pid_alive, create_time_fn=pid_create_time,
    image_fn=pid_image, now_fn=None,
) -> list[dict]:
    """The ``limit`` largest holdings counted by ``reserved_bytes``, as dicts of session_id, run, pid, image, bytes."""
    import time

    rows = _holdings(path, rss_fn, alive_fn, create_time_fn, image_fn, now_fn or time.time)
    return sorted(rows, key=lambda r: r["bytes"], reverse=True)[:limit]


def compact_admission(
    path, alive_fn=pid_alive, create_time_fn=pid_create_time, *, locked: bool = False,
    image_fn=pid_image, now_fn=None,
) -> int:
    """Rewrite the ledger under ``admission_lock`` without dead or recycled STARTs; returns rows removed.

    ``locked=True`` means the caller already holds ``admission_lock`` (the lock is not reentrant).

    Drops each START whose pids no longer hold, each START/END pair already closed, and the ENDs of
    dropped STARTs. A kept legacy START with one pid and no ``create_time`` gets that pid's live
    create_time stamped. Unparseable lines and other rows are kept verbatim. A failed read or
    replace leaves the file untouched.
    """
    import json
    import os
    import time

    now_fn = now_fn or time.time
    path = Path(path)
    with contextlib.nullcontext() if locked else admission_lock(path):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return 0
        parsed = []
        final: dict = {}
        for index, text in enumerate(lines):
            try:
                row = json.loads(text)
            except ValueError:
                row = None
            parsed.append(row)
            if isinstance(row, dict) and row.get("phase") in ("START", "END"):
                final[(row.get("session_id"), row.get("run"))] = (row["phase"], index)
        drop: set = set()
        stamped = False
        for index, row in enumerate(parsed):
            if not isinstance(row, dict) or row.get("phase") not in ("START", "END"):
                continue
            phase, last = final[(row.get("session_id"), row.get("run"))]
            if phase == "END" or index != last:
                drop.add(index)
                continue
            pids = row.get("pids") or []
            if not any(_safe_holds(row, pid, alive_fn, create_time_fn, image_fn, now_fn) for pid in pids):
                drop.add(index)
            elif len(pids) == 1 and _num(row.get("create_time")) is None:
                stamp = create_time_fn(pids[0])
                if stamp is not None:
                    row["create_time"] = stamp
                    lines[index] = json.dumps(row)
                    stamped = True
        if not drop and not stamped:
            return 0
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text("".join(f"{t}\n" for i, t in enumerate(lines) if i not in drop), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return 0
    return len(drop)


def peaks_file(admission_path) -> Path:
    """Recorded-peak store, a sibling of the admission channel."""
    return Path(admission_path).with_name("command-peaks.json")


def read_recorded_peak(admission_path, key: str) -> float | None:
    """Largest peak in GiB recorded for ``key``, or None."""
    import json

    try:
        value = json.loads(Path(peaks_file(admission_path)).read_text(encoding="utf-8")).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def record_peak(admission_path, key: str, peak_gib: float) -> float:
    """Keep the larger of the stored and given peak for ``key``; returns the stored value."""
    import json
    import os

    path = peaks_file(admission_path)
    with admission_lock(admission_path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            data = {}
        stored = max(peak_gib, float(data.get(key) or 0))
        data[key] = stored
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)
    return stored


def register_command(
    admission_path, key: str, pid: int, peak_gib: float, create_time_fn=pid_create_time,
    *, reservation_session_id=None, reservation_run=None, pool_session_id=None, pool_run=None,
    cores: int = 1,
) -> None:
    """Append a START line stamped with ``ts`` and the pid's ``create_time`` (omitted when unreadable).

    The headroom is reserved until END, pid death, or the pid's create_time changing. ``cores`` is
    the declared core count the CPU axis sums (``reserved_cores``).
    """
    import time

    line = {
        "phase": "START", "session_id": "box-memory-snapshot", "run": f"{key}:{pid}",
        "pids": [pid], "declared_peak_mb": peak_gib * 1024, "declared_cores": max(1, int(cores)),
        "ts": time.time(),
    }
    created = create_time_fn(pid)
    if created is not None:
        line["create_time"] = created
    if reservation_session_id is not None and reservation_run is not None:
        line.update(session_id=reservation_session_id, run=reservation_run, command_key=key)
    if pool_session_id is not None and pool_run is not None:
        line.update(pool_session_id=pool_session_id, pool_run=pool_run)
    _append_admission(admission_path, line)


def _proc_peak_mb(proc, platform: str) -> float | None:
    """One process's peak resident MiB: ``peak_wset`` on Windows, ``VmHWM`` on Linux, rss elsewhere."""
    try:
        if platform == "win32":
            info = proc.memory_info()
            return (getattr(info, "peak_wset", None) or info.rss) / (1024 * 1024)
        if platform.startswith("linux"):
            with open(f"/proc/{proc.pid}/status", encoding="ascii", errors="replace") as fh:
                for line in fh:
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1]) / 1024
        return proc.memory_info().rss / (1024 * 1024)
    except Exception:
        return None


def tree_peak_mb(pid: int, platform: str | None = None) -> float | None:
    """Peak RAM in MiB summed over ``pid`` and its live descendants; None when ``pid`` is unreadable."""
    try:
        import psutil

        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
    except Exception:
        return None
    plat = sys.platform if platform is None else platform
    peaks = [p for p in (_proc_peak_mb(proc, plat) for proc in procs) if p is not None]
    return sum(peaks) if peaks else None


def _stamped_run_peaks(run: str, home) -> tuple[float | None, float | None]:
    """(peak_ram_mb, peak_vram_mib) the local capacity stamp holds for ``run``; None per axis when absent."""
    record = _engine_module("coordinator_core.group_em.capacity_record").read({"root": home})
    if record.get("stale"):
        return None, None
    for job in record.get("jobs") or []:
        if isinstance(job, dict) and job.get("run") == run:
            return job.get("peak_ram_mb"), job.get("peak_vram_mib")
    return None, None


def record_measured_peak(job_type: str, pid: int, run: str, home=None) -> bool:
    """Fold the run's measured peaks into ``job-peaks.json[job_type]``; False when nothing was measured or recorded.

    RAM is the highest the watch ticks stamped for the run, folded with the live process tree's peak
    when ``pid`` is still readable (release usually follows exit, so the stamp is the common source;
    the only one on Darwin, where the releaser holds no peak counter). VRAM is the
    per-process figure the capacity stamp assigned to the run. Never raises.
    """
    try:
        if home is None:
            home = _engine_module("coordinator_core._settings_home").settings_home()
        ram = tree_peak_mb(pid)
        stamped_ram, stamped_vram = _stamped_run_peaks(run, home)
        ram_parts = [v for v in (ram, stamped_ram) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        measured = {}
        if ram_parts:
            measured["ram_mb"] = max(ram_parts)
        if isinstance(stamped_vram, (int, float)) and not isinstance(stamped_vram, bool):
            measured["vram_mib"] = stamped_vram
        if not measured:
            return False
        return bool(_engine_module("coordinator_core.group_em.job_peaks").record(job_type, measured, home))
    except Exception:
        return False


def release_command(
    admission_path, key: str, pid: int, *, reservation_session_id=None, reservation_run=None,
    job_type=None, peaks_home=None,
) -> None:
    """Append the END line that frees a registered command's reservation (under ``admission_lock``, so a concurrent compaction cannot drop it).

    Before the END line, the run's measured peaks go to ``job_peaks`` under ``job_type`` (default
    ``key``); ``peaks_home`` overrides the settings home. The declared peak stays only the
    reservation. A failed peak record never fails the release.
    """
    run = reservation_run if reservation_run is not None else f"{key}:{pid}"
    record_measured_peak(job_type or key, pid, run, peaks_home)
    with admission_lock(admission_path):
        _append_admission(admission_path, {
            "phase": "END", "session_id": reservation_session_id if reservation_session_id is not None else "box-memory-snapshot",
            "run": reservation_run if reservation_run is not None else f"{key}:{pid}", "pids": [],
        })


def _append_admission(admission_path, line: dict) -> None:
    import json

    path = Path(admission_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


@dataclass(frozen=True)
class AdmitVerdict:
    """Admission decision with the memory clauses and the CPU axis exposed.

    ``admit`` is false when any axis fails; ``cpu_ok`` is true for a pure memory check.
    """

    admit: bool
    need_avail: float
    avail_ok: bool
    commit_ok: bool
    cpu_ok: bool = True
    declared_cores: int = 1
    reserved_cores: int = 0
    cpu_budget: int | None = None

    @property
    def hold_reason(self) -> str:
        """Empty when admitted; otherwise one clause per failed axis, the CPU axis starting ``cpu:``."""
        if self.admit:
            return ""
        parts = []
        if not self.avail_ok:
            parts.append("memory: available below need")
        if not self.commit_ok:
            parts.append("commit: over limit")
        if not self.cpu_ok:
            parts.append(
                f"cpu: declared {self.declared_cores} + reserved {self.reserved_cores} cores"
                f" > budget {self.cpu_budget}"
            )
        return "HOLD " + "; ".join(parts)


def _with_cpu_axis(verdict: AdmitVerdict, declared: int, reserved: int, budget: int | None) -> AdmitVerdict:
    """Fold the CPU axis into a memory verdict.

    Answers "do these legs' summed cores fit the box?". A leg alone on the box (nothing else
    reserved) always fits, so an over-wide declaration never refuses legitimate work forever.
    """
    import dataclasses

    declared = max(1, int(declared))
    budget = default_cpu_budget() if budget is None else budget
    cpu_ok = reserved == 0 or declared + reserved <= budget
    return dataclasses.replace(
        verdict, admit=verdict.admit and cpu_ok, cpu_ok=cpu_ok,
        declared_cores=declared, reserved_cores=reserved, cpu_budget=budget,
    )


@contextlib.contextmanager
def admission_lock(admission_path):
    """Exclusive cross-process lock on ``<admission>.lock`` (blocking, no deadline: a hung holder stalls every admit) for one check-and-reserve section."""
    path = Path(admission_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a+b") as fh:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def admit_and_register(
    admission_path,
    key: str,
    pid: int,
    peak_gib: float,
    status: MemoryStatus,
    *,
    cushion_pct: float = 25.0,
    commit_limit: int | None = None,
    cores: int = 1,
    cpu_budget: int | None = None,
    **reserved_kwargs,
) -> tuple[AdmitVerdict, int]:
    """Read reservations, decide and write the START line under one lock; returns (verdict, reserved bytes).

    Two concurrent callers serialize, so the second sees the first's reservation. ``cores`` is the
    leg's declared cores (undeclared = 1) and ``cpu_budget`` the box budget (None = ``default_cpu_budget()``);
    the verdict holds when declared plus already-reserved cores exceed it.
    """
    import dataclasses

    liveness = {k: v for k, v in reserved_kwargs.items() if k in ("alive_fn", "create_time_fn", "image_fn", "now_fn")}
    with admission_lock(admission_path):
        compact_admission(admission_path, locked=True, **liveness)
        reserved = reserved_bytes(admission_path, **reserved_kwargs)
        adjusted = dataclasses.replace(
            status,
            avail_phys=max(0, status.avail_phys - reserved),
            commit_used=status.commit_used + reserved,
        )
        verdict = admit(int(peak_gib * GIB), adjusted, cushion_pct=cushion_pct, commit_limit=commit_limit)
        verdict = _with_cpu_axis(verdict, cores, reserved_cores(admission_path, exclude_pid=pid, **liveness), cpu_budget)
        if verdict.admit:
            register_command(admission_path, key, pid, peak_gib, cores=cores,
                             **{k: v for k, v in liveness.items() if k == "create_time_fn"})
    return verdict, reserved


def _parent_pool_credit(admission_path, rows, selection, peak_mb, pid, reserved_kwargs):
    """Check active linked allocations independently of RSS reads, under admission_lock."""
    import math
    import time

    starts, _ = _ledger_starts(admission_path)
    parent_key = (selection.get("pool_session_id"), selection.get("pool_run"))
    own_key = (selection.get("session_id"), selection.get("run"))
    if not all(isinstance(value, str) and value for value in (*parent_key, *own_key)) or parent_key == own_key:
        raise ValueError("invalid parent pool identity")
    alive = reserved_kwargs.get("alive_fn", pid_alive)
    birth = reserved_kwargs.get("create_time_fn", pid_create_time)
    image = reserved_kwargs.get("image_fn", pid_image)
    now = reserved_kwargs.get("now_fn", time.time)
    parent = starts.get(parent_key)
    if not isinstance(parent, dict) or not _verified_pool_line(parent, alive, birth, image, now):
        raise ValueError("parent pool has no active START with reliable PID birth evidence")
    if parent.get("pool_session_id") or parent.get("pool_run"):
        raise ValueError("nested parent pools are not supported")
    capacity = _num(parent.get("declared_peak_mb"))
    if capacity is None or not math.isfinite(capacity) or not 0 < capacity <= 1048576:
        raise ValueError("parent pool registered peak is invalid")
    validator = selection.get("validate_parent_peak")
    if not callable(validator):
        raise ValueError("parent pool grant validator is missing")
    validator(capacity)
    allocated = 0
    for key, line in starts.items():
        linked = (line.get("pool_session_id"), line.get("pool_run")) == parent_key
        if key == own_key and not linked:
            raise ValueError("child run is already registered outside this selected parent pool")
        if not linked:
            continue
        pids = line.get("pids") or []
        if not any(alive(value) for value in pids):
            continue
        if not _verified_pool_line(line, alive, birth, image, now):
            raise ValueError("active child pool allocation has unreadable or mismatched PID birth evidence")
        size = _num(line.get("declared_peak_mb"))
        if size is None or not math.isfinite(size) or size <= 0:
            raise ValueError("active child pool allocation has an invalid peak")
        if key == own_key:
            if peak_mb < size:
                raise ValueError("existing child allocation cannot shrink without explicit release")
            if pid is not None and line["pids"] != [pid]:
                raise ValueError("child run is already allocated to a different active PID")
            continue  # Rechecking one run replaces its allocation; it never adds it twice.
        allocated += size
    if peak_mb > capacity or allocated + peak_mb > capacity:
        raise ValueError("requested child allocations exceed the parent's registered pool peak")
    parent_rows = [row for row in rows if (row["session_id"], row["run"]) == parent_key and row["pid"] is not None]
    if len(parent_rows) != 1:
        raise ValueError("parent pool reservation/RSS evidence is missing or ambiguous")
    return min(parent_rows[0]["bytes"], int(peak_mb * 1024**2)), {
        "pool_session_id": parent_key[0], "pool_run": parent_key[1],
        "pool_peak_mb": capacity, "allocated_peak_mb": allocated + peak_mb,
        "remaining_peak_mb": capacity - allocated - peak_mb,
    }


def admit_selected_reservation(
    admission_path, peak_gib: float, status: MemoryStatus, selector,
    *, key: str | None = None, pid: int | None = None, cushion_pct: float = 25.0,
    commit_limit: int | None = None, cores: int = 1, cpu_budget: int | None = None, **reserved_kwargs,
) -> tuple[AdmitVerdict, int, dict]:
    """Credit one validated caller grant or parent pool during atomic check-and-register.

    ``selector`` is an engine callback, not wire data: it verifies the actual
    caller's grant or native parent lineage in the real settings store while
    this lock is held. Only the explicit selection receives credit; linked child
    peaks remain bounded by the parent's active registered budget. Default
    admission never calls this opt-in path.
    """
    import dataclasses
    import time

    if (key is None) != (pid is None):
        raise ValueError("selected reservation registration requires both key and pid")
    with admission_lock(admission_path):
        selection = selector()
        if not isinstance(selection, dict) or selection.get("kind") not in ("own-grant", "parent-pool"):
            raise ValueError("invalid reservation selector")
        sid, run = selection.get("session_id"), selection.get("run")
        rows = _holdings(admission_path, reserved_kwargs.get("rss_fn", tree_rss_mb),
            reserved_kwargs.get("alive_fn", pid_alive), reserved_kwargs.get("create_time_fn", pid_create_time),
            reserved_kwargs.get("image_fn", pid_image), reserved_kwargs.get("now_fn", time.time))
        extra = {}
        if selection["kind"] == "own-grant":
            grant = selection.get("grant")
            if not isinstance(grant, dict):
                raise ValueError("validated reservation grant is missing")
            if not sid or not run or grant.get("grantee_session_id") != sid or grant.get("run") != run:
                raise ValueError("reservation selector does not match its grant")
            credit_rows = [row for row in rows if row["pid"] is None and row["session_id"] == sid and row["run"] == run
                           and row.get("grant_issuer_session_id") == grant.get("issuer_session_id")]
            credit = min(sum(row["bytes"] for row in credit_rows), int(grant["declared_peak_mb"] * 1024**2))
        else:
            credit, extra = _parent_pool_credit(admission_path, rows, selection, peak_gib * 1024, pid, reserved_kwargs)
        reserved = sum(row["bytes"] for row in rows) - credit
        adjusted = dataclasses.replace(status, avail_phys=max(0, status.avail_phys - reserved),
                                       commit_used=status.commit_used + reserved)
        verdict = admit(int(peak_gib * GIB), adjusted, cushion_pct=cushion_pct, commit_limit=commit_limit)
        cpu_live = {k: v for k, v in reserved_kwargs.items() if k in ("alive_fn", "create_time_fn", "image_fn", "now_fn")}
        verdict = _with_cpu_axis(verdict, cores, reserved_cores(admission_path, exclude_key=(sid, run), **cpu_live), cpu_budget)
        if verdict.admit and pid is not None:
            birth = reserved_kwargs.get("create_time_fn", pid_create_time)(pid)
            import math
            if not isinstance(birth, (float, int)) or isinstance(birth, bool) or not math.isfinite(birth) or birth <= 0:
                raise ValueError("selected reservation requires reliable PID birth evidence")
            register_command(admission_path, key, pid, peak_gib,
                create_time_fn=lambda value: birth, reservation_session_id=sid, reservation_run=run, cores=cores,
                **{k: extra[k] for k in ("pool_session_id", "pool_run") if k in extra})
    return verdict, reserved, {"kind": selection["kind"], "session_id": sid, "run": run, "credited_bytes": credit, **extra}


def admit(
    peak: int,
    status: MemoryStatus,
    cushion_pct: float = 25.0,
    cushion_cap: int = 8 * GIB,
    commit_limit: int | None = None,
) -> AdmitVerdict:
    """Pure admission check; need is peak + min(cushion_pct of peak, cushion_cap) against ``status.avail_phys``."""
    need_avail = peak + min(peak * cushion_pct / 100, cushion_cap)
    avail_ok = need_avail <= status.avail_phys
    commit_ok = status.commit_used + peak <= (status.commit_limit if commit_limit is None else commit_limit)
    return AdmitVerdict(
        admit=avail_ok and commit_ok,
        need_avail=need_avail,
        avail_ok=avail_ok,
        commit_ok=commit_ok,
    )
