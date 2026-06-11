"""
coordinator_whoami/host_probes.py — generic machine/repo/install probe functions.

Twelve probe functions that interrogate local host state: OS, CPU architecture,
GPU presence, system memory, disk capacity, host identity, memory-ceiling
mechanism, Python interpreter, uv tool, Claude config, coordinator plugin,
and current working directory project kind. These probes are generic and not
specific to any adopter — they capture facts about the host that any whoami
adopter (project-rag, session, holodeck, …) may include in its envelope.

Extracted from coordinator_whoami.project_rag.cli as part of the C1 refactor
(archive/specs/2026-05-27-whoami-session-spine-refactor.md § C1) so the session
adopter (C2) and any future adopter can reuse them without importing through
the project-rag subpackage.

Negative spec: these probes do NOT import torch, chromadb, or any heavy ML
dependency. They use only stdlib + subprocess for fast, standalone execution.
torch CUDA-build version is deliberately excluded — it is venv-scoped (describes
the installed wheel, drifts per-interpreter) rather than machine-scoped; it
belongs in an interpreter inventory, not machine.*. subprocess is permitted and
used by several probes (nvidia-smi, uv, physical-core queries).

The project-rag adopter (coordinator_whoami.project_rag.cli) retains its own
probes (_probe_source, _probe_engine_version, _probe_project_kind,
_probe_project_rag_state) which require project-rag-specific state.

Spec backlink: archive/specs/2026-05-27-whoami-host-capacity-fields.md
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

# resource is POSIX-only; on Windows it does not exist. Import once at module
# level so tests can monkeypatch coordinator_whoami.host_probes.resource cleanly.
try:
    import resource  # type: ignore[import-not-found]
except ImportError:
    resource = None  # type: ignore[assignment]

# Windows-only: suppress the console window that console-subsystem child
# processes (powershell, nvidia-smi, uv, ...) flash when this process has no
# console to inherit (e.g. spawned by an MCP server or a GUI Claude Code host).
# POSIX: empty dict — CREATE_NO_WINDOW is a Windows-only attribute, so the
# ternary short-circuits before touching it. Splatted into every spawn here
# including the macOS-only sysctl/vm_stat/ioreg branches (a no-op there) so the
# guard invariant is total — see tripwire CONSOLE-FLASH-GUARD-PY.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _probe_os() -> dict[str, Any]:
    """Probe OS name, version string, active shell, and is_windows flag.

    is_windows derives from sys.platform (hang-free — does not touch WMI).
    On the Windows branch, sys.getwindowsversion() is the primary version
    source (also hang-free). platform.version() is only reached as a fallback
    and, when called, runs on a daemon thread with a 3-second timeout so a
    leaked hung WMI query cannot block process exit in long-lived consumers.
    """
    is_windows: bool = sys.platform == "win32"
    name = platform.system()

    # --- Version string --------------------------------------------------
    if is_windows:
        # Use sys.getwindowsversion() as the primary hang-free source.
        try:
            wv = sys.getwindowsversion()
            version: str = f"{wv.major}.{wv.minor}.{wv.build}"
        except Exception:
            version = "unknown"

        # Normalise to friendly name; Windows 11 is NT 10.0 build ≥ 22000.
        try:
            build = int(version.split(".")[-1])
            pretty = "Windows 11" if build >= 22000 else "Windows 10"
        except (ValueError, IndexError):
            pretty = "Windows"

        # Append edition cheaply via winreg (no WMI).
        try:
            # Review: code-reviewer — nit: win32_edition() is 3.8+; the except guard covers older interpreters.
            edition = platform.win32_edition()
        except Exception:
            edition = None
        if edition:
            pretty = f"{pretty} {edition}"
    else:
        # Non-Windows: platform.version() is safe; no WMI involved.
        version = platform.version()

        if name == "Darwin":
            pretty = "macOS"
        elif name == "Linux":
            pretty = "Linux"
        else:
            pretty = name

    # --- Shell -----------------------------------------------------------
    shell = os.environ.get("SHELL")
    if not shell and is_windows:
        ps_path = os.environ.get("PSModulePath", "")
        if ps_path:
            shell = "powershell"
        else:
            comspec = os.environ.get("COMSPEC", "")
            shell = Path(comspec).stem.lower() if comspec else "cmd"

    return {
        "name": pretty,
        "version": version,
        "shell": shell or "unknown",
        "is_windows": is_windows,
    }


def _probe_arch() -> dict[str, Any]:
    """Probe CPU architecture, logical core count, physical core count, and Apple Silicon flag.

    logical_cores: os.cpu_count() — includes hyperthreads (int or None).
    physical_cores: best-effort per-OS, None on failure.
      macOS: sysctl -n hw.physicalcpu
      Linux: unique (physical id, core id) pairs in /proc/cpuinfo
      Windows: PowerShell Get-CimInstance Win32_Processor sum of NumberOfCores
    """
    machine = platform.machine()
    apple_silicon = (platform.system() == "Darwin") and (machine == "arm64")
    logical_cores: int | None = os.cpu_count()
    physical_cores: int | None = None

    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.physicalcpu"],
                capture_output=True,
                text=True,
                timeout=5,
                **_NO_CONSOLE_WINDOW,
            )
            if result.returncode == 0:
                physical_cores = int(result.stdout.strip())
        elif sys.platform == "linux":
            try:
                cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
                # Collect unique (physical id, core id) pairs.
                pairs: set[tuple[str, str]] = set()
                phys_id: str | None = None
                core_id: str | None = None
                for line in cpuinfo.splitlines():
                    if line.startswith("physical id"):
                        phys_id = line.split(":")[1].strip()
                    elif line.startswith("core id"):
                        core_id = line.split(":")[1].strip()
                    elif line.strip() == "" and phys_id is not None and core_id is not None:
                        pairs.add((phys_id, core_id))
                        phys_id = None
                        core_id = None
                # Review: code-reviewer — P2: real /proc/cpuinfo may not end with a blank line;
                # flush any pending pair so the last socket is not miscounted.
                if phys_id is not None and core_id is not None:
                    pairs.add((phys_id, core_id))
                if pairs:
                    physical_cores = len(pairs)
                else:
                    # Fallback: count "core id" occurrences (single-socket).
                    count = sum(1 for line in cpuinfo.splitlines() if line.startswith("core id"))
                    physical_cores = count if count > 0 else None
            except OSError:
                physical_cores = None
        elif sys.platform == "win32":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                **_NO_CONSOLE_WINDOW,
            )
            if result.returncode == 0:
                val = result.stdout.strip()
                if val.isdigit():
                    physical_cores = int(val)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        physical_cores = None

    return {
        "machine": machine,
        "apple_silicon": apple_silicon,
        "logical_cores": logical_cores,
        "physical_cores": physical_cores,
    }


def _probe_gpu() -> dict[str, Any]:
    """Probe GPU presence via nvidia-smi (fast, no torch import).

    Returns keys: present, vendor, vram_free_mib, cuda_driver,
    vram_total_mib, name, compute_capability, driver_model, device_count.
    On non-NVIDIA machines or when nvidia-smi is absent, present=False and
    all new keys are None (device_count is None).

    Review: code-reviewer — P2: per-device fields (vram_total_mib, vram_free_mib, name,
    compute_capability, driver_model) describe device 0 only; device_count is the total
    across all devices. Multi-GPU per-device enumeration is OOS by plan design — consumers
    that need per-device breakdown must query nvidia-smi independently.

    nvidia-smi query column order:
      count, name, memory.total(MiB), memory.free(MiB),
      driver_version, compute_cap, driver_model.current
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=count,name,memory.total,memory.free,driver_version,compute_cap,driver_model.current",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            **_NO_CONSOLE_WINDOW,
        )
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]

                def _int_or_none(val: str) -> int | None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return None

                def _str_or_none(val: str) -> str | None:
                    if not val or val.upper() in ("N/A", "[N/A]"):
                        return None
                    return val

                device_count = _int_or_none(parts[0]) if len(parts) > 0 else None
                gpu_name = _str_or_none(parts[1]) if len(parts) > 1 else None
                vram_total = _int_or_none(parts[2]) if len(parts) > 2 else None
                vram_free = _int_or_none(parts[3]) if len(parts) > 3 else None
                driver = _str_or_none(parts[4]) if len(parts) > 4 else None
                compute_cap = _str_or_none(parts[5]) if len(parts) > 5 else None
                driver_model = _str_or_none(parts[6]) if len(parts) > 6 else None

                return {
                    "present": True,
                    "vendor": "nvidia",
                    "vram_free_mib": vram_free,
                    "cuda_driver": driver,
                    "vram_total_mib": vram_total,
                    "name": gpu_name,
                    "compute_capability": compute_cap,
                    "driver_model": driver_model,
                    "device_count": device_count,
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        pass

    return {
        "present": False,
        "vendor": None,
        "vram_free_mib": None,
        "cuda_driver": None,
        "vram_total_mib": None,
        "name": None,
        "compute_capability": None,
        "driver_model": None,
        "device_count": None,
    }


def _probe_memory() -> dict[str, Any]:
    """Probe system RAM and commit limits.

    Returns {total_bytes, available_bytes, commit_limit_bytes, commit_available_bytes}
    as int (bytes) or None on failure. All values are in bytes, not MiB.

    Windows: ctypes GlobalMemoryStatusEx (ullTotalPhys/ullAvailPhys for RAM;
             ullTotalPageFile/ullAvailPageFile for commit limit = RAM + pagefile).
    Linux:   /proc/meminfo (MemTotal/MemAvailable/CommitLimit/Committed_AS in kB).
    macOS:   sysctl hw.memsize for total; vm_stat for available best-effort;
             commit best-effort via vm.swapusage (total = physical + swap).
             None where not derivable.
    """
    _null: dict[str, Any] = {
        "total_bytes": None,
        "available_bytes": None,
        "commit_limit_bytes": None,
        "commit_available_bytes": None,
    }

    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            # Review: code-reviewer — P1: capture return value; on failure raise WinError so
            # the outer except Exception folds to _null instead of returning zeros.
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            if not ok:
                raise ctypes.WinError()
            return {
                "total_bytes": int(stat.ullTotalPhys),
                "available_bytes": int(stat.ullAvailPhys),
                "commit_limit_bytes": int(stat.ullTotalPageFile),
                "commit_available_bytes": int(stat.ullAvailPageFile),
            }

        elif sys.platform == "linux":
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace")
            values: dict[str, int] = {}
            for line in meminfo.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    try:
                        values[key] = int(parts[1])  # value in kB
                    except ValueError:
                        pass
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            commit_limit = values.get("CommitLimit")
            committed_as = values.get("Committed_AS")

            commit_available: int | None = None
            if commit_limit is not None and committed_as is not None:
                # Review: code-reviewer — Finding 11 (EM DECISION): do NOT clamp.
                # commit_available_bytes may be negative under active overcommit
                # (Committed_AS > CommitLimit); a negative value means the system is already
                # over its commit limit — consumers gating on headroom should treat <= 0 as
                # 'no headroom'.
                commit_available = commit_limit - committed_as

            return {
                "total_bytes": total * 1024 if total is not None else None,
                "available_bytes": available * 1024 if available is not None else None,
                "commit_limit_bytes": commit_limit * 1024 if commit_limit is not None else None,
                "commit_available_bytes": commit_available * 1024 if commit_available is not None else None,
            }

        elif sys.platform == "darwin":
            # Total: hw.memsize (bytes directly)
            total_bytes: int | None = None
            try:
                r = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5,
                    **_NO_CONSOLE_WINDOW,
                )
                if r.returncode == 0:
                    total_bytes = int(r.stdout.strip())
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
                pass

            # Available: vm_stat (free + inactive pages * page_size) — best-effort
            available_bytes: int | None = None
            try:
                r2 = subprocess.run(
                    ["vm_stat"],
                    capture_output=True, text=True, timeout=5,
                    **_NO_CONSOLE_WINDOW,
                )
                if r2.returncode == 0:
                    page_size = 4096  # default; may be overridden below
                    ps_match = re.search(r"page size of (\d+) bytes", r2.stdout)
                    if ps_match:
                        page_size = int(ps_match.group(1))
                    vm_values: dict[str, int] = {}
                    for vm_line in r2.stdout.splitlines():
                        vm_match = re.match(r"Pages\s+([\w\s]+):\s+(\d+)", vm_line)
                        if vm_match:
                            vm_values[vm_match.group(1).strip()] = int(vm_match.group(2))
                    # Review: code-reviewer — P2: available_bytes must be None (not 0)
                    # when neither "free" nor "inactive" present in vm_stat output.
                    free = vm_values.get("free")
                    inactive = vm_values.get("inactive")
                    if free is not None or inactive is not None:
                        available_bytes = ((free or 0) + (inactive or 0)) * page_size
                    else:
                        available_bytes = None
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
                pass

            # Commit: best-effort via vm.swapusage — total virtual = phys + swap
            commit_limit_bytes: int | None = None
            commit_available_bytes: int | None = None
            try:
                r3 = subprocess.run(
                    ["sysctl", "-n", "vm.swapusage"],
                    capture_output=True, text=True, timeout=5,
                    **_NO_CONSOLE_WINDOW,
                )
                if r3.returncode == 0:
                    # "total = X.00M  used = Y.00M  free = Z.00M"
                    swap_total_match = re.search(r"total\s*=\s*([\d.]+)([KMGT]?)", r3.stdout)
                    swap_free_match = re.search(r"free\s*=\s*([\d.]+)([KMGT]?)", r3.stdout)
                    if swap_total_match and total_bytes is not None:
                        def _parse_swap(val: str, unit: str) -> int:
                            f = float(val)
                            mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}.get(unit, 1)
                            return int(f * mult)
                        swap_total = _parse_swap(swap_total_match.group(1), swap_total_match.group(2))
                        commit_limit_bytes = total_bytes + swap_total
                        if swap_free_match:
                            swap_free = _parse_swap(swap_free_match.group(1), swap_free_match.group(2))
                            commit_available_bytes = swap_free + (available_bytes or 0)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
                pass

            return {
                "total_bytes": total_bytes,
                "available_bytes": available_bytes,
                "commit_limit_bytes": commit_limit_bytes,
                "commit_available_bytes": commit_available_bytes,
            }

        else:
            return _null

    except Exception:
        return _null


