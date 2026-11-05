"""Orchestration of the on-demand Windows file-cache trim.

`run` drives a FileCacheHost through the ordered refusals, then either rehearses (dry-run, the
default) or performs (`--apply`) one `SetSystemFileCacheSize(-1, -1, 0)` trim and reports the
before/after memory counters. The module imports on every OS; the Win32 host is built by `main`
only after the platform check.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import io
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
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

# The PM-installed, trigger-less, on-demand task; its fixed action trims the cache and appends a
# three-line record to trim.log (UTC timestamp, "trimmed" or "failed: ...", the numbers line). The
# action cannot carry a run nonce without re-registration, so a result is this run's only when its
# record timestamp is at or after the instant this module fired the task. This module only fires
# the task; it never creates, stops or schedules one.
TRIM_TASK = "BoxCacheTrim"
TASK_WAIT_SECONDS = 30.0
RUNNING_EXTENSION_SECONDS = 120.0
GOVERNOR_WAIT_SECONDS = 10.0
POLL_SECONDS = 1.0
STATE_POLL_SECONDS = 2.0
IDLE_POLLS_BEFORE_FAIL = 2

# A drop smaller than this share of the before cache (and under MIN_DROP_BYTES) reads as no drop;
# a before cache under NOOP_FLOOR_BYTES has nothing worth trimming.
DROP_FRACTION = 0.10
MIN_DROP_BYTES = _GIB
NOOP_FLOOR_BYTES = _GIB
REFILL_BYTES = _GIB

_TS_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}[:][0-9]{2}[:][0-9]{2}([.][0-9]+)?Z$")


def trim_log_path() -> Path:
    root = os.environ.get("ProgramData") or (os.environ.get("SystemDrive", "C:") + os.sep + "ProgramData")
    return Path(root) / "BoxMemory" / "trim.log"


@dataclasses.dataclass(frozen=True)
class TrimFire:
    """Outcome of one task fire: `ok` only when a result record written after the fire says the
    trim ran; `detail` is that record's numbers line, or the reason it is not ok."""

    ok: bool
    detail: str
    waited: float
    running: bool = False

    def line(self) -> str:
        if self.ok:
            return f"{self.detail} (this run's result, waited {self.waited:.1f}s)"
        return f"NOT TRIMMED: {self.detail}"


@dataclasses.dataclass(frozen=True)
class _TaskState:
    running: bool
    status: str
    last_result: str


def _parse_ts(text: str) -> Optional[datetime]:
    if not _TS_RE.match(text):
        return None
    try:
        return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _last_record(path: Path) -> Optional[tuple[datetime, list[str]]]:
    """The newest complete trim.log record: (timestamp, body lines). A record whose body is still
    being written (timestamp line only, or "trimmed" without its numbers line) is None."""
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return None
    lines = [ln for ln in lines if ln]
    for idx in range(len(lines) - 1, -1, -1):
        stamp = _parse_ts(lines[idx])
        if stamp is None:
            continue
        body = lines[idx + 1:]
        if len(body) >= 2 or (body and body[0].startswith("failed")):
            return stamp, body
        return None
    return None


