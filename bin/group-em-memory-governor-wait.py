"""group-em-memory-governor-wait — the Group EM's one-shot wake on the memory governor's log.

The governor runs as a session-long background shell appending to a log; this waiter is a second
background shell whose exit is the wake. It starts at the log's current end, so lines the Group EM
already acted on never re-wake it, prints the first new complete line, and exits 0. After acting,
relaunch the waiter only, never the governor: a governor restart would drop the trees it holds
paused.

Usage: group-em-memory-governor-wait.py <log> [--interval SECONDS]

On start, before tailing, it thaws the pids a hard-killed governor left recorded in its pidfile.
The pidfile names its owning governor (pid and start time): a live owner keeps its pause, so
nothing is signalled and the file is kept; a dead owner's recorded pids are thawed only when their
start times still match. A legacy or malformed file thaws nothing and is cleared.
A missing log is waited for, not an error. A log that shrinks (rotated or truncated) restarts the
read at 0. Never filter the output: the governor prints only action lines.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path
from typing import Callable, Optional


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def wait_for_line(path: Path, interval: float = 2.0, sleep: Callable[[float], None] = time.sleep,
                  max_polls: Optional[int] = None) -> Optional[str]:
    offset = _size(path)
    pending = b""
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        size = _size(path)
        if size < offset:
            offset, pending = 0, b""
        if size > offset:
            with path.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size - offset)
            offset += len(chunk)
            pending += chunk
            # Only a newline-terminated line counts: the governor may be mid-write.
            for raw in pending.split(b"\n")[:-1]:
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if line.strip():
                    return line
            pending = pending.rsplit(b"\n", 1)[-1]
        sleep(interval)
    return None


def _load_governor():
    spec = importlib.util.spec_from_file_location(
        "group_em_memory_governor", Path(__file__).resolve().with_name("group-em-memory-governor.py"))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, mod)
    spec.loader.exec_module(mod)
    return mod


def thaw_on_start(pidfile: Optional[Path] = None, signal_fn: Optional[Callable] = None,
                  start_time_fn: Optional[Callable] = None) -> list[int]:
    """Resume the pids a DEAD governor left frozen, before the waiter tails the log.

    Goes through the governor's owner-aware `thaw_leftovers`: a live recorded governor's pause is
    left alone. Defaults resolve to the governor's own pidfile, signal and start-time seams; all
    are injectable for tests.
    """
    gov = _load_governor()
    return gov.thaw_leftovers(pidfile if pidfile is not None else gov.default_pidfile(),
                              signal_fn if signal_fn is not None else gov.signal_tree,
                              start_time_fn if start_time_fn is not None else gov.process_start_time)


def main(argv: Optional[list[str]] = None,
         thaw: Callable[[], list[int]] = thaw_on_start) -> int:
    ap = argparse.ArgumentParser(description="Wake once on the memory governor's next log line.")
    ap.add_argument("log", type=Path)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args(argv)
    thaw()
    line = wait_for_line(args.log, args.interval)
    if line is not None:
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