def _probe_disk(paths: list[str] | None = None) -> list[dict[str, Any]]:
    """Probe disk capacity for each requested path.

    Args:
        paths: List of filesystem paths to probe. Defaults to [os.getcwd()].

    Returns a list of {path, total_bytes, free_bytes} dicts. If a path fails
    (PermissionError, OSError, non-existent), total_bytes and free_bytes are
    None but the entry is still included. Values are in bytes.
    """
    if paths is None:
        paths = [os.getcwd()]

    results: list[dict[str, Any]] = []
    for p in paths:
        try:
            usage = shutil.disk_usage(p)
            results.append({
                "path": p,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
            })
        except (OSError, PermissionError):
            results.append({
                "path": p,
                "total_bytes": None,
                "free_bytes": None,
            })
    return results


def _probe_host() -> dict[str, Any]:
    """Probe hostname and machine identity.

    hostname: socket.gethostname() — always present.
    machine_id: best-effort per-OS, None on failure.
      Linux:   read /etc/machine-id or /var/lib/dbus/machine-id
      Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography MachineGuid (winreg)
      macOS:   ioreg -rd1 -c IOPlatformExpertDevice → IOPlatformUUID
    """
    try:
        hostname: str = socket.gethostname()
    except Exception:
        hostname = "unknown"

    machine_id: str | None = None

    try:
        if sys.platform == "linux":
            for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    machine_id = Path(candidate).read_text(encoding="utf-8").strip()
                    if machine_id:
                        break
                except OSError:
                    continue

        elif sys.platform == "win32":
            import winreg
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "MachineGuid")
                    machine_id = str(value)
            except OSError:
                machine_id = None

        elif sys.platform == "darwin":
            r = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5,
                **_NO_CONSOLE_WINDOW,
            )
            if r.returncode == 0:
                m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', r.stdout)
                if m:
                    machine_id = m.group(1)

    except Exception:
        machine_id = None

    return {
        "hostname": hostname,
        "machine_id": machine_id,
    }


