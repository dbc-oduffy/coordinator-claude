# is serialized field-for-field, mirroring the JSON-RPC op veneers
#   0  -- a successful resolution attempt, INCLUDING a `not_reachable`
#   3  -- _TRANSPORT_FAIL: the engine root could not be resolved, the
#         to stderr in the same terse register as the other _TRANSPORT_FAIL
from __future__ import annotations
"""session-reachability-cli — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes THIS triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as session-liveness-cli / archive-stamp-cli / session-claim-cli)."""

import json
import os
import sys

_TRANSPORT_FAIL = 3


def _import_modules():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.session.reachability as reachability_mod
    import coordinator_core.session.peer_roster as peer_roster_mod
    import coordinator_core.session.artifact_owner as artifact_owner_mod
    import coordinator_core.session.messaging_gate as messaging_gate_mod

    return reachability_mod, peer_roster_mod, artifact_owner_mod, messaging_gate_mod


_SUBCOMMANDS = "subcommands: resolve-address | peer-roster | artifact-owner"

_HELP_FLAGS = ("--help", "-h", "help")


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _emit(payload: dict) -> int:
    print(json.dumps(payload))
    return 0


def _candidate_to_dict(candidate) -> dict:
    return {
        "session_id": candidate.session_id,
        "name": candidate.name,
        "ref": candidate.ref,
        "address": candidate.address,
    }


def _resolve_result_to_dict(result, messaging_gate_mod) -> dict:
    return {
        "outcome": result.outcome,
        "session_id": result.session_id,
        "address": result.address,
        "reason": result.reason,
        "candidates": [_candidate_to_dict(c) for c in result.candidates],
        "caller_messaging_gate": messaging_gate_mod.to_dict(messaging_gate_mod.classify()),
    }


def _peer_row_to_dict(row) -> dict:
    return {
        "session_id": row.session_id,
        "address": row.address,
        "name": row.name,
        "ref": row.ref,
        "cwd": row.cwd,
        "status": row.status,
        "running_seconds": row.running_seconds,
        "is_self": row.is_self,
        "self_determination": row.self_determination,
        "messaging_available": row.messaging_available,
    }


def _owner_resolution_to_dict(resolution) -> dict:
    result = resolution.result
    return {
        "session_id": resolution.owner.session_id,
        "source_field": resolution.owner.source_field,
        "outcome": result.outcome,
        "resolved_session_id": result.session_id,
        "address": result.address,
        "claim_live": resolution.owner.claim_live,
        "claim_stage": resolution.owner.claim_stage,
        "candidates": [_candidate_to_dict(c) for c in result.candidates],
    }


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("session-reachability-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: session-reachability-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    try:
        (
            reachability_mod,
            peer_roster_mod,
            artifact_owner_mod,
            messaging_gate_mod,
        ) = _import_modules()
    except RuntimeError as exc:
        print(f"session-reachability-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"session-reachability-cli: coordinator_core.session reachability modules not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if subcmd == "resolve-address":
        if len(rest) != 1:
            return _usage("session-reachability-cli resolve-address <session_id>")
        session_id = rest[0]
        try:
            result = reachability_mod.resolve_address(session_id)
        except Exception as exc:
            print(f"session-reachability-cli: resolve-address: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        return _emit(_resolve_result_to_dict(result, messaging_gate_mod))

    if subcmd == "peer-roster":
        repo_root = None
        args = list(rest)
        if args and args[0] == "--repo":
            if len(args) != 2:
                return _usage("session-reachability-cli peer-roster [--repo <repo_root>]")
            repo_root = args[1]
        elif args:
            return _usage("session-reachability-cli peer-roster [--repo <repo_root>]")
        try:
            rows = peer_roster_mod.build_roster(repo_root, raise_on_failure=True)
        except Exception as exc:
            print(f"session-reachability-cli: peer-roster: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        return _emit({"rows": [_peer_row_to_dict(r) for r in rows]})

    if subcmd == "artifact-owner":
        if len(rest) != 1:
            return _usage("session-reachability-cli artifact-owner <artifact_path>")
        artifact_path = rest[0]
        try:
            result = artifact_owner_mod.resolve_artifact_owner(artifact_path)
        except Exception as exc:
            print(f"session-reachability-cli: artifact-owner: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        return _emit(
            {
                "artifact_path": result.artifact_path,
                "owners": [_owner_resolution_to_dict(o) for o in result.owners],
                "file_error": result.file_error,
            }
        )

    print(f"session-reachability-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-reachability-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
