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
    ram_available_mb=<int|unknown>   # host_sampler.avail_mb: MemAvailable (Linux) / ullAvailPhys (Win) / memorystatus_level (mac)
    ram_total_mb=<int|unknown>
    vram_free_mb=<int|unknown>       # summed across NVIDIA GPUs; unknown if no nvidia-smi
    vram_total_mb=<int|unknown>

Usage:
    python3 coordinator/bin/probe-memory-headroom.py            # key=value lines (machine-parseable)
    python3 coordinator/bin/probe-memory-headroom.py --human    # one human-readable sentence

Platform coverage: RAM through coordinator_core.telemetry.host_sampler.avail_mb (spawn-free
on Linux, Windows and macOS). VRAM is NVIDIA-only (nvidia-smi) on any platform; AMD/Intel GPUs
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

import subprocess
import sys
from typing import Optional


def _bootstrap_engine() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)


def _bounded(secs: float, cmd: list[str]) -> Optional[str]:
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
    if mb >= 1024:
        return f"~{mb // 1024} GB"
    return f"~{mb} MB"


def _vram_from_nvidia() -> tuple[Optional[int], Optional[int]]:
    import shutil

    if not shutil.which("nvidia-smi"):
        return None, None
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

    from coordinator_core.telemetry import host_sampler

    ram_avail, ram_total = host_sampler.avail_mb()

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
