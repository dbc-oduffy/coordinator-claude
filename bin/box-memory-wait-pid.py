#!/usr/bin/env python3
"""box-memory-wait-pid.py PID [--interval S] [--timeout S] [--result PATH] -- wait on a PID, print one line.

Output is exactly one line on stdout:
  EXITED pid=N code=<c|?> elapsed=<s>s   exit 0
  TIMEOUT pid=N                          exit 1
  NO-SUCH-PID pid=N                      exit 1
  (cannot leave the session's job)       exit 5, one remedy line on stderr

Two halves. Run from a Claude Code session, the waiter relaunches itself detached with --result
and this session half tails the result file with the same --interval and --timeout: its exit is
the wake, and a reaped session half loses nothing because the detached half records the line
(tmp + replace) and exits. A result file already holding an EXITED line is printed without
waiting, so a relaunch after a reap reads the recorded exit; a recorded TIMEOUT or NO-SUCH-PID
is stale, deleted, and the wait runs again. Outside a session, or as the detached half, the wait
runs inline. The detached half carries the operator's --timeout; with none given it waits
until the pid exits.

`code` is `?` when the exit status is unavailable (a non-child process, or the POSIX poll
branch). Runs on every host and consumes nothing from the box-memory library.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
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


def _git_toplevel(start: Path) -> Optional[Path]:
    cur = start.resolve()
    for cand in (cur, *cur.parents):
        if (cand / ".git").exists():
            return cand
    return None


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or str(Path.home())) / ".coordinator-claude-settings"


def default_result_path(pid: int) -> Path:
    """scratch/ of the cwd's git toplevel, else of the settings home."""
    root = _git_toplevel(Path.cwd()) or _settings_home()
    return root / "scratch" / f"wait-pid-{pid}.result"


def status_of(line: str) -> int:
    return 0 if line.startswith("EXITED ") else 1


def read_result(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_result(path: Path, line: str) -> None:
    """Atomic: a reader sees the whole line or no file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(line + "\n", encoding="utf-8")
    os.replace(tmp, path)


def tail_result(
    path: Path,
    pid: int,
    interval: float,
    timeout: Optional[float],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Tuple[str, int]:
    """Poll for the detached waiter's result line; TIMEOUT when none lands by the deadline."""
    deadline = None if timeout is None else clock() + timeout
    while True:
        line = read_result(path)
        if line is not None:
            return line, status_of(line)
        if deadline is not None and clock() >= deadline:
            return f"TIMEOUT pid={pid}", 1
        sleep(interval)


def _default_ensure(prog: str, argv: list, log: Path) -> Optional[int]:
    lib = str(Path(__file__).resolve().parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import session_detach

    return session_detach.ensure_detached(prog, argv, log, out=sys.stderr)


def main(
    argv: Optional[list] = None,
    waiter: Optional[Waiter] = None,
    *,
    ensure: Optional[Callable[[str, list, Path], Optional[int]]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    parser = argparse.ArgumentParser(
        prog="box-memory-wait-pid.py",
        description="Wait on a PID and print one exit line.",
    )
    parser.add_argument("pid", type=int)
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds (default 1)")
    parser.add_argument("--timeout", type=float, default=None, help="give up after S seconds")
    parser.add_argument("--result", type=Path, default=None, help="result file (default scratch/wait-pid-<pid>.result)")
    args = parser.parse_args(argv)
    if args.pid <= 0:
        # kill(0, 0) / kill(-1, 0) address process groups and always succeed: the poll would never end.
        parser.error("pid must be a positive integer")
    interval = max(args.interval, 0.01)
    result = args.result or default_result_path(args.pid)

    recorded = read_result(result)
    if recorded is not None:
        if recorded.startswith("EXITED "):
            print(recorded)
            return 0
        # TIMEOUT / NO-SUCH-PID describe an earlier wait, not this one; the session half's tail
        # would otherwise read it as the new result.
        result.unlink(missing_ok=True)

    # The marker means this process is already the detached half: skip the session probe.
    if ensure is not None or not os.environ.get("COORDINATOR_GUARD_DETACHED"):
        relaunch = list(sys.argv[1:] if argv is None else argv)
        if args.result is None:
            relaunch += ["--result", str(result)]
        rc = (ensure or _default_ensure)("box-memory-wait-pid", relaunch, result.with_name(result.name + ".log"))
        if rc is not None:
            if rc != 0:
                return rc
            line, status = tail_result(result, args.pid, interval, args.timeout, sleep, clock)
            print(line)
            return status

    line, status = run(args.pid, interval, args.timeout, waiter, clock)
    if args.result is not None:
        write_result(result, line)
    print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
