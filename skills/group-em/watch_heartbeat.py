"""Per-repo Group EM watch heartbeat -- the artifact that makes the watch's

absence loud (roadmap plan `pln-the-watch-leaves-a-trace-b884a8`, chunks C1/C2).

PURPOSE. `state/group-em-watch.json` is stamped once per tick by whichever
session currently holds the crown, and read by sessions OTHER than the
watcher at the entry points a session already passes through (`/group-em`
entry, `/workday-start` Step 5.7, SessionStart orientation -- wired in C3).
A watch that armed successfully and has since gone silent, or thinned to
zero `Monitor` subscriptions, must be distinguishable on disk from a repo
nobody ever watched -- that is the whole of P1/P2/P2a/P2b/P3 in the owning
plan's `## Problem set`.

ONE WRITER, NO FOLD. Unlike the sibling ledger
(`coordinator/hooks/scripts/_next_move_ledger.py`), which is written by TWO
planes (this repo's own hook and the engine's cross-repo intake) and needs an
append-then-fold path to avoid a read-modify-whole-file-rewrite collision,
this file has exactly one writer per repo: the current crown holder, which is
itself a filesystem invariant enforced by `group-em-nomination.py`. Every
tick's `stamp()` call is a full rewrite of the whole record, not an append --
there is nothing to fold and no second producer to collide with. Its absence
here is not an oversight; it is what "exactly one writer" is for.
<!-- Review: overengineering-reviewer -- armed_at/tick_count read-back removed;
stamp() is now a plain write, no read-before-write, making this claim literal. -->

NO TIMING PREDICATE. `next_expected_by` is a recorded EXPECTATION -- what
this tick believes the next one will land by -- never a threshold this module
acts on. `stamp()` never reads the clock to decide whether to fire; `read_watch`
never nudges, re-nominates, or announces on a stale verdict, it only reports
one. Acting on staleness is explicitly out of scope (see the owning plan's
`## What is NOT the problem`) -- the stood-down `runtime-tripwire-stop-watcher.py`
is exactly that mechanism, at 681 fires / 26 days / ~99.4% wrong.

`absent` and `vacant` are different and never collapse: "nobody has ever
entered" (no file) and "someone entered, and their session is no longer live"
call for different moves, and the null-vs-zero collapse is this corpus's
standing failure mode.
"""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import tempfile
import time
from typing import Any, Callable, Optional

_WATCH_RELATIVE_PATH = os.path.join("state", "group-em-watch.json")

#: Recorded expectation window used by `stamp()` -- matched to the
#: `~23 minute` `CronCreate` tick interval named in `SKILL.md`. Never read
#: back as a threshold by this module.
DEFAULT_TICK_INTERVAL_SECONDS = 23 * 60

_TICK_SOURCES = ("cron", "monitor", "entry")

VERDICT_ABSENT = "absent"
VERDICT_VACANT = "vacant"
VERDICT_STALE = "stale"
VERDICT_ARMED = "armed"

_CLAUDE_AGENTS_CMD = ["claude", "agents", "--json"]


