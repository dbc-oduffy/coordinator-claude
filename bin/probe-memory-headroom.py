# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""probe-memory-headroom.py — best-effort cross-platform RAM/VRAM headroom probe.

Purpose: the load-bearing resource for a fan-out wave is memory commit (RAM/VRAM),
NOT CPU core count. The large-wave NOTE in bin/fan-out-dispatch.py historically used a
core-count proxy (3x logical cores); this probe is its memory-commit-aware successor —
it reads what actually degrades the machine (available RAM and free GPU VRAM) so the
fan-out advisory can surface live headroom and fire on a tight machine regardless of
wave size. See docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md SS111-114.

Design — best-effort, graceful degradation: this is a SOFT advisory input. Every probe
leg is wrapped so an unsupported platform, a missing tool (no nvidia GPU, no PowerShell),
a wedged driver, or a parse miss yields `unknown` for that field rather than aborting.
The caller treats `unknown` as "no signal on this axis" and falls back to the cores proxy.
Exit is always 0 except a usage error; absence of signal is communicated in the VALUES,
never the exit code. External tool calls (PowerShell / nvidia-smi) are wall-clock bounded
via coordinator_core.watchdog.cs_timeout (claude-klabauter) so a stuck nvidia-smi or a slow
PowerShell cold-start cannot stall the caller's dispatch.

Windows de-bash campaign (Plan C, Wave E3-d, per-op port): Port of:
probe-memory-headroom.sh (DoE 71e76370, 2026-07-21), which sourced
coordinator/lib/coordinator-claude-klabauter-root.sh and coordinator/lib/resolve-python.sh
to build a `cs_timeout` shell shim over a
`python -c` subprocess dispatching coordinator_core.watchdog.cs_timeout — bash needed
that native trampoline because bash itself has no portable built-in timeout (GNU
`timeout` / macOS `gtimeout` / background-kill fallback). Fix-in-port (DR-059):
Python's own `subprocess.run(..., timeout=secs)` IS a portable wall-clock bound on
every platform this probe targets, so wrapping it through the watchdog seam here would
be pure indirection with no functional benefit — this port bounds each external-tool
leg directly via `subprocess.run`'s native timeout, no watchdog dependency.

NOTE — sibling implementation: whoami/coordinator_whoami/host_probes.py::_probe_memory is
a SEPARATE RAM probe consumed by the machine-identity / doctor tooling (psutil-shaped).
This probe is authoritative for the fan-out path only. They are intentionally not
unified (different consumers, both soft-advisory) — keep this comment and that one
cross-referenced if either's contract changes.

Output (stdout) — stable key=value lines, always all four keys, value is an integer or
the literal `unknown`:
    ram_available_mb=<int|unknown>   # MemAvailable (Linux) / FreePhysicalMemory (Win) / free+inactive+spec (mac)
    ram_total_mb=<int|unknown>
    vram_free_mb=<int|unknown>       # summed across NVIDIA GPUs; unknown if no nvidia-smi
    vram_total_mb=<int|unknown>

Usage:
    python3 coordinator/bin/probe-memory-headroom.py            # key=value lines (machine-parseable)
    python3 coordinator/bin/probe-memory-headroom.py --human    # one human-readable sentence

Platform coverage: Linux/WSL (/proc/meminfo), Windows (PowerShell CIM), macOS
(sysctl + vm_stat). VRAM is NVIDIA-only (nvidia-smi) on any platform; AMD/Intel GPUs
report `unknown` (no portable query) — deliberately, not a bug.

Historical note (DR-059, superseded): the bash oracle's `_ram_from_windows` used
`read -r ... <<< "$out"` after stripping `\r`, which silently swallowed a
stderr-interleaved line if PowerShell printed a warning before its result line; the
first Python port (still shelling to `powershell.exe`) fixed this by scanning the LAST
non-blank output line instead of the first. That whole banner-noise concern is now moot:
`_ram_from_windows` queries `psutil.virtual_memory()` in-process (no PowerShell spawn,
no stdout to parse) per the PM's 2026-08-06 no-shell-spawns ruling. Kept here as
provenance for why the old parsing looked the way it did.

