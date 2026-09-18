"""
coordinator.bin.measure-listener-availability -- committed sampler for the http-transport
fail-open exposure window.

Ported from DoE-claude `coordinator/bin/measure-listener-availability.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`). One path-resolution seam changed (§ Path
resolution): DoE's copy resolved "the claude-klabauter engine clone" as a SIBLING repo, via a
machine-local registry key (`repos.claude_klabauter`) read through a settings-home ladder --
`_settings_home`, `_read_registry_key`, `_resolve_engine_root` below, all deleted, not ported
(§ Path resolution: "`_engine_root` imports are deleted, not ported"). That whole mechanism
existed only because DoE and the engine were two different repos on the box; now that this
sampler lives INSIDE the engine it probes, `coordinator_core.warm.election` / `.client` are an
ordinary "engine" class import (this module's own `__file__` parent chain is the engine root),
the same resolution `coordinator/bin/goal-kr-evidence.py` already uses. `--engine-root` /
`COORDINATOR_ENGINE_ROOT` are kept as an override (a test sandbox, or a differently-laid-out
clone) but now default to this repo's own root instead of a registry lookup.

Purpose: docs/plans/2026-08-25-measure-the-http-transport-fail-open-exp.md, chunk C2. project-
Claude-klabauter's C14b wants a Bash PreToolUse guard moved onto Claude Code's `type: "http"` hook transport,
which fails open (guard silently stops guarding) whenever its listener is unreachable. No listener
exists yet -- C1 (docs/research/2026-08-25-http-listener-availability.md) established that a
listener living inside claude-klabauter's warm engine would be up exactly when that engine process is, and
that the engine is NOT a long-lived daemon: it is ephemeral by design, spawned lazily and dying
every few minutes (median generation life ~5.6-5.7min per the warm-engine door's own README and
`coordinator_core.orientation.warm_health_signal`). This module measures that process's naturally-
occurring availability over a working day, so the fail-open exposure window has a real number
behind it instead of a hypothetical.

Negative spec -- why this file exists at all rather than a throwaway listener in a session
scratchpad: `measure-loopback-round-trip.py`'s own docstring records the precedent this repeats.
Its first measurement of the round-trip term was a throwaway; it produced a wrong bimodal figure
that was published to a peer repo, and by the time the figure was refuted the original harness was
gone, so its actual defect could never be identified. A long-running availability sampler is even
more exposed to that failure mode than a short latency probe: it runs for a working day, unattended,
and its correctness properties (does a gap in the record mean "sampler dead" or "subject dead"?)
are exactly the kind of thing nobody can reconstruct after the fact from a deleted scratch script.
Do not move this back to a scratchpad.

THE PROBE -- settled by C1, not re-derived here. C1 ruled out two tempting shortcuts:
  - `coordinator-invoke.exe` (the C door) -- on ANY doubt (pipe not found, busy, malformed
    response, anything) it falls straight through to a cold Python execution of the op and prints
    a normal-looking success. A stone-dead listener therefore reads as "up" through the door. This
    sampler never shells out to it.
  - `coordinator_core.warm.client.dispatch()` -- its own miss path is `_spawn_once()`, so merely
    observing through it would start the very process this sampler must observe passively.
Instead this sampler dials the elected endpoint directly, at the same layer `warm.client` itself
uses just before its spawn-on-miss branch: `election.pipe_name(engine_token())` on Windows (a pure
string derivation -- two `stat()` calls, no subprocess, no side effect), opened with a bare
`open(pipe, "r+b")`. A missing pipe raises `FileNotFoundError` immediately with no side effect --
nothing is created, nothing is spawned. It then writes+reads one trivial `scope=none` op
(`cli.parse_flag`), bounded by `coordinator_core.warm.client.READ_DEADLINE_SECS` (2.0s) -- the same
constant the engine's own client uses to decide "is the server alive". Three outcomes, recorded
distinctly (never collapsed):
    connect-fail                       -> down,  mode="no_listener"
    connect ok, contended (busy)       -> up,    mode="busy"/"backlog" (server demonstrably
                                                   present, just queued -- `warm.client`'s own
                                                   anti-storm table treats a busy pipe as "up, do
                                                   not retry", and this sampler mirrors that
                                                   verdict). Kept as its OWN mode and reported as
                                                   `contended_share_of_uptime`: for a BLOCKING
                                                   guard the operator waits contention out, and on
                                                   this box contention is the dominant term (the
                                                   door-probe spike measured 324ms p50 against a
                                                   22ms floor). An uptime figure that cannot say
                                                   how much of its "up" was queueing overstates
                                                   the guard's health.
    connect ok, answered in time       -> up,    mode="answered" (any well-formed JSON-RPC frame,
                                                   error envelope included -- the server engaged)
    connect ok, read-timeout           -> down,  mode="wedged" (bound but not servicing -- a wedged
                                                   listener fails open exactly like a dead one, so
                                                   it counts as down, never as a third state)
    connect ok, empty/malformed frame  -> down,  mode="empty_response"/"malformed_response"

TRANSPORT ASYMMETRY, again by name (C1's own framing): the probe rides the named pipe / unix
socket because that is the endpoint observable today. The thing this measurement is actually
reasoning about is an http listener that WOULD live inside the same host process -- a listener
that does not exist yet and would be circular to stand up just to measure it (anti-scope, plan
body). This sampler measures the host process's availability, which C1 established as the honest
proxy for the http endpoint's. The plan's `127.0.0.1`-literal rule binds any http CLIENT this repo
writes; it does not apply here because this file never dials http.

MULTI-OS COVERAGE. Windows (the box this plan runs on) is exercised end-to-end via
`coordinator_core.warm.election.pipe_name` / `.warm.client.engine_token`, both imported read-only
from the resolved claude-klabauter engine clone. `client.py` also carries a POSIX arm
(`election.socket_path`, an `AF_UNIX` connect) that this module's `_probe_posix` mirrors for parity
-- unexercised on this box (no POSIX host available here to run it against a live server) and
carrying the same "not verified on other OSes" caveat the plan's own Out-of-scope section states
for the cost profile generally. `sys.platform == "win32"` selects the arm at call time; nothing here
guesses.

AC4 -- GAP VS. DOWN, THE SINGLE MOST IMPORTANT CORRECTNESS PROPERTY IN THIS FILE. A killed or
restarted sampler must never let its own silence read as subject uptime OR subject downtime --
either misreading fabricates the number this plan exists to produce. Two things make the two
distinguishable:
  1. Every appended line IS a heartbeat: `kind: "sample"` records carry `pid`, `seq` (a counter
     that persists across restarts -- resumed from the last record's `seq` + 1, so a fresh process
     boundary is visible in the record even when timestamps alone would not show one) and the
     subject observation together. A tick that never got written because the sampler was not
     running produces no line at all -- there is no way to fabricate liveness retroactively.
  2. `--report` walks CONSECUTIVE sample timestamps and classifies each inter-sample interval: one
     close to the configured `--interval-secs` is attributed to the earlier sample's subject state
     (up time or down time, accordingly); one exceeding `--gap-threshold-multiplier` x the interval
     (default 3x) is a SAMPLER GAP -- excluded from both the uptime and downtime tally and reported
     under its own bucket, never silently folded into either. A `kind: "start"` record (written
     once at every process boot, before the first sample) marks exactly when a fresh sampler
     lifetime began, which is what lets a reader see WHY a gap happened (a restart) rather than
     merely THAT one did.
This is why the file is append-only and never rewrites history: the record's own silence is the
signal, and a rewritten or truncated history could no longer prove it.

AC3 -- DUTY CYCLE. `--report` also sums each sample's own `probe_latency_ms` against the wall-clock
span the samples cover and prints the fraction as this sampler's duty cycle -- the fraction of the
measurement period this process spent actually doing pipe I/O, as opposed to sleeping. This box
carries a dozen-plus concurrent EM sessions (CLAUDE.md); a sampler whose own footprint is not
negligible against that load would be measuring itself, not the subject.

Interval floor -- NOT free to choose. C1 measured the subject's median generation life at
~5.6-5.7 minutes; a cadence coarser than that would alias away real outages the way an hourly
sample would miss a five-minute one entirely. `--interval-secs` defaults to 30 (tens of seconds,
per the plan). Do NOT lower it to a latency-probe cadence (the plan's anti-scope names the K=25-
in-minutes precedent explicitly) for a real collection run -- a fast interval exists here only to
make `--once`/smoke-testing convenient, not as a production knob.

Refuses to run two samplers against one output file: an OS-native exclusive lock
(`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) on a sibling `<output>.lock` file, held for
the sampler's entire lifetime and released by the kernel on any exit including a hard kill -- the
same reasoning `coordinator_core.warm.election`'s own `flock`-based election lock documents for why
a lock FILE'S existence proves nothing and only the live kernel hold matters.

Usage:
    python coordinator/bin/measure-listener-availability.py --once
    python coordinator/bin/measure-listener-availability.py --output state/measurements/listener-availability.jsonl
    python coordinator/bin/measure-listener-availability.py --report --output state/measurements/listener-availability.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------------------------
# Engine-root resolution ("engine" class, § Path resolution). This script lives inside the
# engine it probes, so its own `__file__` parent chain IS the engine root -- no registry lookup,
# no sibling-checkout search. `COORDINATOR_ENGINE_ROOT` is kept as an override for a test
# sandbox or a differently-laid-out clone.
# --------------------------------------------------------------------------------------------

_ENGINE_ROOT = Path(__file__).resolve().parents[2]


def _resolve_engine_root() -> Path:
    override = os.environ.get("COORDINATOR_ENGINE_ROOT")
    return Path(override) if override else _ENGINE_ROOT


# --------------------------------------------------------------------------------------------
# The probe. Imports `coordinator_core.warm.election` / `.client` READ-ONLY, and only the pure
# derivation functions (`pipe_name`, `socket_path`, `engine_token`, the two deadline constants) --
# never `client.try_warm_dispatch` or `client.dispatch`, which is exactly the seam C1 forbade.
# --------------------------------------------------------------------------------------------

SUBJECT_UP = "up"
SUBJECT_DOWN = "down"

#: The op this probe dials: `cli.parse_flag`, `scope=none` (no filesystem, no repo state) --
#: the same op the 2026-08-23 door-probe spike validated as transport-only work with no side
#: effects (C1's own citation). Any value works; this one is deliberately inert.
_PROBE_METHOD = "cli.parse_flag"
_PROBE_PARAMS = {"arguments": "--probe listener-availability", "flag_names": ["--probe"]}

_TIMED_OUT = object()


class _ThreadedRead:
    """One `readline()` on a daemon thread, waited with a deadline -- the Windows named-pipe file
    object has no `settimeout`, so a bounded read needs this shape (mirrors
    `coordinator_core.warm.client._PendingRead`, trimmed to this module's single-deadline need: no
    mutation-deadline second wait, because every op this sampler ever sends is `scope=none`)."""

    def __init__(self, fh: Any) -> None:
        self._result: dict[str, Any] = {}
        self._thread = threading.Thread(target=self._run, args=(fh,), daemon=True)
        self._thread.start()

    def _run(self, fh: Any) -> None:
        try:
            self._result["line"] = fh.readline()
        except OSError as exc:
            self._result["exc"] = exc

    def wait(self, deadline_secs: float) -> Any:
        self._thread.join(deadline_secs)
        if self._thread.is_alive():
            return _TIMED_OUT
        if "exc" in self._result:
            raise self._result["exc"]
        return self._result.get("line")


def _classify_response(line: Any) -> tuple[str, Optional[str]]:
    """Shared verdict for "bytes came back" on either platform arm. Returns (subject, mode)."""
    if line is _TIMED_OUT:
        return SUBJECT_DOWN, "wedged"
    if not line or not line.strip():
        return SUBJECT_DOWN, "empty_response"
    try:
        response = json.loads(line)
    except json.JSONDecodeError:
        return SUBJECT_DOWN, "malformed_response"
    if not isinstance(response, dict) or "jsonrpc" not in response:
        return SUBJECT_DOWN, "malformed_response"
    return SUBJECT_UP, "answered"


def _probe_windows(pipe: str, payload: bytes, read_deadline: float) -> tuple[str, Optional[str], float]:
    started = time.perf_counter()
    try:
        fh = open(pipe, "r+b")
    except FileNotFoundError:
        return SUBJECT_DOWN, "no_listener", (time.perf_counter() - started) * 1000
    except OSError as exc:
        # ERROR_PIPE_BUSY (231): server up, contended -- warm.client's own anti-storm table
        # counts this as UP and refuses to retry into it; this sampler mirrors that verdict
        # rather than inventing a third state for "present but momentarily contended".
        # Recorded under its own mode, never merged into "answered": for a BLOCKING guard the
        # operator waits out contention, and this box's contention is not incidental -- the
        # door-probe spike measured arm C at 324ms p50 against a 22ms floor. An uptime figure
        # that cannot say how much of its "up" was queueing would overstate the guard's health.
        if getattr(exc, "winerror", None) == 231:
            return SUBJECT_UP, "busy", (time.perf_counter() - started) * 1000
        return SUBJECT_DOWN, f"connect_error:{exc!r}", (time.perf_counter() - started) * 1000

    try:
        fh.write(payload)
        fh.flush()
        line = _ThreadedRead(fh).wait(read_deadline)
    except OSError as exc:
        return SUBJECT_DOWN, f"write_error:{exc!r}", (time.perf_counter() - started) * 1000
    finally:
        try:
            fh.close()
        except OSError:
            pass

    subject, mode = _classify_response(line)
    return subject, mode, (time.perf_counter() - started) * 1000


def _probe_posix(
    socket_path_str: str, payload: bytes, connect_deadline: float, read_deadline: float
) -> tuple[str, Optional[str], float]:
    """POSIX arm -- unexercised on this box (Windows-only host), kept in parity with
    `coordinator_core.warm.client._open_pipe`'s own POSIX branch. See module docstring."""
    import socket as _socket

    started = time.perf_counter()
    sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        sock.settimeout(connect_deadline)
        sock.connect(socket_path_str)
    except (FileNotFoundError, ConnectionRefusedError):
        sock.close()
        return SUBJECT_DOWN, "no_listener", (time.perf_counter() - started) * 1000
    except (TimeoutError, _socket.timeout):
        # Full backlog -- server up, contended. Same verdict as ERROR_PIPE_BUSY above,
        # and likewise recorded under its own mode rather than merged into "answered".
        sock.close()
        return SUBJECT_UP, "backlog", (time.perf_counter() - started) * 1000
    except OSError as exc:
        sock.close()
        return SUBJECT_DOWN, f"connect_error:{exc!r}", (time.perf_counter() - started) * 1000

    try:
        sock.settimeout(None)
        io = sock.makefile("rwb")
        sock.close()  # documented CPython idiom -- io holds its own reference
        io.write(payload)
        io.flush()
        line = _ThreadedRead(io).wait(read_deadline)
    except OSError as exc:
        return SUBJECT_DOWN, f"write_error:{exc!r}", (time.perf_counter() - started) * 1000
    finally:
        try:
            io.close()
        except (OSError, UnboundLocalError):
            pass

    subject, mode = _classify_response(line)
    return subject, mode, (time.perf_counter() - started) * 1000