def _probe_mem_ceiling_mechanism() -> str:
    """Probe the active memory-ceiling mechanism for this process.

    Returns one of:
      "cgroup_v2"     — Linux cgroup v2 memory limit is set
      "cgroup_v1"     — Linux cgroup v1 memory limit is set
      "rlimit"        — POSIX RLIMIT_AS is finite
      "win_jobobject" — Windows Job Object memory limit is active
      "none"          — probed successfully, no ceiling in effect
      "unknown"       — probe could not run or failed (cannot determine)

    The distinction between "none" and "unknown" is load-bearing: a consumer's
    commit-gate safety posture flips on it (Decision-5).
    """
    try:
        if sys.platform == "linux":
            # cgroup v2: /sys/fs/cgroup/memory.max
            cg2 = Path("/sys/fs/cgroup/memory.max")
            if cg2.exists():
                content = cg2.read_text(encoding="utf-8").strip()
                if content and content != "max":
                    return "cgroup_v2"

            # cgroup v1: /sys/fs/cgroup/memory/memory.limit_in_bytes
            cg1 = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            if cg1.exists():
                content = cg1.read_text(encoding="utf-8").strip()
                # Default (no limit) is typically 9223372036854771712 or similar large value.
                # Any value that is not the maximum sentinel is considered a real limit.
                try:
                    limit_val = int(content)
                    # Linux sets this to a near-LLONG_MAX sentinel when there is no limit.
                    if limit_val < (2**63 - 4096):
                        return "cgroup_v1"
                except ValueError:
                    pass

            # POSIX rlimit — resource is imported at module level (POSIX-only, None on Windows)
            # Review: code-reviewer — P1: guard resource is None; tests patching sys.platform='linux'
            # on a Windows host would dereference None without this guard.
            if resource is None:
                return "unknown"
            soft, _ = resource.getrlimit(resource.RLIMIT_AS)
            if soft != resource.RLIM_INFINITY:
                return "rlimit"

            return "none"

        elif sys.platform == "win32":
            # IsProcessInJob + QueryInformationJobObject
            JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
            JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_ulong),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_ulong),
                    ("Affinity", ctypes.c_size_t),  # Review: code-reviewer — P1: ULONG_PTR is pointer-sized; c_ulong is 4B on 64-bit Windows shifting all later fields
                    ("PriorityClass", ctypes.c_ulong),
                    ("SchedulingClass", ctypes.c_ulong),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            in_job = ctypes.c_int(0)
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # Review: code-reviewer — P2: handle is pointer-sized; default c_int truncates on 64-bit.
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            current_process = kernel32.GetCurrentProcess()
            ok = kernel32.IsProcessInJob(current_process, None, ctypes.byref(in_job))

            if ok and in_job.value:
                JobObjectExtendedLimitInformation = 9
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                ret = kernel32.QueryInformationJobObject(
                    None,  # current job
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info),
                    None,
                )
                if ret:
                    flags = info.BasicLimitInformation.LimitFlags
                    if flags & (JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY):
                        return "win_jobobject"

            return "none"

        else:
            # Non-Linux non-Windows (macOS etc.): no mechanism implemented.
            # Review: code-reviewer — nit: "unknown"=not-determined (probe not attempted);
            # "none"=probed-and-no-ceiling. macOS probe is not implemented, so "unknown" is correct.
            return "unknown"

    except Exception:
        return "unknown"


