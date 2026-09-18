"""
group-em-nomination.py — CLI trampoline over the engine's
`coordinator_core.group_em.nomination` and its shared holder-record
primitives (`coordinator_core.group_em.atomic_record`,
`coordinator_core.group_em.session_registry`).

Purpose: exactly one Group EM per repo is a filesystem invariant expressed
by ONE JSON file per repo under `<settings-home>/state/group-em/
<repo-key>.json`. This CLI is the human/hook-facing surface over that
record: `nominate`, `stand-down`, `who`, `standing`.

WHY `nominate` REFUSES A LIVE INCUMBENT HERE, UNLIKE THE ARCHIVED DoE
REFERENCE. The DoE-plane script this replaces documented last-writer-wins
("entry never refuses") as current policy. That policy is the exact
2026-08-30 failure `coordinator_core.group_em.nomination`'s own module
docstring exists to not repeat: a session claiming over a live incumbent
with no evidence the incumbent has exited. The engine's `claim()` — the
same function `groupem.enter` (W2-C7's sibling CLI `group-em-enter.py`)
already calls — auto-replaces ONLY a holder with POSITIVE evidence of
death (`live_reason: "pid_not_running"`), and refuses (never claims) over a
LIVE holder or one merely unaccounted for (`live_reason:
"no_registry_record"`, ambiguous on a multi-machine fleet). This CLI's
`nominate` verb calls that same `claim()` rather than reimplementing the
DoE reference's separate, more permissive policy — one nomination policy,
not two that drift. Recorded in the chunk's arrival record
(`state/audits/doe-script-arrivals/W2-C7.yaml`).

`stand-down`, `who` and `standing` have no engine-side equivalent yet (the
engine's own consumer is `groupem.enter`, which only ever claims). Their
orchestration lives here, over the same public primitives `claim()` itself
uses — `read_record`, `atomic_record.holder_lock`/`remove_holder_record`,
`session_registry.find_registry_row`/`liveness_annotation` — never a
second copy of the record shape or the liveness join.

Cold path — one process, one call. Direct in-process import
(`lib` bootstrap, `require_dispatch_engine_on_path`), same trampoline shape
`coordinator/bin/group-em-watch.py` uses.

Exit codes: 0 success | 2 usage error | 3 no nomination on record
(`stand-down`/`who`) | 4 stand-down's own record unlink failed (record may
still be on disk; never reported as success) | 5 refused — `nominate`
refuses a live/unaccounted-for incumbent; `stand-down` refuses when the
given session id is not the current holder.

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
              peer_name: Optional[str] = None) -> NominationResult:
    verdict = nomination.claim(repo_root, session_id, peer_name=peer_name, nominated_by=note)
    if not verdict.get("claimed"):
        incumbent = verdict.get("superseded_incumbent") or {}
        return NominationResult(
            False,
            f"refused: incumbent {incumbent.get('session_id', 'unknown')} "
            f"[{incumbent.get('live_reason', 'unknown')}] holds this repo's nomination",
            5,
            verdict,
        )
    if verdict.get("already_held"):
        message = f"{session_id} already holds Group EM for {repo_root} (refreshed)"
    elif verdict.get("replaced_holder"):
        replaced = verdict["replaced_holder"]
        message = (
            f"replaced lapsed nomination {replaced.get('session_id')} with {session_id} "
            "(prior holder was not live)"
        )
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


def _who(nomination, session_registry, repo_root: str) -> NominationResult:
    record = nomination.read_record(repo_root)
    if record is None:
        return NominationResult(False, f"no nomination on record for {repo_root}", 3, None)
    live, live_reason, live_state = session_registry.liveness_annotation(record)
    annotated = dict(record)
    annotated["live"] = live
    annotated["live_reason"] = live_reason
    message = f"{record.get('session_id')} ({live_state}) holds Group EM for {repo_root}"
    return NominationResult(True, message, 0, annotated)


def _session_id_for_name(session_registry, name: str) -> Optional[str]:
    if not name:
        return None
    matches = {row.session_id for row in session_registry.read_rows() if row.name == name}
    if len(matches) != 1:
        return None
    return matches.pop()


def _standing(nomination, session_registry, repo_root: str, peer: str) -> NominationResult:
    result = _who(nomination, session_registry, repo_root)
    if not result.ok:
        return result
    record = dict(result.record or {})
    holder_session_id = str(record.get("session_id") or "")
    matches = bool(peer) and (
        peer == holder_session_id
        or _session_id_for_name(session_registry, peer) == holder_session_id
    )
    if not matches:
        record["standing"] = "no_match"
        message = (
            f"{peer} does not hold Group EM standing for {repo_root} "
            f"(held by {holder_session_id or 'unknown'})"
        )
        return NominationResult(True, message, 0, record)
    if record.get("live"):
        record["standing"] = "live"
        message = f"{peer} holds live Group EM standing for {repo_root}"
    else:
        record["standing"] = "not_live"
        message = (
            f"{peer} is the recorded Group EM for {repo_root} but is not live "
            f"({record.get('live_reason')})"
        )
    return NominationResult(True, message, 0, record)


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

    p_down = sub.add_parser("stand-down", help="stand down the Group EM nomination for a repo")
    p_down.add_argument("--session-id", help="session id standing down; default any holder")
    p_down.add_argument("--repo", help="repo root; default cwd")

    p_who = sub.add_parser("who", help="show the current Group EM nomination for a repo")
    p_who.add_argument("--repo", help="repo root; default cwd")
    p_who.add_argument("--json", action="store_true", help="emit the record as JSON")

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
        session_id = _resolve_session_id(args.session_id)
        if not session_id:
            parser.error("give --session-id or set $CLAUDE_SESSION_ID")
        peer_name = _resolve_peer_name(session_registry, session_id)
        result = _nominate(nomination, repo, session_id, note=args.note, peer_name=peer_name)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "stand-down":
        result = _stand_down(nomination, atomic_record, repo, args.session_id)
        print(result.message, file=sys.stdout if result.ok else sys.stderr)
        return result.exit_code

    if args.verb == "who":
        result = _who(nomination, session_registry, repo)
        if not result.ok:
            print(result.message, file=sys.stderr)
            return result.exit_code
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message)
        return 0

    if args.verb == "standing":
        result = _standing(nomination, session_registry, repo, args.peer)
        if not result.ok:
            print(result.message, file=sys.stderr)
            return result.exit_code
        if args.json:
            print(json.dumps(result.record))
        else:
            print(result.message)
        return 0

    # Unreachable: `sub.add_parser(..., required=True)` above guarantees `args.verb` is one of
    # the verbs handled; argparse itself exits 2 before `main()` ever sees anything else.
    raise AssertionError(f"unhandled verb {args.verb!r}")


if __name__ == "__main__":
    sys.exit(main())
