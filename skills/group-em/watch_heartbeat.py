"""Per-repo Group EM watch heartbeat -- the artifact that makes the watch's

absence loud (roadmap plan `pln-the-watch-leaves-a-trace-b884a8`, chunks C1/C2).

PURPOSE. `state/group-em-watch.json` is stamped once per tick by whichever
session currently holds the Group EM, and read by sessions OTHER than the
watcher at the entry points a session already passes through (`/group-em`
entry, `/workday-start` Step 5.7, SessionStart orientation -- wired in C3).
A watch that armed successfully and has since gone silent, or thinned to
zero `Monitor` subscriptions, must be distinguishable on disk from a repo
nobody ever watched -- that is the whole of P1/P2/P2a/P2b/P3 in the owning
plan's `## Problem set`.

ONE HOLDER, THREE PRODUCERS, TWO PLANES, NO FOLD HERE. `group-em-nomination.py`
enforces exactly one HOLDER session per repo, never exactly one WRITER, and
the three producers named by `_TICK_SOURCES` are split across two planes with
two different `stamp()` signatures over the SAME on-disk record: the
~23-minute `CronCreate` tick and the ~3-minute Monitor tick are written by
the ENGINE'S OWN COPY of this module, `coordinator_core/group_em/watch_heartbeat.py`
(the published engine root this repo resolves per
`_engine_root.resolve_claude_klabauter_root_with_provenance()`; invoked from
`coordinator_core/group_em/watch.py`, lines ~1155/~1315) -- never by `stamp()`
below. This module's `stamp()` writes only the `entry` tick, from
`group-em-enter.py`'s `_stamp_watch` -- which makes `entry` the tick that
has to carry `writer_session_id`, since the engine's arm-time refusal reads
foreignness off `(holder_session_id, writer_session_id)` and an entry record
omitting it presents as foreign to the very holder that wrote it, refusing
the first arm for the whole freshness window. Every reader (the SessionStart presence
hook, `group-em-watch-cli.py`, `read_watch` below) is this copy, not the
engine's.

Review: coordinatorreview-integrator -- overengineering-reviewer finding #3: the
paragraph that lived here re-derived the module header's own claim above; it
now lives once, at TWO_MODULES_ONE_RECORD_ARE_TWO_SIGNATURES, not here.

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
    pattern).
    """
    # Review: coordinatorreview-integrator -- overengineering-reviewer finding #3:
    # dropped the four added lines re-deriving the module header's claim at a
    # helper that neither writes nor reads a prior_* key.
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
    """Rewrite `state/group-em-watch.json` for the `entry` tick -- the only
    source this module ever writes (see the module header: `cron`/`monitor`
    are the engine's own writer). Whole-file replace, never a fold: the
    engine's `cron`/`monitor` writer replaces this same file the same way,
    so `entry` must produce the identical record shape or the next engine
    tick, ~3 minutes away at worst, silently drops whatever this module
    added that the engine's writer does not know about.

    `source` must be one of `cron` | `monitor` | `entry` (P2b/P3's `tick_source`
    vocabulary) -- `entry` in practice for this module's own callers; the other
    two are accepted to mirror the engine's declared vocabulary, not because a
    reader downstream inspects the argument (Review: coordinatorreview-integrator
    -- overengineering-reviewer finding #5: the prior wording attributed the
    width to `read_watch`, which never sees this argument). `declinations` is
    THIS tick's rows only -- each
    `{session_id, gate, reason}` -- never an accumulating history; a
    tick that messaged nobody and declined nobody passes `[]`, which is what
    lets the reader tell "did not look" apart from "looked, nothing to do".

    `writer_session_id` on the written record is the INSTRUMENT that wrote it,
    which is not `session_id` when a delegate stamps on the crown's behalf. It
    is not decoration: the engine's arm-time refusal reads foreignness off the
    pair `(holder_session_id, writer_session_id)`, so a record omitting the
    field presents as `(<holder>, None)` and is FOREIGN to the very crown that
    wrote it. Entry then locks out the watch entry exists to arm, for the
    whole freshness window, silently -- the arm refuses and a refusal read as
    a quiet result is a fleet nobody is watching. This module has no delegate
    caller (see the module header: `entry` writes on the crown's own behalf
    only), so the value is always `session_id` -- no parameter, since there is
    no second value on this axis to take.

    `holder_name`: this module never writes the key. The engine's `cron`/
    `monitor` writer is the sole owner of `holder_name` on this record; `name`
    is written only when a caller actually supplies one (no caller does today
    -- `enter()` never puts one on `standing`), so in practice entry's own
    ticks omit the key entirely rather than read the file back to preserve the
    engine's prior value. Readers already tolerate the key's absence via
    `record.get("holder_name")` and the live-registry fallback in `read_watch`
    below, so an entry tick that says nothing about the name is exactly as
    readable as one that says nothing about the name and looks unwritten.

    Returns True on a successful atomic replace, False on any I/O failure --
    never raises; a failed stamp is a missed tick, not a crash of the tick
    procedure calling it.
    """
    if source not in _TICK_SOURCES:
        raise ValueError(f"source must be one of {_TICK_SOURCES}, got {source!r}")

    next_expected_by = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + DEFAULT_TICK_INTERVAL_SECONDS)
    )

    payload = {
        "holder_session_id": session_id,
        "writer_session_id": session_id,
        "last_tick_at": _now_iso(),
        "tick_source": source,
        "next_expected_by": next_expected_by,
        "subscribed_peers": subscribed_peers,
        "declinations": list(declinations or []),
    }
    if name:
        payload["holder_name"] = name
    return _write_atomic(watch_path(repo_root), payload)


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

    Every non-`absent` verdict also carries the six `prior_*` keys the
    engine's own `stamp()` writes whenever the record it replaced was
    stamped by a different instrument (holder, writer, or tick_source
    differing) -- `prior_holder_session_id`, `prior_holder_name`,
    `prior_tick_source`, `prior_last_tick_at`, `prior_subscribed_peers`,
    `prior_declination_count`. This is the identity and rough shape of a
    tick that a later whole-file replace destroyed, never its content --
    read defensively (`.get`, no assumed presence or type) since a first
    stamp, or a record from before the engine added this trace, carries
    none of them: absent, not null, and this reader reports `None` for
    each rather than inventing a value.
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
            "prior_holder_session_id": None,
            "prior_holder_name": None,
            "prior_tick_source": None,
            "prior_last_tick_at": None,
            "prior_subscribed_peers": None,
            "prior_declination_count": None,
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
        # Review: coordinatorreview-integrator -- overengineering-reviewer finding #2:
        # the CLI's destroyed-tick render needs the record's CURRENT tick_source to
        # tell "prior differs from current" from "prior repeats current".
        "tick_source": record.get("tick_source"),
        "prior_holder_session_id": record.get("prior_holder_session_id"),
        "prior_holder_name": record.get("prior_holder_name"),
        "prior_tick_source": record.get("prior_tick_source"),
        "prior_last_tick_at": record.get("prior_last_tick_at"),
        "prior_subscribed_peers": record.get("prior_subscribed_peers"),
        "prior_declination_count": record.get("prior_declination_count"),
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