Exit codes:
    0  success (including "no signal on any axis" — a legitimate degraded-but-clean state)
    2  usage error (unrecognized argument)

Spec backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md SS111-114 (successor signal)
Spec backlink: docs/plans/2026-06-27-coordinator-watchdog.md [DEAD-CITATION: plan file never committed to this repo]
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Plan C, Wave E3-d)
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from typing import Optional


def _bootstrap_engine() -> None:
    """The engine root must be on sys.path before a `coordinator_core`
    import runs: this file is also published into the claude-klabauter
    mirror, where `coordinator_core` is NOT pip-installed and the
    interpreter's `sys.path[0]` is this bin/ directory, not the checkout
    root. Same bootstrap as coordinator/bin/coordinator-lesson-add
    (9b979ee5f)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)


def _bounded(secs: float, cmd: list[str]) -> Optional[str]:
    """Run cmd with a wall-clock cap; return stdout text, or None on any failure.

    See module docstring's Fix-in-port note: subprocess.run's own `timeout=`
    is the portable bound here — a wedged driver or slow cold-start raises
    TimeoutExpired, caught below and folded into the same "no signal on this
    axis" None return every other failure mode on this probe leg produces.
    """
    from coordinator_core.win_portability import no_console_creationflags

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=secs,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _fmt_mb(mb: int) -> str:
    """Render an MB integer as a compact human magnitude.

    "~N GB" at >=1 GB, "~N MB" below (integer GB truncation would print "~0 GB"
    for a memory-starved machine — exactly the case the headroom-tight signal
    exists to surface).
    """
    if mb >= 1024:
        return f"~{mb // 1024} GB"
    return f"~{mb} MB"


# --- RAM: Linux / WSL — /proc/meminfo is authoritative and cheap -------------


def _ram_from_proc() -> tuple[Optional[int], Optional[int]]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None, None
    avail_kb = None
    free_kb = None
    total_kb = None
    for line in text.splitlines():
        m = re.match(r"^MemAvailable:\s*(\d+)", line)
        if m:
            avail_kb = int(m.group(1))
            continue
        m = re.match(r"^MemFree:\s*(\d+)", line)
        if m:
            free_kb = int(m.group(1))
            continue
        m = re.match(r"^MemTotal:\s*(\d+)", line)
        if m:
            total_kb = int(m.group(1))
    # MemAvailable is the kernel's reclaim-aware estimate; fall back to
    # MemFree on pre-3.14 kernels that lack it (conservative — undercounts
    # true headroom).
    if avail_kb is None:
        avail_kb = free_kb
    if avail_kb is None:
        return None, None
    total_mb = total_kb // 1024 if total_kb is not None else None
    return avail_kb // 1024, total_mb


# --- RAM: Windows — PowerShell CIM (wmic is deprecated on Win11) ------------


def _ram_from_windows() -> tuple[Optional[int], Optional[int]]:
    """Windows available/total RAM via psutil (no shell spawn).

    `psutil.virtual_memory().available` is the reclaim-aware "available"
    estimate (same semantic as Linux MemAvailable) — a closer analogue to
    the other platform legs here than the old PowerShell path's
    FreePhysicalMemory (which was "free", not "available"). `.total` is
    total physical RAM. Returns `(None, None)` on any failure; never raises.
    """
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - psutil is a declared dependency
        return None, None
    try:
        vm = psutil.virtual_memory()
        avail_bytes = vm.available
        total_bytes = vm.total
    except Exception:  # pragma: no cover - psutil internals, defensive only
        return None, None
    return avail_bytes // (1024 * 1024), total_bytes // (1024 * 1024)


# --- RAM: macOS — sysctl for total, vm_stat pages for available ------------


def _ram_from_macos() -> tuple[Optional[int], Optional[int]]:
    import shutil

    from coordinator_core.win_portability import no_console_creationflags

    if not shutil.which("sysctl") or not shutil.which("vm_stat"):
        return None, None
    try:
        total_bytes_out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5,
            **no_console_creationflags(),
        )
        pagesize_out = subprocess.run(
            ["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, timeout=5,
            **no_console_creationflags(),
        )
        stats_out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if total_bytes_out.returncode != 0:
        return None, None
    total_bytes_s = total_bytes_out.stdout.strip()
    pagesize_s = pagesize_out.stdout.strip() if pagesize_out.returncode == 0 else ""
    pagesize = int(pagesize_s) if pagesize_s.isdigit() else 4096
    stats = stats_out.stdout if stats_out.returncode == 0 else ""

    def _pages(label: str) -> Optional[int]:
        m = re.search(rf"^{label}:\s*(\d+)\.", stats, re.MULTILINE)
        return int(m.group(1)) if m else None

    free = _pages("Pages free")
    if free is None:
        return None, None
    inactive = _pages("Pages inactive") or 0
    spec = _pages("Pages speculative") or 0
    avail_pages = free + inactive + spec
    # Divide before multiplying: avail_pages * pagesize can reach ~32e9 on a
    # large-RAM box; (pagesize // 1024) is exact for all real Apple page
    # sizes (4096, 16384).
    avail_mb = (avail_pages // 1024) * (pagesize // 1024)
    total_mb = int(total_bytes_s) // 1024 // 1024 if total_bytes_s.isdigit() else None
    return avail_mb, total_mb


# --- VRAM: NVIDIA only, any platform — sum free/total across GPUs ----------


def _vram_from_nvidia() -> tuple[Optional[int], Optional[int]]:
    import shutil

    if not shutil.which("nvidia-smi"):
        return None, None
    # Bounded: a wedged NVIDIA driver makes nvidia-smi hang indefinitely
    # (known issue).
    out = _bounded(
        3,
        [
            "nvidia-smi",
            "--query-gpu=memory.free,memory.total",
            "--format=csv,noheader,nounits",
        ],
    )
    if out is None:
        return None, None
    free_sum = 0
    total_sum = 0
    saw_free = False
    saw_total = False
    for line in out.replace("\r", "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            continue
        f, t = parts
        if f.isdigit():
            free_sum += int(f)
            saw_free = True
        if t.isdigit():
            total_sum += int(t)
            saw_total = True
    if not saw_free:
        return None, None
    # Only report a total if at least one GPU gave a numeric one — never a
    # misleading 0.
    return free_sum, (total_sum if saw_total else None)


def _fmt(v: Optional[int]) -> str:
    return "unknown" if v is None else str(v)


def main(argv: list[str]) -> int:
    _bootstrap_engine()

    args = argv[1:]
    human = False
    if args:
        if args == ["--human"]:
            human = True
        else:
            print("usage: probe-memory-headroom.py [--human]", file=sys.stderr)
            return 2

    system = platform.system()
    ram_avail: Optional[int] = None
    ram_total: Optional[int] = None
    if system == "Linux":
        ram_avail, ram_total = _ram_from_proc()
    elif system == "Darwin":
        ram_avail, ram_total = _ram_from_macos()
    elif system == "Windows":
        ram_avail, ram_total = _ram_from_windows()

    vram_free, vram_total = _vram_from_nvidia()

    if human:
        parts = []
        if ram_avail is not None:
            parts.append(f"RAM free {_fmt_mb(ram_avail)}")
        if vram_free is not None:
            parts.append(f"VRAM free {_fmt_mb(vram_free)}")
        if not parts:
            print("memory headroom: unavailable on this platform")
        else:
            print(f"memory headroom: {', '.join(parts)}")
        return 0

    print(f"ram_available_mb={_fmt(ram_avail)}")
    print(f"ram_total_mb={_fmt(ram_total)}")
    print(f"vram_free_mb={_fmt(vram_free)}")
    print(f"vram_total_mb={_fmt(vram_total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