def _probe_python() -> dict[str, Any]:
    """Probe invoking Python version, path, MS Store shim check, and .venv state.

    Uses the running interpreter as the invoking Python since whoami is invoked
    via `python -m coordinator_whoami.<adopter>` — the invoking interpreter is
    what ran this code. MS Store shim detection: path contains WindowsApps or
    Microsoft\\WindowsApps.

    Review: code-reviewer — F5: renamed ambient_path/ambient_version → invoking_path/
    invoking_version; "ambient" was misleading under venv invocation where the
    interpreter is not the ambient system Python.
    """
    interp = sys.executable
    version = platform.python_version()

    ms_store_shim = bool(
        interp
        and (
            "WindowsApps" in interp
            or "Microsoft\\WindowsApps" in interp
            or "Microsoft/WindowsApps" in interp
        )
    )

    # .venv detection: look for a .venv adjacent to the repo root.
    # Walk up from CWD to find pyproject.toml as proxy for repo root.
    venv_present = False
    venv_python: str | None = None

    try:
        cwd = Path.cwd()
        candidate = cwd
        for _ in range(6):  # up to 6 levels up
            pyproject = candidate / "pyproject.toml"
            if pyproject.exists():
                venv_dir = candidate / ".venv"
                if venv_dir.is_dir():
                    venv_present = True
                    # Locate python executable inside the venv.
                    for rel in (
                        "Scripts/python.exe",
                        "Scripts/python",
                        "bin/python",
                        "bin/python3",
                    ):
                        venv_py = venv_dir / rel
                        if venv_py.exists():
                            venv_python = str(venv_py)
                            break
                break
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent
    except (OSError, PermissionError):
        pass

    return {
        "invoking_version": version,
        "invoking_path": interp,
        "ms_store_shim": ms_store_shim,
        "venv_present": venv_present,
        "venv_python": venv_python,
    }