def _task_state(run: Callable[..., "subprocess.CompletedProcess"]) -> Optional[_TaskState]:
    """BoxCacheTrim's Status and Last Result via one `schtasks /query /v /fo csv`; None when the
    task is absent or the query fails. Columns are positional (Status 4th, Last Result 7th)."""
    try:
        proc = run(["schtasks", "/query", "/tn", TRIM_TASK, "/v", "/fo", "csv", "/nh"],
                   capture_output=True, text=True, timeout=15,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    rows = [r for r in csv.reader(io.StringIO(getattr(proc, "stdout", "") or "")) if r]
    row = rows[-1] if rows else []
    status = row[3].strip() if len(row) > 3 else ""
    last = row[6].strip() if len(row) > 6 else ""
    return _TaskState(status.lower() == "running", status, last)


def fire_trim_task(
    run: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
    log_path: Optional[Path] = None,
    sleep: Callable[[float], None] = time.sleep,
    live_fn: Optional[Callable[[], bool]] = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sample: Optional[Callable[[], None]] = None,
    wait_seconds: float = TASK_WAIT_SECONDS,
    extend_while_running: float = RUNNING_EXTENSION_SECONDS,
) -> Optional[TrimFire]:
    """Fire BoxCacheTrim and report only a result written after the fire. None when the task is
    absent or would not start (caller falls back); else a TrimFire, never the old log tail: a task
    still Running (0x41301), a refused fire (0x800710E0), a task that left Running without a
    record, and a bounded wait that expires are all `ok=False`. `sample` is called once per poll
    while waiting. An automatic caller passes `live_fn`: None, with nothing spawned, unless it
    reports a live group-em (a raising probe reads as not live); no `live_fn` is a manual trim.
    Trap: past `wait_seconds` a task still Running keeps being waited on for up to
    `extend_while_running` more; if it is still Running then, the result has `running=True` so the
    caller re-measures instead of judging the trim."""
    if live_fn is not None:
        try:
            if not live_fn():
                return None
        except Exception:
            return None
    path = log_path if log_path is not None else trim_log_path()
    state = _task_state(run)
    if state is None:
        return None
    waited = 0.0
    while state.running and waited < wait_seconds:
        sleep(STATE_POLL_SECONDS)
        waited += STATE_POLL_SECONDS
        state = _task_state(run) or state
    if state.running:
        return TrimFire(False, f"{TRIM_TASK} still Running (0x41301) after {waited:.0f}s; not fired", waited, running=True)

    fired_at = now()
    try:
        fired = run(["schtasks", "/run", "/tn", TRIM_TASK], capture_output=True, text=True,
                    timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if fired.returncode != 0:
        said = f"{getattr(fired, 'stdout', '')} {getattr(fired, 'stderr', '')}".lower()
        if "running" in said or "800710e0" in said:
            return TrimFire(False, f"{TRIM_TASK} refused the fire: already running (0x800710E0)", waited, running=True)
        return None

    elapsed = 0.0
    since_state = 0.0
    idle_polls = 0
    state = None
    while True:
        record = _last_record(path)
        if record is not None and record[0] >= fired_at:
            body = record[1]
            if body[0] == "trimmed" and len(body) >= 2:
                return TrimFire(True, body[1], waited + elapsed)
            return TrimFire(False, f"{TRIM_TASK} reported {' '.join(body)}", waited + elapsed)
        if state is not None and not state.running and idle_polls >= IDLE_POLLS_BEFORE_FAIL:
            return TrimFire(
                False,
                f"{TRIM_TASK} left Running with no result record from this run "
                f"(Last Result {state.last_result or 'unknown'})",
                waited + elapsed,
            )
        if elapsed >= wait_seconds and not (
            state is not None and state.running and elapsed < wait_seconds + extend_while_running
        ):
            break
        sleep(POLL_SECONDS)
        elapsed += POLL_SECONDS
        if sample is not None:
            sample()
        since_state += POLL_SECONDS
        if since_state >= STATE_POLL_SECONDS:
            since_state = 0.0
            state = _task_state(run) or state
            idle_polls = 0 if state is None or state.running else idle_polls + 1

    state = _task_state(run) or state
    shown = f"{state.status or 'unknown'}, Last Result {state.last_result or 'unknown'}" if state else "unknown"
    return TrimFire(
        False,
        f"no result record from this run after {elapsed:.0f}s wait (task {shown})",
        waited + elapsed,
        running=bool(state and state.running),
    )


def fire_box_cache_trim(
    run: Callable[..., "subprocess.CompletedProcess"] = subprocess.run,
    log_path: Optional[Path] = None,
    sleep: Callable[[float], None] = time.sleep,
    live_fn: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """`fire_trim_task` rendered as one line for the governor: None when the task is absent, would
    not start, or `live_fn` reports no live group-em; else this run's result line, or a line
    starting `NOT TRIMMED:` naming why no result from this run arrived. Trap: the governor's loop
    blocks on this call, so its waits are bounded at GOVERNOR_WAIT_SECONDS, not the manual 30s."""
    fired = fire_trim_task(run, log_path, sleep, live_fn, wait_seconds=GOVERNOR_WAIT_SECONDS,
                           extend_while_running=0.0)
    return None if fired is None else fired.line()


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


def _fire_with_sample(sample: Callable[[], None]) -> Optional[TrimFire]:
    return fire_trim_task(sample=sample)


def _fmt_move(label: str, before: int, after: int) -> str:
    return f"{label} {_gib(before)} -> {_gib(after)}"


def _judge_running(
    host: FileCacheHost,
    before: MemorySnapshot,
    seen: list[int],
    sample: Callable[[], None],
    fired: TrimFire,
    need: int,
) -> int:
    """The task was still Running when the bounded wait ended: judge by re-measured memory, never
    by the missing record. A drop is success; no drop yet is UNVERIFIED, not 'NOT effective'."""
    sample()
    try:
        after = host.read_memory()
    except CounterError as exc:
        _err(f"{TRIM_TASK} still Running after {fired.waited:.0f}s and the memory counters could "
             f"not be re-read: {exc}")
        return ExitCode.COUNTERS_UNAVAILABLE
    trough = min([*seen, after.cache_bytes])
    numbers = (f"{_fmt_move('cache', before.cache_bytes, after.cache_bytes)}, "
               f"{_fmt_move('available', before.available_bytes, after.available_bytes)}")
    if before.cache_bytes - trough >= need:
        print(f"{TRIM_TASK} still Running after {fired.waited:.0f}s but the cache dropped "
              f"(low {_gib(trough)}): {numbers}")
        print(_block("before", before))
        print(_block("after", after))
        return ExitCode.OK
    _err(f"trim UNVERIFIED: {TRIM_TASK} still Running after {fired.waited:.0f}s, cache not dropped "
         f"yet: {numbers} (low seen {_gib(trough)}); re-measure with box-memory-snapshot")
    return ExitCode.TRIM_FAILED


def _apply_via_task(
    host: FileCacheHost,
    fire: Callable[[Callable[[], None]], Optional[TrimFire]],
    sleep: Callable[[float], None],
) -> Optional[int]:
    """Unelevated `--apply`: measure, fire the task, wait for this run's result, measure again.

    None when the task is absent (caller reports the elevation refusal). Any other outcome is an
    exit code: OK only when the measured cache working set fell, else TRIM_FAILED naming the
    before/after cache and available-memory numbers. The cache trough seen while waiting tells a
    late drop that a concurrent reader refilled apart from a trim that never took."""
    try:
        before = host.read_memory()
    except CounterError as exc:
        _err(f"could not read memory counters: {exc}")
        return ExitCode.COUNTERS_UNAVAILABLE

    seen: list[int] = []

    def sample() -> None:
        try:
            seen.append(host.read_memory().cache_bytes)
        except CounterError:
            pass

    fired = fire(sample)
    if fired is None:
        return None
    need = max(MIN_DROP_BYTES, int(before.cache_bytes * DROP_FRACTION))
    if not fired.ok and fired.running:
        return _judge_running(host, before, seen, sample, fired, need)
    if not fired.ok:
        _err(f"trim NOT effective: {fired.detail}; before cache {_gib(before.cache_bytes)}, "
             f"available {_gib(before.available_bytes)}, no after-read (waited {fired.waited:.1f}s)")
        return ExitCode.TRIM_FAILED

    sample()
    sleep(SETTLE_SECONDS)
    try:
        after = host.read_memory()
    except CounterError as exc:
        _err(f"{TRIM_TASK} reported this run's result ({fired.detail}) but the memory counters could "
             f"not be re-read: {exc}")
        return ExitCode.COUNTERS_UNAVAILABLE

    trough = min([*seen, after.cache_bytes])
    print(f"fired scheduled task {TRIM_TASK}: {fired.detail}")
    print(f"waited {fired.waited:.1f}s for this run's result")
    print(_block("before", before))
    print(_block("after", after))
    print(_delta_block(before, after))

    numbers = (f"{_fmt_move('cache', before.cache_bytes, after.cache_bytes)}, "
               f"{_fmt_move('available', before.available_bytes, after.available_bytes)}")
    refilled = after.cache_bytes - trough
    if before.cache_bytes < NOOP_FLOOR_BYTES:
        print(f"nothing to trim: cache already under {_gib(NOOP_FLOOR_BYTES)} ({numbers})")
        return ExitCode.OK
    if before.cache_bytes - after.cache_bytes >= need:
        if refilled >= REFILL_BYTES:
            print(f"note: cache refilled {_gib(refilled)} after its low of {_gib(trough)} "
                  "(a concurrent reader is re-reading files)")
        return ExitCode.OK
    if before.cache_bytes - trough >= need:
        _err(f"cache dropped to {_gib(trough)} then refilled {_gib(refilled)} by a concurrent reader; "
             f"after-read did not hold the drop: {numbers}")
    else:
        _err(f"{TRIM_TASK} reported a result from this run but the cache did not drop: {numbers} "
             f"(low seen {_gib(trough)}; waited {fired.waited:.1f}s)")
    return ExitCode.TRIM_FAILED


def run(
    argv: list[str],
    host: FileCacheHost | None,
    platform: str,
    sleep: Callable[[float], None] = time.sleep,
    fire: Optional[Callable[[Callable[[], None]], Optional[TrimFire]]] = None,
) -> int:
    """Run the trim CLI against `host`; returns the process exit code.

    Order, each a hard stop: platform, elevation, privilege, counters. `host` may be None only
    when `platform` is not win32. Unelevated with `--apply`, a present BoxCacheTrim task is fired
    and the cache measured around it; `fire(sample)` returns None when the task is absent.
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
            code = _apply_via_task(host, fire or _fire_with_sample, sleep)
            if code is not None:
                return code
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
