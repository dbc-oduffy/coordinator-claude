"""Append-only, per-session ledger of Stop-guard fires and their discharges.

Spec backlink: docs/plans/2026-09-06-block-discharge-durable-artifact.md
(chunk C1).

Problem this closes: a blocking Stop guard fires into a session whose only
reader is the agent it just objected to, and the turn continues. Unattended,
that agent is sole judge of its own compliance and the verdict never routes
anywhere else. This module gives a fire a durable, out-of-session record and
a way for the agent (or a later checker, see C4) to see whether it was ever
discharged.

Record shapes, one JSON object per line:

    {"kind": "fire", "nonce": ..., "guard": ..., "session_id": ...,
     "reason": ..., "at": ...}
    {"kind": "discharge", "nonce": ..., "action": ..., "at": ...}

`nonce` is the join key between the two record kinds -- minted fresh by
`record_fire` and never invented by a caller, so a `record_discharge` call
naming a nonce with no matching fire record is rejected (returns False)
rather than silently recording a self-issued discharge.

Storage: `state/block-discharge/<session-id>.jsonl` -- ONE file per session,
appended to, never one file per fire. Six-plus peer sessions share this
worktree; a per-fire file would multiply `git status` churn for all of them
with no read-side gain (see C1 dispatch brief). `repo_root` is always a
caller-supplied parameter (the value `stop-dispatch.py` already resolved via
`_git_root_walk.git_root_walk()` and threads to every guard module) -- this
module does not walk for it and does not spawn `git rev-parse`.

Writer discipline -- deliberately NOT `_next_move_ledger`'s whole-file
read-modify-write replace. That module's own docstring accepts a lost write
as "at worst a missed fire", which is the right tradeoff for a per-session
dedup latch and the wrong one for an audit record of fires: an audit record
must not be lossy under concurrent writers, since more than one of the nine
registry entries `stop-dispatch.py` fans out to can record a fire in the
same turn. So every write here is a single `O_APPEND` append of one encoded
JSON line -- atomic at the OS level, no read-modify-write, so concurrent
writers cannot clobber each other's lines. (Two ledgers, one shared
lineage of technique, deliberately NOT one shared file or one shared
in-process store -- `_next_move_ledger`'s latch semantics and this module's
audit semantics diverge exactly where lossiness would matter, so folding the
two into a single implementation would either loosen this module's
durability guarantee or tighten that one's, and only one of the two callers
wants each.)

Import-light and stdlib-only, by design: this runs on the Stop hot path,
which the dispatcher exists to keep cheap. No `subprocess`, no third-party
import, no module-level file I/O.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Optional

_LEDGER_DIRNAME = os.path.join("state", "block-discharge")


def _ledger_path(repo_root: str, session_id: str) -> str:
    return os.path.join(repo_root, _LEDGER_DIRNAME, session_id + ".jsonl")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append_record(path: str, record: dict) -> bool:
    """Single-write `O_APPEND` append of one JSON line. Best-effort: any
    failure (missing directory, permissions, disk full) is swallowed and
    reported as False -- callers translate that into their own contract
    (`record_fire` returns None rather than a nonce it could not durably
    record; `record_discharge` returns False)."""
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def _read_one(path: str) -> tuple:
    """Return `(records, skipped_count)` for one ledger file. A malformed or
    truncated line (e.g. a container torn down mid-write) is skipped and
    counted rather than aborting the read -- an unreadable ledger is an
    unresolved audit, not a clean one, and the skip count lets a checker
    (C4) report that and exit non-zero instead of reading a partial ledger
    as if it were complete."""
    records: list = []
    skipped = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:  # noqa: BLE001
                    skipped += 1
                    continue
                if isinstance(record, dict):
                    records.append(record)
                else:
                    skipped += 1
    except OSError:
        return [], 0
    return records, skipped


def record_fire(repo_root: str, session_id: str, guard: str, reason: str) -> Optional[str]:
    """Append a `fire` record and return its freshly minted nonce.

    Best-effort: on a write failure this returns `None` -- a sentinel, never
    a nonce it could not durably record -- so a write failure cannot convert
    a block into a crash, and cannot mint a nonce that will never be
    honourable (nothing durable exists for it to join against)."""
    nonce = uuid.uuid4().hex
    record = {
        "kind": "fire",
        "nonce": nonce,
        "guard": guard,
        "session_id": session_id,
        "reason": reason,
        "at": _now_iso(),
    }
    try:
        path = _ledger_path(repo_root, session_id)
        ok = _append_record(path, record)
    except Exception:  # noqa: BLE001
        ok = False
    return nonce if ok else None


def record_discharge(repo_root: str, session_id: str, nonce: str, action: str) -> bool:
    """Append a `discharge` record for `nonce`, and return whether it was
    recorded.

    Returns False if no `fire` record in this session's ledger carries
    `nonce` -- an invented nonce cannot self-discharge. `action` may be a
    reasoned no-op or a disputed-block explanation; this function (and the
    `check` side in C4) deliberately does not adjudicate `action` content --
    it exists so a human reader can see the agent's account."""
    try:
        path = _ledger_path(repo_root, session_id)
        records, _skipped = _read_one(path)
    except Exception:  # noqa: BLE001
        return False
    has_matching_fire = any(
        record.get("kind") == "fire" and record.get("nonce") == nonce for record in records
    )
    if not has_matching_fire:
        return False
    record = {
        "kind": "discharge",
        "nonce": nonce,
        "action": action,
        "at": _now_iso(),
    }
    try:
        return _append_record(path, record)
    except Exception:  # noqa: BLE001
        return False


def read_ledger(repo_root: str, session_id: Optional[str] = None) -> tuple:
    """Return `(records, skipped_count)` -- the read side C4's `check` uses.

    `session_id=None` reads every session's ledger under
    `state/block-discharge/` and aggregates both the records and the skip
    count; a given `session_id` reads just that one file. Missing directory
    or missing file is not an error -- it is an empty, clean ledger (nothing
    has fired yet)."""
    if session_id is not None:
        return _read_one(_ledger_path(repo_root, session_id))

    directory = os.path.join(repo_root, "state", "block-discharge")
    all_records: list = []
    total_skipped = 0
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return [], 0
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        records, skipped = _read_one(os.path.join(directory, name))
        all_records.extend(records)
        total_skipped += skipped
    return all_records, total_skipped