def _probe_uv() -> dict[str, Any]:
    """Probe uv presence and version via subprocess (no shell script required)."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            **_NO_CONSOLE_WINDOW,
        )
        if result.returncode == 0:
            # "uv 0.4.18" → "0.4.18"
            output = result.stdout.strip()
            parts = output.split()
            version = parts[1] if len(parts) >= 2 else output
            return {"present": True, "version": version}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return {"present": False, "version": None}


def _probe_claude() -> dict[str, Any]:
    """Probe ~/.claude.json existence and project-rag entry health.

    Reads from the CLAUDE_HOME env var if set (test-sandbox support),
    otherwise ~/.claude.json.

    Lookup order (W5 default install writes per-project, not top-level):
        1. Top-level: data["mcpServers"]["project-rag"]
        2. Per-project: data["projects"][<any>]["mcpServers"]["project-rag"]
    Returns "healthy" on the first non-None entry found in either location.

    Entry health:
        "healthy"  — mcpServers.project-rag exists with a non-empty command/args
                     (checked in top-level mcpServers first, then per-project)
        "broken"   — mcpServers.project-rag key exists but looks malformed
        "absent"   — no mcpServers.project-rag key found anywhere
        "no_file"  — ~/.claude.json does not exist
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        claude_json_path = Path(claude_home) / ".claude.json"
    else:
        claude_json_path = Path.home() / ".claude.json"

    if not claude_json_path.exists():
        return {"json_present": False, "project_rag_entry": "no_file"}

    try:
        data = json.loads(claude_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"json_present": True, "project_rag_entry": "broken"}

    def _check_entry(entry: Any) -> str | None:
        """Return health verdict for a single mcpServers entry, or None if absent."""
        if entry is None:
            return None
        # HTTP-transport entries carry "url" instead of "command"/"args"
        # (post-multi-RAG MCP daemon shape); accept either as evidence of a
        # configured entry. Cf. project-rag-ue-addon dogfood F4 (2026-05-20).
        endpoint = entry.get("command") or entry.get("args") or entry.get("url")
        if not endpoint:
            return "broken"
        return "healthy"

    # Review: code-reviewer — F1: top-level lookup misses W5 per-project install path.
    # Check top-level mcpServers first.
    mcp_servers = data.get("mcpServers") or {}
    top_level_entry = mcp_servers.get("project-rag")
    verdict = _check_entry(top_level_entry)
    if verdict is not None:
        return {"json_present": True, "project_rag_entry": verdict}

    # Fall through to per-project mcpServers (default W5 install shape).
    for proj_data in (data.get("projects") or {}).values():
        proj_mcp = (proj_data.get("mcpServers") if isinstance(proj_data, dict) else None) or {}
        per_project_entry = proj_mcp.get("project-rag")
        verdict = _check_entry(per_project_entry)
        if verdict is not None:
            return {"json_present": True, "project_rag_entry": verdict}

    return {"json_present": True, "project_rag_entry": "absent"}


