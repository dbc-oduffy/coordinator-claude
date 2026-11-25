"""Per-phase total-cost accounting for the publish driver and the percolate-round driver.

`time.process_time()` is this process only; a phase that mostly spawns reads near zero and the
wall is unattributed. `PhaseAccount` reads the whole tree: on Windows one job object holds the
driver and every child it spawns afterwards (`process_time.LiveTreeAccountant`: no kill-on-close,
so closing the instrument never kills the driver), on POSIX `getrusage(SELF)+(CHILDREN)`.

Every figure that cannot be read is the word `unavailable`, never 0 (DR-402).
Traps: job accounting lands on ~15.6ms ticks, so a sub-100ms phase reads as a tick count; a
child spawned before the job was attached is not counted; POSIX has no process count.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, List, NamedTuple, Optional

UNAVAILABLE = "unavailable"
ROUND_LOG_ENV = "COORDINATOR_ROUND_LOG"
ROUND_LOG_SUBDIR = Path(".coordinator-local") / "publish-rounds"
_ENGINE_TAIL_BYTES = 4 * 1024 * 1024
_SESSION_ENV_NAMES = ("COORDINATOR_SESSION_ID", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID")

_files_lock = threading.Lock()
_files_total = 0


def count_files(n: int) -> None:
    """Add `n` to the process-wide files-touched counter a phase reads as a delta."""
    global _files_total
    if n > 0:
        with _files_lock:
            _files_total += int(n)


class _Mark(NamedTuple):
    wall: float
    own_cpu: float
    tree_cpu: Optional[float]
    procs: Optional[int]
    files: int
    ts: float


class PhaseCost(NamedTuple):
    """One span's cost. `cpu_total`/`spawns`/`engine_s` are None when unreadable (`engine_note` says why)."""

    wall: float
    cpu_own: float
    cpu_total: Optional[float]
    spawns: Optional[int]
    files: int
    engine_s: Optional[float]
    engine_note: str
    t_start: float
    t_end: float

    def fields(self) -> str:
        cpu = f"{self.cpu_total:.3f}s" if self.cpu_total is not None else UNAVAILABLE
        spawns = str(self.spawns) if self.spawns is not None else UNAVAILABLE
        engine = f"{self.engine_s:.3f}s" if self.engine_s is not None else f"{UNAVAILABLE}:{self.engine_note}"
        return f"cpu_total={cpu} spawns={spawns} files={self.files} engine={engine}"


def caller_session_id() -> Optional[str]:
    """The session id the warm engine tags this process's requests with, or None."""
    for name in _SESSION_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def engine_cpu_for_windows(
    windows: "List[tuple[float, float]]", session_id: Optional[str], engine_root: Optional[Path] = None
) -> "List[tuple[Optional[float], str]]":
    """Warm-engine thread CPU served to `session_id` inside each (start_ts, end_ts) window, from one read
    of the request telemetry tail.

    Each result is `(seconds, "")` or `(None, reason)`. The engine serves every peer on the box, so rows
    are filtered to this caller's session; a window is trusted only when the tail starts at or
    before it and the newest row ends at or after it (the server flushes on slow
    requests and idle ticks, so an unflushed window would otherwise read as a false zero).
    """
    if not windows:
        return []
    if not session_id:
        return [(None, "no-session-id")] * len(windows)
    try:
        from coordinator_core.warm import telemetry  # noqa: PLC0415

        telemetry.flush_requests(engine_root)
        path = telemetry.request_telemetry_path(engine_root)
        size = path.stat().st_size
        with path.open("rb") as fh:
            truncated = size > _ENGINE_TAIL_BYTES
            if truncated:
                fh.seek(size - _ENGINE_TAIL_BYTES)
            raw = fh.read()
    except Exception as exc:  # noqa: BLE001 - never fails a round
        return [(None, type(exc).__name__)] * len(windows)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    if truncated and lines:
        lines = lines[1:]
    mine: "List[tuple[float, float, float]]" = []
    oldest = newest = None
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        end = row.get("end_ts")
        start = row.get("start_ts")
        if not isinstance(end, (int, float)):
            continue
        oldest = end if oldest is None else min(oldest, end)
        newest = end if newest is None else max(newest, end)
        if row.get("session") == session_id and isinstance(start, (int, float)) \
                and isinstance(row.get("cpu_ms"), (int, float)):
            mine.append((float(start), float(end), float(row["cpu_ms"])))
    results: "List[tuple[Optional[float], str]]" = []
    for start_ts, end_ts in windows:
        if newest is None:
            results.append((None, "no-rows"))
        elif newest < end_ts:
            results.append((None, "unflushed"))
        elif truncated and oldest is not None and oldest > start_ts:
            results.append((None, "window-before-tail"))
        else:
            results.append((sum(c for s, e, c in mine if s >= start_ts and e <= end_ts) / 1000.0, ""))
    return results


def attach_engine(costs: "List[PhaseCost]", session_id: Optional[str]) -> "List[PhaseCost]":
    """`costs` with each span's `engine_s`/`engine_note` filled from one telemetry read."""
    got = engine_cpu_for_windows([(c.t_start, c.t_end) for c in costs], session_id)
    return [c._replace(engine_s=s, engine_note=n) for c, (s, n) in zip(costs, got)]