def watch_path(repo_root: str) -> str:
    """Absolute path of the heartbeat file for `repo_root`."""
    return os.path.join(repo_root, _WATCH_RELATIVE_PATH)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(value: Any) -> Optional[float]:
    """Best-effort epoch-seconds parse of a `%Y-%m-%dT%H:%M:%SZ` stamp.

    Returns None on anything unparseable -- a malformed or missing timestamp
    degrades the caller to treating the record as unreadable, never raises.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, OverflowError):
        return None


def _read_existing(path: str) -> Optional[dict]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_atomic(path: str, payload: dict) -> bool:
    """Rewrite the whole heartbeat via temp file + `os.replace` -- atomic on
    both POSIX and Windows (see `_next_move_ledger._write_records`, the same
    pattern). No cross-process lock: at most one writer, the crown holder,
    ever calls `stamp()` for a given repo, so there is no race to arbitrate.
    """
    directory = os.path.dirname(path)
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".group-em-watch-", suffix=".tmp", dir=directory
        )
        try:
            try:
                handle = os.fdopen(tmp_fd, "w", encoding="utf-8")
            except Exception:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                raise
            with handle:
                json.dump(payload, handle, sort_keys=True)
            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            if tmp_path is not None and os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    except (OSError, TypeError, ValueError):
        return False
    return True


def stamp(
    repo_root: str,
    session_id: str,
    name: Optional[str],
    source: str,
    declinations: list,
    subscribed_peers: int = 0,
) -> bool:
    """Rewrite `state/group-em-watch.json` for this tick. One writer per
    repo (the crown holder); the whole file is replaced, never folded, and
    never read first -- a plain write.

    `source` must be one of `cron` | `monitor` | `entry` (P2b/P3's `tick_source`
    vocabulary). `declinations` is THIS tick's rows only -- each
    `{session_id, name, gate, reason}` -- never an accumulating history; a
    tick that messaged nobody and declined nobody passes `[]`, which is what
    lets the reader tell "did not look" apart from "looked, nothing to do".

    Returns True on a successful atomic replace, False on any I/O failure --
    never raises; a failed stamp is a missed tick, not a crash of the tick
    procedure calling it.
    """
    if source not in _TICK_SOURCES:
        raise ValueError(f"source must be one of {_TICK_SOURCES}, got {source!r}")

    path = watch_path(repo_root)
    now = _now_iso()

    next_expected_by = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + DEFAULT_TICK_INTERVAL_SECONDS)
    )

    payload = {
        "holder_session_id": session_id,
        "holder_name": name,
        "last_tick_at": now,
        "tick_source": source,
        "next_expected_by": next_expected_by,
        "subscribed_peers": subscribed_peers,
        "declinations": list(declinations or []),
    }
    return _write_atomic(path, payload)


def _fetch_live_agents(
    run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run,
) -> Optional[list]:
    """Re-invoke `claude agents --json`. Returns None when the registry
    could not be reached or parsed at all (command missing, non-JSON output)
    -- distinct from an empty-but-successful `[]` result, which genuinely
    means no live sessions. None is the caller's signal to fail open rather
    than manufacture a false `vacant` off an unreachable registry."""
    try:
        result = run(_CLAUDE_AGENTS_CMD, capture_output=True, text=True, check=False)
    except OSError:
        return None
    try:
        data = json.loads(result.stdout)
    except (ValueError, AttributeError):
        return None
    return data if isinstance(data, list) else None


def _holder_row(holder_session_id: Any, agents: list) -> Optional[dict]:
    """The registry row for this holder, or `None` when it lists no such session."""
    if not isinstance(holder_session_id, str) or not holder_session_id:
        return None
    for agent in agents:
        if isinstance(agent, dict) and agent.get("sessionId") == holder_session_id:
            return agent
    return None


def read_watch(
    repo_root: str,
    agents: Optional[list] = None,
    run: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run,
) -> dict:
    """Read `state/group-em-watch.json` and answer one of `absent` | `vacant`
    | `stale` | `armed`, joined against the live session registry.

    `agents`, when given, is the injected registry (tests never spawn
    `claude agents --json` themselves -- they pass this list). When omitted,
    the registry is fetched fresh via `run` (never cached, per
    `read_pass.fetch_live_agents`'s same discipline) -- and a registry that
    could not be reached at all (`None` from `_fetch_live_agents`) fails
    OPEN to a freshness-only verdict (`armed`/`stale`) rather than reporting
    a holder `vacant` on no evidence; only a registry that was successfully
    read and does not list the holder earns `vacant`.

    Every verdict carries `holder_session_id`, `holder_name`, `last_tick_at`,
    and `declination_count` (the length of that tick's `declinations` list).
    `holder_name` prefers the LIVE registry row over the stamped one: a name
    is an address that re-points, and the record's copy is only as fresh as
    the tick that wrote it.
    `absent` and `vacant` never collapse: no file at all is "nobody has ever
    entered"; a file naming a holder no longer live is "the watcher exited".
    """
    path = watch_path(repo_root)
    record = _read_existing(path)
    if record is None:
        return {
            "verdict": VERDICT_ABSENT,
            "holder_session_id": None,
            "holder_name": None,
            "last_tick_at": None,
            "declination_count": 0,
        }

    holder_session_id = record.get("holder_session_id")
    holder_name = record.get("holder_name")
    last_tick_at = record.get("last_tick_at")
    # Review: coordinatorcode-reviewer P2 -- a structurally-valid JSON record whose
    # `declinations` field is truthy but not list-shaped (disk corruption, a second
    # writer's bug) short-circuited `X or []` to the non-list value and raised
    # inside this reader; `group-em-watch-cli.py` calls `read_watch` unguarded, so
    # this reached the user as an unhandled `TypeError` instead of degrading.
    raw_declinations = record.get("declinations")
    declination_count = len(raw_declinations) if isinstance(raw_declinations, list) else 0

    base = {
        "holder_session_id": holder_session_id,
        "holder_name": holder_name,
        "last_tick_at": last_tick_at,
        "declination_count": declination_count,
    }

    registry = agents if agents is not None else _fetch_live_agents(run=run)
    if registry is not None:
        row = _holder_row(holder_session_id, registry)
        if row is None:
            return {"verdict": VERDICT_VACANT, **base}
        # The registry is the live answer and the record is a snapshot, so the
        # name is re-resolved here rather than trusted from disk. A name stored
        # at stamp time can point at a different session by the time anyone
        # reads it, which is the hazard `resolve_addressee` exists to refuse on
        # the send path -- a durable copy is the same hazard with a longer fuse.
        live_name = row.get("name")
        if live_name:
            base["holder_name"] = live_name

    last_tick_epoch = _parse_iso(last_tick_at)
    next_expected_epoch = _parse_iso(record.get("next_expected_by"))
    now_epoch = time.time()
    if next_expected_epoch is not None and now_epoch > next_expected_epoch:
        return {"verdict": VERDICT_STALE, **base}
    if last_tick_epoch is None:
        return {"verdict": VERDICT_STALE, **base}

    return {"verdict": VERDICT_ARMED, **base}