def _probe_coordinator() -> dict[str, Any]:
    """Probe coordinator-claude installation state.

    Checks for the coordinator's CLAUDE.md at the standard plugin path
    under ~/.claude/plugins/coordinator-claude/.
    """
    claude_home = os.environ.get("CLAUDE_HOME")
    base = Path(claude_home) if claude_home else Path.home() / ".claude"
    coordinator_marker = base / "plugins" / "coordinator-claude" / "coordinator" / "CLAUDE.md"

    if coordinator_marker.exists():
        # Attempt to read version from the CLAUDE.md frontmatter — optional.
        version: str | None = None
        try:
            text = coordinator_marker.read_text(encoding="utf-8", errors="replace")
            # Look for "version: X.Y.Z" in frontmatter-like header.
            m = re.search(r"version:\s*([^\s\n]+)", text[:2000])
            if m:
                version = m.group(1)
        except OSError:
            pass
        return {"installed": True, "version": version}

    return {"installed": False, "version": None}


def _probe_project() -> dict[str, Any]:
    """Probe the current working directory for project kind markers.

    Checks CWD for .uproject, package.json, Cargo.toml, pyproject.toml.
    """
    cwd = Path.cwd()
    kind_markers = {
        "uproject": list(cwd.glob("*.uproject")),
        "package_json": cwd / "package.json",
        "cargo_toml": cwd / "Cargo.toml",
        "pyproject_toml": cwd / "pyproject.toml",
    }

    kinds_detected: list[str] = []
    uproject_present = bool(kind_markers["uproject"])

    if uproject_present:
        kinds_detected.append("unreal")
    if kind_markers["package_json"].exists():
        kinds_detected.append("typescript")
    if kind_markers["cargo_toml"].exists():
        kinds_detected.append("rust")
    if kind_markers["pyproject_toml"].exists():
        kinds_detected.append("python")

    return {
        "root": str(cwd),
        "kinds_detected": kinds_detected,
        "uproject_present": uproject_present,
    }