class Prober:
    """Resolves the engine clone and pipe/socket identity ONCE per process (the token can change
    across a generation boundary, but re-deriving it fresh on every tick is what `warm.client`
    itself does, and it is two cheap `stat()` calls -- not worth caching across a sample when
    doing so risks probing a stale generation's endpoint name after a spawn)."""

    def __init__(self, engine_root: Path) -> None:
        sys.path.insert(0, str(engine_root))
        from coordinator_core.warm import client as warm_client  # noqa: PLC0415
        from coordinator_core.warm import election  # noqa: PLC0415

        self._client = warm_client
        self._election = election
        self.read_deadline = warm_client.READ_DEADLINE_SECS
        self.connect_deadline = getattr(warm_client, "CONNECT_DEADLINE_SECS", 0.25)

    def probe_once(self) -> dict:
        token = self._client.engine_token()
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": _PROBE_METHOD,
            "params": _PROBE_PARAMS,
            "_engine_token": token,
        }
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"

        if sys.platform == "win32":
            endpoint = self._election.pipe_name(token)
            subject, mode, latency_ms = _probe_windows(endpoint, payload, self.read_deadline)
        else:
            endpoint = str(self._election.socket_path(token))
            subject, mode, latency_ms = _probe_posix(
                endpoint, payload, self.connect_deadline, self.read_deadline
            )
        return {
            "subject": subject,
            "mode": mode,  # "answered"/"busy"/"backlog" on up; the failure name on down
            "probe_latency_ms": round(latency_ms, 3),
            "engine_token": token,
        }


