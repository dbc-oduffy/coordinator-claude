"""uhura-mode.py -- who holds the PM comms channel for a repo, and since when.

Uhura is a MODE an EM session enters, the same shape as `/group-em`, not an agent
and not a persona. This module is the one durable fact the mode needs: which
session is currently the channel. Everything else about the mode -- the triage
ladder, the reserved push channel, the pointer-not-authority rule -- lives in
the `uhura` skill doctrine and is re-derived per invocation.

WHY THIS PERSISTS WHEN `/group-em`'s ANTI-SCOPE FORBIDS DURABLE STATE. That rule
bars a Driver REGISTRY -- a standing record of who coordinates whom, rebuilt from
peer facts. This record holds no peer facts at all: one session id, one repo, one
timestamp, written by the session about itself. It exists because the mode's whole
value is legibility from OUTSIDE the session -- the PM has to be able to see which
window is the channel without asking, and a mode nothing records is a mode the PM
must remember. That is the identical carve-out the Group EM record already won, and
this file follows its conventions deliberately rather than inventing a second
shape (`group-em-nomination.py` -- same settings-home root, same `repo_key` stem,
same atomic swap, same last-writer-wins). The three shared primitives come from
`coordinator_core.group_em.atomic_record`, the same module
`group-em-nomination.py` and `navi-singleton.py` import.

LAST WRITER WINS, and entry never refuses. A stale record outlives the session
that earned it exactly as a nomination does, so refusing over an incumbent turns a
legibility aid into a lock that needs a human. `who` reports liveness; it does not
enforce it.

NEVER RAISES ON READ. A missing settings home, an unreadable record, or a
truncated write all resolve to "no holder" -- the statusline reads this on a hot
path and must degrade to less output, never a traceback.

Cold path — one process, one call. Direct in-process import
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C7.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1


def _resolve_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em import atomic_record

    return atomic_record


def _record_path(atomic_record, repo_root: str) -> Path:
    return atomic_record.settings_home() / "state" / "uhura" / f"{atomic_record.repo_key(repo_root)}.json"


def read_record(atomic_record, repo_root: str) -> Optional[dict[str, Any]]:
    """The current holder record, or None. Never raises.

    A record from a FUTURE schema version reads as no-holder rather than as a
    holder with unknown fields: this is the input to a colour decision, and
    rendering scarlet off a record whose shape you cannot interpret asserts a
    channel exists on evidence you did not understand.
    """
    try:
        path = _record_path(atomic_record, repo_root)
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            return None
        if int(record.get("schema_version") or 0) > SCHEMA_VERSION:
            return None
        return record
    except Exception:  # noqa: BLE001
        return None


def enter(atomic_record, repo_root: str, session_id: str,
          peer_name: Optional[str] = None) -> dict[str, Any]:
    """Take the channel for this repo. Never refuses over an incumbent; a write failure
    still raises -- returns the written record only on success."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "peer_name": peer_name,
        "entered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _record_path(atomic_record, repo_root)
    atomic_record.write_json_atomic(path, record)
    return record


def stand_down(atomic_record, repo_root: str, session_id: str) -> bool:
    """Release the channel iff THIS session holds it. True when a record was removed.

    Scoped to the caller deliberately: a session that stands another session's
    channel down leaves the fleet believing there is no channel while a live
    session still thinks it is the channel, which is worse than a stale record.
    """
    record = read_record(atomic_record, repo_root)
    if not record:
        return False
    held_by = str(record.get("session_id") or "")
    if not session_id or not held_by or held_by != session_id:
        return False
    path = _record_path(atomic_record, repo_root)
    try:
        path.unlink()
        return True
    except OSError:
        return False


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("verb", choices=["enter", "who", "stand-down"])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--name")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    repo = os.path.abspath(args.repo)

    try:
        atomic_record = _resolve_module()
    except Exception as exc:  # noqa: BLE001
        print(f"uhura-mode: engine unresolvable — {exc}", file=sys.stderr)
        return 1

    if args.verb == "who":
        record = read_record(atomic_record, repo)
        if args.json:
            print(json.dumps({"holder": record}, sort_keys=True))
        elif record:
            who = record.get("peer_name") or record.get("session_id")
            print(f"Uhura: {who} since {record.get('entered_at')}")
        else:
            print("Uhura: no channel held for this repo")
        return 0

    if not args.session_id:
        parser.error(f"--session-id is required for `{args.verb}`")

    if args.verb == "enter":
        record = enter(atomic_record, repo, args.session_id, args.name)
        print(json.dumps({"entered": record}, sort_keys=True) if args.json
              else f"Uhura channel held by {args.name or args.session_id}")
        return 0

    released = stand_down(atomic_record, repo, args.session_id)
    print(json.dumps({"released": released}) if args.json
          else ("Uhura channel released" if released
                else "not the holder; nothing released"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
