"""Orchestration of the on-demand Windows file-cache trim.

`run` drives a FileCacheHost through the ordered refusals, then either rehearses (dry-run, the
default) or performs (`--apply`) one `SetSystemFileCacheSize(-1, -1, 0)` trim and reports the
before/after memory counters. The module imports on every OS; the Win32 host is built by `main`
only after the platform check.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from file_cache_contract import (
    CacheLimits,
    CounterError,
    ExitCode,
    FileCacheHost,
    MemorySnapshot,
    PrivilegeError,
    TrimError,
)

# SetSystemFileCacheSize returns before the memory manager has finished moving pages to the
# standby list; counters read immediately afterwards show a partial move.
SETTLE_SECONDS = 2.0

_GIB = 1024**3

# The PM-installed, trigger-less, on-demand task; its fixed action trims the cache and appends to
# trim.log. This module only fires it; it never creates or schedules a task.
TRIM_TASK = "BoxCacheTrim"
LOG_WAIT_SECONDS = 5.0


def trim_log_path() -> Path:
    root = os.environ.get("ProgramData") or (os.environ.get("SystemDrive", "C:") + os.sep + "ProgramData")
    return Path(root) / "BoxMemory" / "trim.log"


def _log_tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return lines[-1].strip() if lines else ""


def fire_box_cache_trim(
    run: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
    log_path: Optional[Path] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[str]:
    """Fire the BoxCacheTrim task. None when the task is absent or would not start (caller falls
    back); else the trim.log tail line, waiting up to LOG_WAIT_SECONDS for the run to append one
    ("" when the log is unreadable)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def _schtasks(verb: str):
        try:
            return run(["schtasks", f"/{verb}", "/tn", TRIM_TASK], capture_output=True, text=True,
                       timeout=15, creationflags=flags)
        except (OSError, subprocess.SubprocessError):
            return None

    query = _schtasks("query")
    if query is None or query.returncode != 0:
        return None
    path = log_path if log_path is not None else trim_log_path()
    before = _log_tail(path)
    fired = _schtasks("run")
    if fired is None or fired.returncode != 0:
        return None
    waited = 0.0
    while waited < LOG_WAIT_SECONDS:
        tail = _log_tail(path)
        if tail and tail != before:
            return tail
        sleep(0.25)
        waited += 0.25
    return _log_tail(path)


def _gib(n: int) -> str:
    return f"{n / _GIB:.2f} GiB"


def project_after(before: MemorySnapshot) -> MemorySnapshot:
    """What would a trim move, at most? The whole cache working set leaves CacheBytes; standby and
    available each gain up to that much (modified pages go to the modified list instead)."""
    return dataclasses.replace(
        before,
        cache_bytes=0,
        standby_bytes=before.standby_bytes + before.cache_bytes,
        available_bytes=before.available_bytes + before.cache_bytes,
    )


def _block(title: str, snap: MemorySnapshot, upper_bound: bool = False) -> str:
    note = " (upper bound)" if upper_bound else ""
    return (
        f"{title}\n"
        f"  CacheBytes: {_gib(snap.cache_bytes)}{' (floor)' if upper_bound else ''}\n"
        f"  standby:    {_gib(snap.standby_bytes)}{note}\n"
        f"  available:  {_gib(snap.available_bytes)}{note}"
    )


def _delta_block(before: MemorySnapshot, after: MemorySnapshot) -> str:
    def d(a: int, b: int) -> str:
        diff = b - a
        sign = "+" if diff >= 0 else "-"
        return f"{sign}{abs(diff) / _GIB:.2f} GiB"

    return (
        "delta\n"
        f"  CacheBytes: {d(before.cache_bytes, after.cache_bytes)}\n"
        f"  standby:    {d(before.standby_bytes, after.standby_bytes)}\n"
        f"  available:  {d(before.available_bytes, after.available_bytes)}"
    )


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _read(host: FileCacheHost) -> tuple[MemorySnapshot, CacheLimits]:
    return host.read_memory(), host.read_limits()


def _operate(host: FileCacheHost, apply: bool, sleep: Callable[[float], None]) -> int:
    try:
        before, before_limits = _read(host)
    except CounterError as exc:
        _err(f"could not read memory counters: {exc}")
        return ExitCode.COUNTERS_UNAVAILABLE

    if before_limits.hard_max_enabled:
        print(
            "WARNING: a hard maximum file-cache cap is already set on this system. This tool did "
            "not set it and will not change it; caps reset at reboot."
        )

    print(_block("before", before))

    if not apply:
        print(_block("after (projected, nothing trimmed)", project_after(before), upper_bound=True))
        print("no trim performed (dry-run; pass --apply to trim)")
        return ExitCode.OK

    try:
        host.trim_working_set()
    except TrimError as exc:
        _err(f"trim failed: {exc}")
        return ExitCode.TRIM_FAILED

    sleep(SETTLE_SECONDS)

    try:
        after, after_limits = _read(host)
    except CounterError as exc:
        _err(f"the trim DID run, but the memory counters could not be re-read: {exc}")
        return ExitCode.COUNTERS_UNAVAILABLE

    print(_block("after", after))
    print(_delta_block(before, after))

    if after_limits.flags != before_limits.flags:
        _err(
            f"CAP CHANGED: file-cache limit flags went from {before_limits.flags:#x} to "
            f"{after_limits.flags:#x} across the trim. The tool never sets flags; inspect the "
            "system file-cache limits."
        )
        return ExitCode.CAP_CHANGED
    return ExitCode.OK


def run(
    argv: list[str],
    host: FileCacheHost | None,
    platform: str,
    sleep: Callable[[float], None] = time.sleep,
    fire: Optional[Callable[[], Optional[str]]] = None,
) -> int:
    """Run the trim CLI against `host`; returns the process exit code.

    Order, each a hard stop: platform, elevation, privilege, counters. `host` may be None only
    when `platform` is not win32. Unelevated with `--apply`, a present BoxCacheTrim task is fired
    instead of failing; `fire` returns None when it is absent.
    """
    parser = argparse.ArgumentParser(
        prog="trim-file-cache.py",
        description="Trim the Windows system file-cache working set to the standby list. "
        "Dry-run by default.",
    )
    parser.add_argument("--apply", action="store_true", help="perform the trim (default: dry-run)")
    args = parser.parse_args(argv)

    if platform != "win32":
        _err("trim-file-cache is Windows-only (it wraps SetSystemFileCacheSize).")
        return ExitCode.NOT_WINDOWS

    if host is None:
        raise TypeError("host is required on win32")
    if not host.is_elevated():
        if args.apply:
            tail = (fire or fire_box_cache_trim)()
            if tail is not None:
                print(f"fired scheduled task {TRIM_TASK}" + (f": {tail}" if tail else ""))
                return ExitCode.OK
        _err("not elevated: run from an elevated (Administrator) shell.")
        return ExitCode.NOT_ELEVATED

    cm = host.quota_privilege()
    try:
        cm.__enter__()
    except PrivilegeError as exc:
        _err(f"could not enable SeIncreaseQuotaPrivilege: {exc}")
        return ExitCode.PRIVILEGE_UNAVAILABLE

    try:
        return _operate(host, args.apply, sleep)
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception as exc:  # reported, never masks the exit code already chosen
            _err(f"failed to restore the prior privilege state: {exc}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if sys.platform != "win32":
        return run(argv, None, sys.platform)
    lib_dir = str(Path(__file__).resolve().parent)
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from file_cache_win32 import Win32FileCacheHost

    return run(argv, Win32FileCacheHost(), sys.platform)