# --------------------------------------------------------------------------------------------
# Singleton lock -- refuses a second sampler against the same output file.
# --------------------------------------------------------------------------------------------


class AlreadyRunningError(RuntimeError):
    pass


def _acquire_singleton_lock(output_path: Path):
    """Exclusive, kernel-held lock on `<output>.lock`. Returns an opaque handle the caller must
    keep referenced for the sampler's lifetime (garbage-collecting or closing it releases the
    lock) -- never released explicitly, mirroring `coordinator_core.warm.election`'s own
    election-lock reasoning: the lock FILE surviving a hard kill is harmless because it is never
    consulted for liveness, only locked."""
    lock_path = Path(str(output_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            os.close(fd)
            raise AlreadyRunningError(
                f"another sampler already holds the lock for {output_path}"
            ) from exc
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise AlreadyRunningError(
                f"another sampler already holds the lock for {output_path}"
            ) from exc
    return fd


# --------------------------------------------------------------------------------------------
# Recording.
# --------------------------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _last_seq(output_path: Path) -> int:
    """Resume point for the `seq` heartbeat counter -- the last record's `seq`, or -1 if the file
    is absent/empty/unparseable (fresh start). Reads only the tail; this file can grow to tens of
    thousands of lines over a working day and a full parse on every resume would be needless."""
    if not output_path.is_file():
        return -1
    try:
        with output_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            chunk = min(size, 4096)
            fh.seek(-chunk, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return -1
    for raw_line in reversed(tail.splitlines()):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        seq = record.get("seq")
        if isinstance(seq, int):
            return seq
    return -1


def _append(output_path: Path, record: dict) -> None:
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


def run_sampler(
    output_path: Path,
    interval_secs: float,
    engine_root: Path,
    max_samples: Optional[int] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = _acquire_singleton_lock(output_path)  # noqa: F841 -- held for process lifetime

    prober = Prober(engine_root)
    seq = _last_seq(output_path) + 1

    _append(
        output_path,
        {
            "kind": "start",
            "ts": _now_iso(),
            "pid": os.getpid(),
            "seq": seq,
            "interval_secs": interval_secs,
            "platform": platform.platform(),
            "engine_root": str(engine_root),
        },
    )

    taken = 0
    try:
        while max_samples is None or taken < max_samples:
            tick_started = time.perf_counter()
            result = prober.probe_once()
            record = {
                "kind": "sample",
                "ts": _now_iso(),
                "pid": os.getpid(),
                "seq": seq,
                **result,
            }
            _append(output_path, record)
            print(
                f"[{record['ts']}] seq={seq} subject={result['subject']} "
                f"mode={result['mode']} latency_ms={result['probe_latency_ms']}",
                flush=True,
            )
            seq += 1
            taken += 1
            elapsed = time.perf_counter() - tick_started
            time.sleep(max(0.0, interval_secs - elapsed))
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------------------------
# --report
# --------------------------------------------------------------------------------------------

OUTAGE_BUCKETS = ("<1min", "1-5min", "5-15min", "15-60min", ">60min")


def _bucket_outage(minutes: float) -> str:
    if minutes < 1:
        return "<1min"
    if minutes < 5:
        return "1-5min"
    if minutes < 15:
        return "5-15min"
    if minutes < 60:
        return "15-60min"
    return ">60min"


def _load_samples(output_path: Path) -> list[dict]:
    samples = []
    with output_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if record.get("kind") == "sample":
                samples.append(record)
    samples.sort(key=lambda r: r["ts"])
    return samples


def _mode_census(samples: list[dict]) -> dict:
    """Per-mode sample counts, so a reader can see how much of "up" was queueing."""
    census: dict[str, int] = {}
    for smp in samples:
        key = f"{smp.get('subject')}:{smp.get('mode')}"
        census[key] = census.get(key, 0) + 1
    return dict(sorted(census.items()))


def _engine_commits(engine_root: Path, since: datetime, until: datetime) -> list[dict]:
    """Commits landing in the engine clone across the sampled span.

    Exists because the first outage this sampler ever recorded was NOT churn: a percolate
    (`5eb74eed`) deleted `coordinator_core/_engine_stamp` three seconds before the subject went
    down, and an unstamped clone is "not a warm-server host" by ruling -- so the engine stops
    serving, the http listener cannot be elected, and live ops refuse. Attribution is therefore
    part of the measurement, not a nicety: an outage with a deploy behind it and an outage from
    natural churn are different findings that a duration alone cannot tell apart.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--format=%H%x1f%cI%x1f%s",
             f"--since={since.isoformat()}", f"--until={until.isoformat()}"],
            cwd=str(engine_root), capture_output=True, text=True, timeout=60,
        )
    except Exception:  # noqa: BLE001 -- attribution is best-effort; never fail the report
        return []
    rows = []
    for line in (out.stdout or "").splitlines():
        parts = line.split("")
        if len(parts) != 3:
            continue
        try:
            when = datetime.fromisoformat(parts[1])
        except ValueError:
            continue
        rows.append({"sha": parts[0][:9], "at": when, "subject": parts[2]})
    return rows


def _attribute(outages: list[dict], commits: list[dict], window_secs: float = 180.0) -> None:
    """Tag each outage with any engine-clone commit landing just before it began.

    `window_secs` is deliberately generous relative to the 3s observed on the percolate: a
    deploy that lands mid-interval is seen at the next sample, so the gap between cause and
    first `down` is bounded by the sampling interval, not by the deploy.
    """
    for o in outages:
        o["attributed_to"] = [
            {"sha": c["sha"], "subject": c["subject"],
             "lead_secs": round((o["started"] - c["at"]).total_seconds(), 1)}
            for c in commits
            if 0 <= (o["started"] - c["at"]).total_seconds() <= window_secs
        ]


def _outage_rows(outages: list[dict], first: datetime, last: datetime,
                 engine_root: Optional[Path], interval: float) -> list[dict]:
    """Per-outage rows with deploy attribution, newest first.

    NEVER emits a point duration. A sampler observes an outage only at its own cadence, so
    `k` consecutive down samples establish that the subject was down for AT LEAST
    `(k-1) * interval` and AT MOST `(k+1) * interval`, and nothing narrower. The unobserved
    interval on BOTH sides is real: at k=1 the true outage may be milliseconds or may be just
    under two intervals, and reporting the accumulated wall time as a measurement claims a
    precision the sampling rate cannot support. That defect shipped a "30.2s" figure into a
    decision record and a monitor banner for what was a single missed sample."""
    if not outages:
        return []
    commits = _engine_commits(engine_root, first, last) if engine_root else []
    _attribute(outages, commits)
    rows = []
    for o in outages:
        k = o.get("down_samples", 0)
        rows.append({
            "started": o["started"].isoformat().replace("+00:00", "Z") if o["started"] else None,
            "at_least_secs": round(max(0.0, (k - 1) * interval), 1),
            "at_most_secs": round((k + 1) * interval, 1),
            "down_samples": k,
            "ended_by": o["ended_by"],
            "attributed_to": o.get("attributed_to") or [],
        })
    return rows


def build_report(output_path: Path, interval_secs: float, gap_threshold_multiplier: float,
                 engine_root: Optional[Path] = None) -> dict:
    """Reduce the JSONL to AC5's terms: uptime fraction, outage count, outage-duration buckets,
    longest continuous outage -- explicitly excluding sampler-gap time from both the uptime and
    downtime tally (AC4's whole point)."""
    samples = _load_samples(output_path)
    if len(samples) < 2:
        return {
            "n_samples": len(samples),
            "error": "fewer than 2 sample records -- nothing to reduce yet",
        }

    gap_threshold = interval_secs * gap_threshold_multiplier
    up_secs = 0.0
    down_secs = 0.0
    gap_secs = 0.0
    gap_count = 0
    outage_durations_secs: list[float] = []
    current_outage_down_samples = 0
    outages: list[dict] = []
    outage_started: Optional[datetime] = None
    contended_secs = 0.0
    current_outage_secs = 0.0
    in_outage = False
    latencies = [s["probe_latency_ms"] for s in samples if isinstance(s.get("probe_latency_ms"), (int, float))]

    def _parse_ts(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    timestamps = [_parse_ts(s["ts"]) for s in samples]

    # The bound arithmetic below is keyed on the cadence the SAMPLES actually show, never on
    # `interval_secs` as configured: a sampler that drifted, was throttled, or was restarted
    # with a different flag would otherwise be scored against a cadence it never ran at.
    _deltas = sorted(
        d for d in ((timestamps[i + 1] - timestamps[i]).total_seconds()
                    for i in range(len(samples) - 1))
        if d <= gap_threshold
    )
    observed_interval = _deltas[len(_deltas) // 2] if _deltas else interval_secs

    for i in range(len(samples) - 1):
        delta = (timestamps[i + 1] - timestamps[i]).total_seconds()
        subject = samples[i]["subject"]

        if delta > gap_threshold:
            gap_secs += delta
            gap_count += 1
            if in_outage:
                outage_durations_secs.append(current_outage_secs)
                outages.append({"started": outage_started, "duration_secs": current_outage_secs,
                                "down_samples": current_outage_down_samples,
                                "ended_by": "sampler_gap"})
                current_outage_secs = 0.0
                current_outage_down_samples = 0
                in_outage = False
                outage_started = None
            continue

        if subject == SUBJECT_UP:
            up_secs += delta
            if samples[i].get("mode") in ("busy", "backlog"):
                contended_secs += delta
            if in_outage:
                outage_durations_secs.append(current_outage_secs)
                outages.append({"started": outage_started, "duration_secs": current_outage_secs,
                                "down_samples": current_outage_down_samples,
                                "ended_by": "recovered"})
                current_outage_secs = 0.0
                current_outage_down_samples = 0
                in_outage = False
                outage_started = None
        else:
            down_secs += delta
            current_outage_secs += delta
            current_outage_down_samples += 1
            if not in_outage:
                outage_started = timestamps[i]
            in_outage = True

    if in_outage:
        outage_durations_secs.append(current_outage_secs)
        outages.append({"started": outage_started, "duration_secs": current_outage_secs,
                        "down_samples": current_outage_down_samples,
                        "ended_by": "still_down"})

    monitored_secs = up_secs + down_secs
    uptime_fraction = (up_secs / monitored_secs) if monitored_secs > 0 else None

    span_secs = (timestamps[-1] - timestamps[0]).total_seconds()
    duty_cycle = (sum(latencies) / 1000.0) / span_secs if span_secs > 0 and latencies else None

    outage_at_most_secs = [
        (o.get("down_samples", 0) + 1) * observed_interval for o in outages
    ]
    buckets = {name: 0 for name in OUTAGE_BUCKETS}
    for at_most in outage_at_most_secs:
        buckets[_bucket_outage(at_most / 60.0)] += 1

    return {
        "n_samples": len(samples),
        "monitored_span_secs": round(span_secs, 1),
        "uptime_fraction": round(uptime_fraction, 6) if uptime_fraction is not None else None,
        "up_secs": round(up_secs, 1),
        "down_secs": round(down_secs, 1),
        "sampler_gap_secs": round(gap_secs, 1),
        "sampler_gap_count": gap_count,
        "outage_count": len(outage_durations_secs),
        # Ranked on the UPPER bound, never on accumulated wall time -- see `_outage_rows`.
        "longest_outage_at_most_secs": (
            round(max(outage_at_most_secs), 1) if outage_at_most_secs else 0.0
        ),
        "sample_interval_observed_secs": round(observed_interval, 1),
        "outage_duration_buckets": buckets,
        # Uptime is not uniform: a "busy"/"backlog" sample means the host process was present
        # but queued. For a BLOCKING guard the operator waits that out, so it is reported as its
        # own share of uptime rather than left indistinguishable from a clean answer.
        "contended_secs": round(contended_secs, 1),
        "contended_share_of_uptime": (
            round(contended_secs / up_secs, 6) if up_secs > 0 else None
        ),
        "mode_census": _mode_census(samples),
        "outages": _outage_rows(outages, timestamps[0], timestamps[-1], engine_root,
                                observed_interval),
        "sampler_duty_cycle": round(duty_cycle, 8) if duty_cycle is not None else None,
        "probe_latency_ms_median": round(statistics.median(latencies), 3) if latencies else None,
        "probe_latency_ms_p90": (
            round(sorted(latencies)[int(0.9 * len(latencies))], 3) if latencies else None
        ),
    }


def print_report(report: dict) -> None:
    if "error" in report:
        print(f"n_samples={report['n_samples']}: {report['error']}", flush=True)
        return
    print(
        f"n_samples={report['n_samples']} monitored_span={report['monitored_span_secs']}s "
        f"uptime_fraction={report['uptime_fraction']} "
        f"contended_share_of_uptime={report['contended_share_of_uptime']}",
        flush=True,
    )
    print(
        f"up={report['up_secs']}s down={report['down_secs']}s "
        f"sampler_gaps={report['sampler_gap_secs']}s (count={report['sampler_gap_count']}) "
        "-- gap time is EXCLUDED from uptime_fraction, never counted as subject downtime",
        flush=True,
    )
    print(
        f"outage_count={report['outage_count']} "
        f"longest_outage_at_most_secs={report['longest_outage_at_most_secs']}",
        flush=True,
    )
    print(
        "   " + "  ".join(f"{name}: {report['outage_duration_buckets'][name]}" for name in OUTAGE_BUCKETS),
        flush=True,
    )
    for o in report.get("outages") or []:
        attrib = o.get("attributed_to") or []
        if attrib:
            tag = "  <- " + "; ".join(
                f"{a['sha']} (+{a['lead_secs']}s) {a['subject'][:60]}" for a in attrib
            )
        else:
            tag = "  <- no engine-clone commit in the 180s before it: not deploy-attributable"
        print(f"  outage {o['started']} for at least {o['at_least_secs']}s, at most "
              f"{o['at_most_secs']}s [{o['down_samples']} missed sample(s)] "
              f"({o['ended_by']}){tag}")

    print(
        f"sampler_duty_cycle={report['sampler_duty_cycle']} "
        f"probe_latency_ms median={report['probe_latency_ms_median']} p90={report['probe_latency_ms_p90']}",
        flush=True,
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="state/measurements/http-listener-availability.jsonl",
        help="Append-only JSONL path (default: state/measurements/http-listener-availability.jsonl)",
    )
    parser.add_argument(
        "--interval-secs",
        type=float,
        default=30.0,
        help="Sampling interval. Tens of seconds by C1's finding; do not lower for a real "
        "collection run (see module docstring's interval-floor note).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Stop after N samples (smoke-testing only; omit for a real collection run).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Take exactly one sample and exit (does not take the singleton lock or loop).",
    )
    parser.add_argument("--report", action="store_true", help="Reduce the JSONL and print, then exit.")
    parser.add_argument(
        "--gap-threshold-multiplier",
        type=float,
        default=3.0,
        help="--report only: an inter-sample gap wider than this multiple of --interval-secs "
        "is treated as a sampler gap, not subject downtime.",
    )
    parser.add_argument(
        "--engine-root",
        default=None,
        help="Override the engine root this sampler probes (defaults to this repo's own root, "
        "or $COORDINATOR_ENGINE_ROOT).",
    )
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    engine_root = Path(args.engine_root) if args.engine_root else _resolve_engine_root()

    if args.report:
        if not output_path.is_file():
            print(f"no such file: {output_path}", file=sys.stderr)
            return 2
        report = build_report(output_path, args.interval_secs, args.gap_threshold_multiplier,
                              engine_root=engine_root)
        print_report(report)
        return 0

    if args.once:
        prober = Prober(engine_root)
        result = prober.probe_once()
        print(json.dumps(result, ensure_ascii=False))
        return 0

    try:
        run_sampler(output_path, args.interval_secs, engine_root, max_samples=args.max_samples)
    except AlreadyRunningError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