class PhaseAccount:
    """Total CPU (driver + every child), process count and files touched, read as deltas."""

    def __init__(self) -> None:
        self._tree = None
        self._rusage = None
        self.tree_note = ""
        self.session_id = caller_session_id()
        if sys.platform == "win32":
            try:
                from coordinator_core.benchmarks.process_time import LiveTreeAccountant  # noqa: PLC0415

                self._tree = LiveTreeAccountant(os.getpid())
            except Exception as exc:  # noqa: BLE001 - already in a non-nestable job, import failure
                self.tree_note = type(exc).__name__
        else:
            try:
                import resource  # noqa: PLC0415

                self._rusage = resource
            except ImportError:
                self.tree_note = "no-resource"
        self.t0 = self.mark()

    def _tree_reading(self) -> "tuple[Optional[float], Optional[int]]":
        if self._tree is not None:
            try:
                snap = self._tree.snapshot()
                return snap["process_time_ms"] / 1000.0, int(snap["procs"])
            except Exception:  # noqa: BLE001
                return None, None
        if self._rusage is not None:
            me = self._rusage.getrusage(self._rusage.RUSAGE_SELF)
            kids = self._rusage.getrusage(self._rusage.RUSAGE_CHILDREN)
            return me.ru_utime + me.ru_stime + kids.ru_utime + kids.ru_stime, None
        return None, None

    def mark(self) -> _Mark:
        tree_cpu, procs = self._tree_reading()
        return _Mark(time.perf_counter(), time.process_time(), tree_cpu, procs, _files_total, time.time())

    def cost_since(self, start: _Mark) -> PhaseCost:
        """The span since `start`; engine CPU is filled later, in one read, by `attach_engine`."""
        end = self.mark()
        cpu_total = end.tree_cpu - start.tree_cpu if end.tree_cpu is not None and start.tree_cpu is not None else None
        spawns = end.procs - start.procs if end.procs is not None and start.procs is not None else None
        return PhaseCost(
            end.wall - start.wall, end.own_cpu - start.own_cpu, cpu_total, spawns,
            end.files - start.files, None, "not-measured", start.ts, end.ts,
        )

    def close(self) -> None:
        if self._tree is not None:
            self._tree.close()
            self._tree = None


_ACCOUNT: Optional[PhaseAccount] = None


def get_account() -> PhaseAccount:
    """The one account per driver process, created at first use."""
    global _ACCOUNT
    if _ACCOUNT is None:
        _ACCOUNT = PhaseAccount()
    return _ACCOUNT


def unattributed_line(label: str, total: PhaseCost, parts_cpu: float, parts_spawns: int, spans_have_cpu: bool) -> str:
    """The summary's remainder: whole-process cost minus the sum of the listed spans."""
    if total.cpu_total is None or not spans_have_cpu:
        return f"  [timing] {label}: unattributed cpu_total={UNAVAILABLE} spawns={UNAVAILABLE}"
    spawns = f"{total.spawns - parts_spawns}" if total.spawns is not None else UNAVAILABLE
    return f"  [timing] {label}: unattributed cpu_total={total.cpu_total - parts_cpu:.3f}s spawns={spawns}"


@contextmanager
def track() -> Iterator[List[PhaseCost]]:
    """Time one span; the yielded list holds its `PhaseCost` after the block exits."""
    acct = get_account()
    start = acct.mark()
    out: List[PhaseCost] = []
    try:
        yield out
    finally:
        out.append(acct.cost_since(start))


class _Tee:
    """Duplicates writes to a stream and to the round log; the log never fails the round."""

    def __init__(self, stream: IO[str], log: IO[str]) -> None:
        self._stream = stream
        self._log = log

    def write(self, data: str) -> int:
        n = self._stream.write(data)
        try:
            self._log.write(data)
            self._log.flush()
        except Exception:  # noqa: BLE001
            pass
        return n

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def round_log_path(repo_root: Path, label: str) -> Path:
    """`<repo>/.coordinator-local/publish-rounds/<utc>-<label>.log`, or the path a parent round already chose."""
    inherited = os.environ.get(ROUND_LOG_ENV, "").strip()
    if inherited:
        return Path(inherited)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in label) or "round"
    return repo_root / ROUND_LOG_SUBDIR / f"{stamp}-{safe}.log"


@contextmanager
def tee_round_log(repo_root: Path, label: str) -> Iterator[Optional[Path]]:
    """Tee this process's stdout and stderr into the durable round log; yields its path (None if unwritable).

    The path is exported in `ROUND_LOG_ENV` so a delegated child appends to the same file.
    """
    try:
        path = round_log_path(repo_root, label)
        path.parent.mkdir(parents=True, exist_ok=True)
        log = path.open("a", encoding="utf-8", errors="replace", newline="")
    except OSError:
        yield None
        return
    prev_out, prev_err = sys.stdout, sys.stderr
    prev_env = os.environ.get(ROUND_LOG_ENV)
    os.environ[ROUND_LOG_ENV] = str(path)
    sys.stdout, sys.stderr = _Tee(prev_out, log), _Tee(prev_err, log)
    try:
        yield path
    finally:
        sys.stdout, sys.stderr = prev_out, prev_err
        if prev_env is None:
            os.environ.pop(ROUND_LOG_ENV, None)
        else:
            os.environ[ROUND_LOG_ENV] = prev_env
        log.close()
