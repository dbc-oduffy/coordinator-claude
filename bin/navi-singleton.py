"""
navi-singleton.py -- one-per-box Navi claim, and the in-instance poke-dedup
ledger.

Purpose: Navi is the machine-wide nudge role -- a repo-less session enumerating
every session on the box and poking the stalled ones. This CLI records the
single machine-global JSON claim under `<settings-home>/state/navi/`, on the
exact liveness shape `coordinator/bin/group-em-nomination.py` already proves
out -- last-writer-wins on claim (dead-incumbent auto-replace only; a LIVE
incumbent refuses), liveness ONLY from a registry join, never a stored pid.

Verbs: `claim`, `who`, `release` operate the singleton claim. `poke-mark` /
`poke-check` operate a SEPARATE ledger, scoped to the one instance that wrote
it, for the in-instance dedup regression (one Navi instance poking the same
peer more than once inside a single unbroken stall occurrence).

NEGATIVE SPEC -- what this deliberately does NOT do, and why:

  - The claim record MUST NOT carry a `pid`. Exactly `group-em-nomination.py`'s
    own negative spec: a pid written by the CLI subprocess is that
    subprocess's own, dead the moment the CLI exits, and reading liveness off
    it fails in the one direction a mutual-exclusion check must never fail --
    a false "not live" that lets a second Navi collide with a live one.
    Liveness comes ONLY from `session_registry.is_live`'s join: find the
    harness registry row for the claim's `session_id`, then check THAT row's
    own published `pid`. That helper is imported, never redefined here.

  - The liveness VALUE is NEVER cached, at any layer. Every `who`/`claim` call
    re-joins the registry fresh. A dead-but-unreaped claim record is the
    steady state to expect, not an anomaly to special-case.

  - There is no key-mode selector. The guard has ONE key: one per box. `--key`
    does not exist as a CLI flag.

  - The poke ledger is NOT a key inside the claim record and shares NO code
    path with it: its read never calls `is_live()`, is never subject to
    last-writer-wins displacement, and never goes through the claim's read
    guard. It is scoped to the one instance (`session_id`) that wrote each
    entry, so a repeat check from a different session id reads as
    not-yet-poked.

Both records live under `<settings-home>/state/navi/`
(`atomic_record.settings_home()`) -- machine-global, in no repo's tree.

Cold path — one process, one call. Direct in-process import
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Exit codes: 0 success | 2 usage error | 3 no claim on record (`who`/`release`
with nothing to report) | 4 unlink failed on `release` (the record, and the
mutual exclusion it represents, is still on disk) | 5 refused -- claim is LIVE
and held by another session (`claim` only; `release` refuses if given a
`--session-id` that does not match the current holder, exit 5 as well).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C7.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple, Optional

SCHEMA_VERSION = 1


def _resolve_modules():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em import atomic_record
    from coordinator_core.group_em import session_registry

    return atomic_record, session_registry


def _navi_state_dir(atomic_record) -> Path:
    return atomic_record.settings_home() / "state" / "navi"


def _claim_path(atomic_record) -> Path:
    return _navi_state_dir(atomic_record) / "singleton.json"


def _ledger_path(atomic_record) -> Path:
    return _navi_state_dir(atomic_record) / "poke-ledger.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_session_id(explicit: Optional[str]) -> Optional[str]:
    return explicit or os.environ.get("CLAUDE_SESSION_ID")


def read_claim(atomic_record, directory: Optional[Path] = None) -> Optional[dict]:
    """The claim record, or None if absent or unparseable -- never a directory scan; the path is
    deterministic (one key, one box)."""
    path = directory / "singleton.json" if directory else _claim_path(atomic_record)
    return atomic_record.read_json_tolerant(path)


class ClaimResult(NamedTuple):
    ok: bool
    message: str
    exit_code: int
    record: Optional[dict]


def claim(
    atomic_record,
    session_registry,
    session_id: str,
    *,
    peer_name: Optional[str] = None,
    note: Optional[str] = None,
    directory: Optional[Path] = None,
) -> ClaimResult:
    """Claim the one-per-box Navi singleton.

    Refuses (exit 5) when an existing claim is held by a DIFFERENT session and that session is
    LIVE right now, per the registry join -- never per a stored pid. A self-refresh (same
    `session_id` re-claiming) always succeeds. A claim held by a session that is not live is
    lapsed, not binding, and this call displaces it and reports the displacement.

    Serialized behind `atomic_record.holder_lock`: two claimants racing against no live holder
    read-check-write under the same kernel advisory lock, so only one at a time ever decides.
    """
    path = directory / "singleton.json" if directory else _claim_path(atomic_record)
    with atomic_record.holder_lock(path):
        existing = read_claim(atomic_record, directory)
        displaced_from = None

        if existing is not None:
            holder_sid = str(existing.get("session_id") or "")
            if holder_sid and holder_sid != session_id:
                live, _row = session_registry.is_live(existing)
                if live:
                    return ClaimResult(
                        False,
                        f"refused: Navi singleton is held by live session {holder_sid}",
                        5,
                        existing,
                    )
                displaced_from = holder_sid
            elif holder_sid == session_id:
                displaced_from = existing.get("displaced_from")
            else:
                displaced_from = "(malformed prior record)"

        record = {
            "version": SCHEMA_VERSION,
            "session_id": session_id,
            "peer_name": peer_name,
            "claimed_at": _now(),
            "note": note,
            "displaced_from": displaced_from,
        }
        atomic_record.write_json_atomic(path, record)
        if existing is None:
            message = f"claimed Navi singleton as {session_id}"
        elif displaced_from and displaced_from != session_id:
            message = f"claimed Navi singleton as {session_id} (prior holder {displaced_from} was not live)"
        else:
            message = f"{session_id} already holds the Navi singleton (refreshed)"
        return ClaimResult(True, message, 0, record)


def who(
    atomic_record,
    session_registry,
    *,
    directory: Optional[Path] = None,
) -> ClaimResult:
    """The current claim, with liveness resolved fresh -- never cached."""
    record = read_claim(atomic_record, directory)
    if record is None:
        return ClaimResult(False, "no Navi singleton claim on record", 3, None)
    live, live_reason, live_state = session_registry.liveness_annotation(record)
    annotated = dict(record)
    annotated["live"] = live
    annotated["live_reason"] = live_reason
    message = f"{record.get('session_id')} ({live_state}) holds the Navi singleton"
    return ClaimResult(True, message, 0, annotated)


def release(
    atomic_record,
    session_id: Optional[str] = None,
    *,
    directory: Optional[Path] = None,
) -> ClaimResult:
    """Remove the claim record.

    If `session_id` is given it must match the current holder -- a release attempt from a
    non-holder is refused (exit 5), never silently accepted. Omitting `session_id` releases
    whichever session currently holds the claim (operator override).
    """
    path = directory / "singleton.json" if directory else _claim_path(atomic_record)
    with atomic_record.holder_lock(path):
        existing = read_claim(atomic_record, directory)
        if existing is None:
            return ClaimResult(False, "no Navi singleton claim on record", 3, None)
        ok, exit_code, detail = atomic_record.remove_holder_record(path, existing, session_id)
    if ok:
        return ClaimResult(True, f"released Navi singleton held by {existing.get('session_id')}", 0, existing)
    if exit_code == 5:
        return ClaimResult(
            False,
            f"refused: {session_id} does not hold the Navi singleton (held by {detail})",
            5,
            existing,
        )
    return ClaimResult(
        False,
        f"failed to remove Navi singleton record at {path} "
        f"({detail}); {existing.get('session_id')} may still hold the claim",
        4,
        existing,
    )


# --- poke ledger -------------------------------------------------------------------------------
#
# A separate record, sharing only the record home. Each entry is keyed by (session_id, peer),
# scoped to the writing instance: an entry written by a different session_id never reads as
# poked for THIS session. No entry here is ever checked against is_live(), and nothing here
# participates in the claim's last-writer-wins displacement.


def _ledger_key(session_id: str, peer: str) -> str:
    return f"{session_id}\x1f{peer}"


def read_ledger(atomic_record, directory: Optional[Path] = None) -> dict:
    path = directory / "poke-ledger.json" if directory else _ledger_path(atomic_record)
    data = atomic_record.read_json_tolerant(path)
    if data is None or not isinstance(data.get("entries"), dict):
        return {"version": SCHEMA_VERSION, "entries": {}}
    return data


def poke_mark(
    atomic_record,
    session_id: str,
    peer: str,
    *,
    directory: Optional[Path] = None,
) -> ClaimResult:
    """Record that `session_id` poked `peer` for the current unbroken stall occurrence."""
    path = directory / "poke-ledger.json" if directory else _ledger_path(atomic_record)
    ledger = read_ledger(atomic_record, directory)
    ledger["entries"][_ledger_key(session_id, peer)] = {
        "session_id": session_id,
        "peer": peer,
        "poked_at": _now(),
    }
    atomic_record.write_json_atomic(path, ledger)
    return ClaimResult(True, f"marked {peer} as poked by {session_id}", 0, ledger["entries"][_ledger_key(session_id, peer)])


def poke_check(
    atomic_record,
    session_id: str,
    peer: str,
    *,
    directory: Optional[Path] = None,
) -> ClaimResult:
    """Whether `session_id` already poked `peer` for the current unbroken stall occurrence."""
    ledger = read_ledger(atomic_record, directory)
    entry = ledger["entries"].get(_ledger_key(session_id, peer))
    already = entry is not None
    message = (
        f"{peer} already poked by {session_id}" if already else f"{peer} not yet poked by {session_id}"
    )
    return ClaimResult(True, message, 0, {"already_poked": already, "entry": entry})


def _resolve_peer_name(session_registry, session_id: str) -> Optional[str]:
    row = session_registry.find_registry_row(session_id)
    return row.name if row and row.name else None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="navi-singleton",
        description="One-per-box Navi claim, and the in-instance poke-dedup ledger.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    p_claim = sub.add_parser("claim", help="claim the Navi singleton")
    p_claim.add_argument("--session-id", help="session id claiming; default $CLAUDE_SESSION_ID")
    p_claim.add_argument("--note", help="free-form note")

    sub.add_parser("who", help="show the current Navi singleton claim")

    p_release = sub.add_parser("release", help="release the Navi singleton claim")
    p_release.add_argument("--session-id", help="session id releasing; default any holder")

    p_mark = sub.add_parser("poke-mark", help="record a peer as poked for this stall occurrence")
    p_mark.add_argument("--session-id", help="session id marking; default $CLAUDE_SESSION_ID")
    p_mark.add_argument("--peer", required=True, help="peer session id or name poked")

    p_check = sub.add_parser("poke-check", help="ask whether a peer was already poked")
    p_check.add_argument("--session-id", help="session id asking; default $CLAUDE_SESSION_ID")
    p_check.add_argument("--peer", required=True, help="peer session id or name to check")
    p_check.add_argument("--json", action="store_true", help="emit the result as JSON")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        atomic_record, session_registry = _resolve_modules()
    except Exception as exc:  # noqa: BLE001
        print(f"navi-singleton: engine unresolvable — {exc}", file=sys.stderr)
        return 2

    if args.verb == "claim":
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        peer_name = _resolve_peer_name(session_registry, session_id)
        result = claim(atomic_record, session_registry, session_id, peer_name=peer_name, note=args.note)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "who":
        result = who(atomic_record, session_registry)
        if not result.ok:
            print(result.message, file=sys.stderr)
            return result.exit_code
        print(result.message)
        return 0

    if args.verb == "release":
        result = release(atomic_record, args.session_id)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "poke-mark":
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        result = poke_mark(atomic_record, session_id, args.peer)
        print(result.message)
        return result.exit_code

    if args.verb == "poke-check":
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        result = poke_check(atomic_record, session_id, args.peer)
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message)
        return result.exit_code

    # Unreachable: `sub.add_parser(..., required=True)` above guarantees `args.verb` is one of
    # the verbs handled; argparse itself exits 2 before `main()` ever sees anything else.
    raise AssertionError(f"unhandled verb {args.verb!r}")


if __name__ == "__main__":
    sys.exit(main())
