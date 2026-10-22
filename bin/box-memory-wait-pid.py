#!/usr/bin/env python3
"""box-memory-wait-pid.py PID [--interval S] [--timeout S] -- wait on a PID, print one line.

Output is exactly one line on stdout:
  EXITED pid=N code=<c|?> elapsed=<s>s   exit 0
  TIMEOUT pid=N                          exit 1
  NO-SUCH-PID pid=N                      exit 1

`code` is `?` when the exit status is unavailable (a non-child process, or the POSIX poll
branch). Runs on every host and consumes nothing from the box-memory library.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Callable, Optional, Tuple

# A waiter returns (state, code): state is "exited" | "timeout" | "nopid".
Waiter = Callable[[int, float, Optional[float]], Tuple[str, Optional[int]]]


def psutil_waiter(pid: int, interval: float, timeout: Optional[float]) -> Tuple[str, Optional[int]]:
    import psutil

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return "nopid", None
    try:
        code = proc.wait(timeout)
    except psutil.TimeoutExpired:
        return "timeout", None
    except psutil.NoSuchProcess:
        return "exited", None
    return "exited", code


def poll_waiter(
    pid: int,
    interval: float,
    timeout: Optional[float],
    *,
    kill: Callable[[int, int], None] = os.kill,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Tuple[str, Optional[int]]:
    """POSIX liveness poll via signal 0; the exit code is unknowable here."""
    deadline = None if timeout is None else clock() + timeout
    first = True
    while True:
        try:
            kill(pid, 0)
        except ProcessLookupError:
            return ("nopid" if first else "exited"), None
        except PermissionError:
            pass
        first = False
        if deadline is not None and clock() >= deadline:
            return "timeout", None
        sleep(interval)


def default_waiter() -> Waiter:
    try:
        import psutil  # noqa: F401
    except ImportError:
        if os.name == "nt":
            # On Windows os.kill(pid, 0) calls TerminateProcess: the poll branch would kill its target.
            raise SystemExit("box-memory-wait-pid: psutil is required on Windows (pip install psutil)")
        return poll_waiter
    return psutil_waiter


def run(
    pid: int,
    interval: float,
    timeout: Optional[float],
    waiter: Optional[Waiter] = None,
    clock: Callable[[], float] = time.monotonic,
) -> Tuple[str, int]:
    """Return (the single output line, exit status)."""
    waiter = waiter or default_waiter()
    start = clock()
    state, code = waiter(pid, interval, timeout)
    if state == "nopid":
        return f"NO-SUCH-PID pid={pid}", 1
    if state == "timeout":
        return f"TIMEOUT pid={pid}", 1
    elapsed = clock() - start
    shown = "?" if code is None else str(code)
    return f"EXITED pid={pid} code={shown} elapsed={elapsed:.1f}s", 0


def main(argv: Optional[list] = None, waiter: Optional[Waiter] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="box-memory-wait-pid.py",
        description="Wait on a PID and print one exit line.",
    )
    parser.add_argument("pid", type=int)
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds (default 1)")
    parser.add_argument("--timeout", type=float, default=None, help="give up after S seconds")
    args = parser.parse_args(argv)
    if args.pid <= 0:
        # kill(0, 0) / kill(-1, 0) address process groups and always succeed: the poll would never end.
        parser.error("pid must be a positive integer")
    line, status = run(args.pid, max(args.interval, 0.01), args.timeout, waiter)
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
