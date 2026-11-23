#!/usr/bin/env python3
"""peak-cores.py [--window S] [--interval S] [--json] -- logical core count and peak cores in use.

Samples whole-box CPU time counters over a bounded window (default 3.0 s every 0.25 s) and reports
the logical core count plus the peak cores in use: the largest busy fraction between two adjacent
samples times the logical core count. Stdlib only; Windows (GetSystemTimes), Linux (/proc/stat)
and macOS (host_statistics) are read in-process, so the script spawns no child process and its own
CPU time is the sampling loop's few reads.

Human output is two lines (`logical_cores`, `peak_cores`); `--json` prints one object with
`logical_cores`, `peak_cores`, `peak_fraction`, `samples`, `window_s`, `interval_s`.
Exit 0 on success; exit 6 when this host's CPU counters cannot be read (the reason is on stderr).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Callable, Optional

PROG = "peak-cores"
EXIT_UNREADABLE = 6
DEFAULT_WINDOW_S = 3.0
DEFAULT_INTERVAL_S = 0.25

# A sampler returns cumulative (busy_ticks, total_ticks) across all logical cores.
Sampler = Callable[[], "tuple[int, int]"]


def _linux_sampler() -> "tuple[int, int]":
    with open("/proc/stat", "r", encoding="ascii") as fh:
        fields = fh.readline().split()
    if not fields or fields[0] != "cpu":
        raise OSError("/proc/stat has no aggregate cpu line")
    vals = [int(x) for x in fields[1:9]]
    vals += [0] * (8 - len(vals))
    total = sum(vals)
    idle = vals[3] + vals[4]  # idle + iowait
    return total - idle, total


def _windows_sampler() -> "tuple[int, int]":
    import ctypes
    from ctypes import wintypes

    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError("GetSystemTimes failed")

    def _v(ft) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    # Kernel time includes idle time.
    total = _v(kernel) + _v(user)
    return total - _v(idle), total


def _macos_sampler() -> "tuple[int, int]":
    import ctypes
    import ctypes.util

    lib = ctypes.CDLL(ctypes.util.find_library("System") or "/usr/lib/libSystem.dylib")
    lib.mach_host_self.restype = ctypes.c_uint
    count = ctypes.c_uint(4)
    ticks = (ctypes.c_uint * 4)()
    # HOST_CPU_LOAD_INFO = 3; ticks are user, system, idle, nice.
    rc = lib.host_statistics(lib.mach_host_self(), 3, ticks, ctypes.byref(count))
    if rc != 0:
        raise OSError(f"host_statistics returned {rc}")
    total = sum(ticks)
    return total - ticks[2], total


def default_sampler() -> Sampler:
    """Return this host's counter reader; raises OSError when the platform has none."""
    if sys.platform == "win32":
        return _windows_sampler
    if sys.platform == "darwin":
        return _macos_sampler
    if sys.platform.startswith("linux"):
        return _linux_sampler
    raise OSError(f"unsupported platform: {sys.platform}")


def measure(
    sampler: Sampler,
    logical_cores: int,
    window_s: float = DEFAULT_WINDOW_S,
    interval_s: float = DEFAULT_INTERVAL_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Sample until `window_s` elapses; peak cores = max adjacent-sample busy fraction x cores."""
    prev = sampler()
    start = clock()
    peak_fraction = 0.0
    samples = 1
    while clock() - start < window_s:
        sleep(interval_s)
        cur = sampler()
        samples += 1
        d_total = cur[1] - prev[1]
        d_busy = cur[0] - prev[0]
        if d_total > 0:
            peak_fraction = max(peak_fraction, min(1.0, max(0.0, d_busy / d_total)))
        prev = cur
    return {
        "logical_cores": logical_cores,
        "peak_cores": round(peak_fraction * logical_cores, 2),
        "peak_fraction": round(peak_fraction, 4),
        "samples": samples,
        "window_s": window_s,
        "interval_s": interval_s,
    }


def _positive(text: str) -> float:
    val = float(text)
    if val <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return val


def main(argv: Optional[list] = None, sampler: Optional[Sampler] = None) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="Report logical cores and peak cores in use.", allow_abbrev=False)
    parser.add_argument("--window", type=_positive, default=DEFAULT_WINDOW_S, help=f"sample window in seconds (default {DEFAULT_WINDOW_S})")
    parser.add_argument("--interval", type=_positive, default=DEFAULT_INTERVAL_S, help=f"seconds between samples (default {DEFAULT_INTERVAL_S})")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args(argv)
    try:
        read = sampler or default_sampler()
        result = measure(read, os.cpu_count() or 1, args.window, args.interval)
    except OSError as exc:
        print(f"{PROG}: cannot read CPU counters: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    if args.json:
        print(json.dumps(result))
    else:
        print(f"logical_cores: {result['logical_cores']}")
        print(f"peak_cores: {result['peak_cores']} (over {result['window_s']}s, {result['samples']} samples)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
