"""
group-em-nomination.py — CLI trampoline over the engine's
`coordinator_core.group_em.nomination` and its shared holder-record
primitives (`coordinator_core.group_em.atomic_record`,
`coordinator_core.group_em.session_registry`).

Purpose: exactly one Group EM per repo is a filesystem invariant expressed
by ONE JSON file per repo under `<settings-home>/state/group-em/
<repo-key>.json`. This CLI is the human/hook-facing surface over that
record: `nominate`, `stand-down`, `who`, `standing`.

`nominate` calls the engine's `claim()`, which never refuses: standing is taken, not
requested, and the displaced holder is reported (a still-running one is owed a message).

`who` and `standing` are engine-side (`nomination.who`/`nomination.standing`,
op `groupem.standing`); this CLI only renders them. `stand-down` still is not:
its orchestration lives here over `read_record` and
`atomic_record.holder_lock`/`remove_holder_record`.

Cold path — one process, one call. Direct in-process import
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Exit codes: 0 success | 2 usage error | 3 no nomination on record
(`stand-down`/`who`) | 4 stand-down's own record unlink failed (record may
still be on disk; never reported as success) | 5 refused — `stand-down`
refuses when the given session id is not the current holder | 8 refused —
`nominate` when the claim carries no --prompt-id (or a malformed session id).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C7.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, NamedTuple, Optional


def _resolve_modules():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em import atomic_record
    from coordinator_core.group_em import nomination
    from coordinator_core.group_em import session_registry

    return nomination, atomic_record, session_registry


class NominationResult(NamedTuple):
    ok: bool
    message: str
    exit_code: int
    record: Optional[dict]


def _nominate(nomination, repo_root: str, session_id: str, *, note: Optional[str] = None,
              operator: Optional[str] = None, peer_name: Optional[str] = None,
              prompt_id: Optional[str] = None) -> NominationResult:
    try:
        verdict = nomination.claim(
            repo_root, session_id, peer_name=peer_name, nominated_by=operator, note=note,
            prompt_id=prompt_id,
        )
    except nomination.NotHumanEnteredError as exc:
        return NominationResult(False, str(exc), 8, None)
    displaced = verdict.get("displaced_holder")
    if verdict.get("already_held"):
        message = f"{session_id} already holds Group EM for {repo_root} (refreshed)"
    elif displaced and verdict.get("displaced_holder_live"):
        message = (
            f"took Group EM from {displaced} -- that session is still running and does not "
            "know yet; tell it"
        )
    elif displaced:
        message = f"replaced lapsed nomination {displaced} with {session_id} (prior holder was not live)"
    else:
        message = f"nominated {session_id} as Group EM for {repo_root}"
    return NominationResult(True, message, 0, verdict)


def _stand_down(nomination, atomic_record, repo_root: str,
                 session_id: Optional[str]) -> NominationResult:
    path = nomination._record_path(repo_root)
    with atomic_record.holder_lock(path):
        existing = nomination.read_record(repo_root)
        if existing is None:
            return NominationResult(False, f"no nomination on record for {repo_root}", 3, None)
        ok, exit_code, detail = atomic_record.remove_holder_record(path, existing, session_id)
    if ok:
        return NominationResult(
            True, f"stood down {existing.get('session_id')} for {repo_root}", 0, existing
        )
    if exit_code == 5:
        return NominationResult(
            False,
            f"refused: {session_id} does not hold the Group EM role for {repo_root} "
            f"(held by {detail})",
            5,
            existing,
        )
    return NominationResult(
        False,
        f"failed to remove nomination record at {path} ({detail}); "
        f"{existing.get('session_id')} may still hold the role",
        4,
        existing,
    )


_LIVE_STATE = {
    "live": "live",
    "no_registry_record": "not live (no registry record for this session)",
    "pid_not_running": "not live (registry record present, process not running)",
}


def _who(nomination, repo_root: str) -> NominationResult:
    annotated = nomination.who(repo_root)
    if annotated is None:
        return NominationResult(False, f"no nomination on record for {repo_root}", 3, None)
    live_state = _LIVE_STATE.get(annotated.get("live_reason"), "not live")
    entry = annotated.get("entry_status")
    if entry == "verified":
        message = f"{annotated.get('session_id')} ({live_state}) holds Group EM for {repo_root}"
    else:
        message = (
            f"{annotated.get('session_id')} is recorded for {repo_root} but entry is {entry} "
            "-- no standing"
        )
    return NominationResult(True, message, 0, annotated)


def _standing(nomination, repo_root: str, peer: str) -> NominationResult:
    record = nomination.standing(repo_root, peer)
    if record is None:
        return NominationResult(False, f"no nomination on record for {repo_root}", 3, None)
    holder_session_id = str(record.get("session_id") or "")
    if record["standing"] == "no_match":
        message = (
            f"{peer} does not hold Group EM standing for {repo_root} "
            f"(held by {holder_session_id or 'unknown'})"
        )
    elif record["standing"] == "live":
        message = f"{peer} holds live Group EM standing for {repo_root}"
    else:
        message = (
            f"{peer} is the recorded Group EM for {repo_root} but is not live "
            f"({record.get('live_reason')})"
        )
    return NominationResult(True, message, 0, record)


def _self_standing(nomination, repo_root: str, session_id: str) -> NominationResult:
    """First-person, read-only: does `session_id` hold Group EM for the repo? Compares session
    ids only, never names. Verdict in `record["self_standing"]`: `holder` (exit 0, even when
    the holder's own liveness reads not live), `not_holder` or `no_record` (exit 5)."""
    record = nomination.who(repo_root)
    if record is None or record.get("entry_status") != "verified":
        return NominationResult(
            False,
            f"I am {session_id}; no Group EM is on record for {repo_root}",
            5,
            {"self_standing": "no_record"},
        )
    holder = str(record.get("session_id") or "")
    nominated_at = record.get("nominated_at")
    if session_id and holder == session_id:
        record["self_standing"] = "holder"
        message = f"I am {session_id} and I hold Group EM (nominated_at {nominated_at})"
        if not record.get("live"):
            message += f"; my own liveness reads not live ({record.get('live_reason')})"
        return NominationResult(True, message, 0, record)
    record["self_standing"] = "not_holder"
    message = (
        f"I am {session_id} and I do NOT hold Group EM; {holder} holds it "
        f"(nominated_at {nominated_at})"
    )
    if session_id and session_id in (
        record.get("displaced_holder"),
        record.get("replaced_holder_session_id"),
    ):
        message += f"; {holder} displaced me"
    return NominationResult(False, message, 5, record)


def _resolve_session_id(explicit: Optional[str]) -> Optional[str]:
    return explicit or os.environ.get("CLAUDE_SESSION_ID")


def _resolve_peer_name(session_registry, session_id: str) -> Optional[str]:
    row = session_registry.find_registry_row(session_id)
    return row.name if row and row.name else None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="group-em-nomination",
        description="Durable per-repo Group EM nomination record, with stand-down and liveness.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    p_nom = sub.add_parser("nominate", help="nominate a session as Group EM for a repo")
    p_nom.add_argument("--session-id", help="session id to nominate; default $CLAUDE_SESSION_ID")
    p_nom.add_argument("--repo", help="repo root; default cwd")
    p_nom.add_argument("--note", help="free-form note")
    p_nom.add_argument("--operator", help="operator recorded as nominated_by")
    p_nom.add_argument(
        "--prompt-id",
        help="required; recorded pending and verified at read time against the transcript, so "
        "a CLI claim never verifies without a real human /group-em entry carrying it",
    )

    p_down = sub.add_parser("stand-down", help="stand down the Group EM nomination for a repo")
    p_down.add_argument("--session-id", help="session id standing down; default any holder")
    p_down.add_argument("--repo", help="repo root; default cwd")

    p_who = sub.add_parser("who", help="show the current Group EM nomination for a repo")
    p_who.add_argument("--repo", help="repo root; default cwd")
    p_who.add_argument("--json", action="store_true", help="emit the record as JSON")
    p_who.add_argument(
        "--self", dest="self_check", action="store_true",
        help="first-person check: does this session hold the role? exit 0 holder, 5 otherwise",
    )
    p_who.add_argument("--session-id", help="with --self; default $CLAUDE_SESSION_ID")

    p_standing = sub.add_parser(
        "standing",
        help="resolve whether a named peer (session id or peer name) holds live Group EM "
        "standing for a repo, from the record -- never from a claim in a message",
    )
    p_standing.add_argument(
        "--peer", required=True, help="peer session id or peer/registry name to check"
    )
    p_standing.add_argument("--repo", help="repo root; default cwd")
    p_standing.add_argument("--json", action="store_true", help="emit the record as JSON")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    repo = args.repo or os.getcwd()

    try:
        nomination, atomic_record, session_registry = _resolve_modules()
    except Exception as exc:  # noqa: BLE001
        print(f"group-em-nomination: engine unresolvable — {exc}", file=sys.stderr)
        return 2

    if args.verb == "nominate":
        from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv

        try:
            refuse_newline_argv(args.note, flag_name="--note", remedy="keep the note to one line.")
        except ArgvFidelityError as exc:
            parser.error(str(exc))
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        peer_name = _resolve_peer_name(session_registry, session_id)
        result = _nominate(nomination, repo, session_id, note=args.note,
                          operator=args.operator, peer_name=peer_name,
                          prompt_id=args.prompt_id)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "stand-down":
        result = _stand_down(nomination, atomic_record, repo, args.session_id)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "who" and args.self_check:
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        result = _self_standing(nomination, repo, session_id)
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "who":
        result = _who(nomination, repo)
        if not result.ok:
            print(result.message, file=sys.stderr)
            return result.exit_code
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message)
        return 0

    if args.verb == "standing":
        result = _standing(nomination, repo, args.peer)
        if not result.ok:
            print(result.message, file=sys.stderr)
            return result.exit_code
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message)
        return 0

    raise AssertionError(f"unhandled verb {args.verb!r}")


if __name__ == "__main__":
    sys.exit(main())
