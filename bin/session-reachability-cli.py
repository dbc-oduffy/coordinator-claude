# session-reachability-cli — CLI trampoline over claude-klabauter
# coordinator_core.session.reachability / peer_roster / artifact_owner (the
# live UUID -> SendMessage-address resolver, the cwd-filtered peer roster,
# and the artifact-keyed "who's on this?" read). Direct-import variant,
# mirroring coordinator/bin/session-liveness-cli's resolve/import/dispatch/
# exit shape (same-day sibling: 2026-08-13 session-owner-reachability
# registry, opening this callable surface to sibling repos' skills that
# have no other way to reach the three ops
# `session.resolve_address`/`session.peer_roster`/`session.artifact_owner`
# already registered in `coordinator_core/ops/_registry_map.py`).
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator_core.session function):
#   resolve-address <session_id>              -> reachability.resolve_address(...)
#                                                 -- one live UUID -> SendMessage
#                                                 address, plus this session's
#                                                 own `caller_messaging_gate`
#                                                 (messaging_gate.classify()).
#   peer-roster [--repo <repo_root>]           -> peer_roster.build_roster(...)
#                                                 -- every live session whose cwd
#                                                 is within repo_root (default:
#                                                 this process's own cwd).
#   artifact-owner <artifact_path>             -> artifact_owner.resolve_artifact_owner(...)
#                                                 -- every recorded owner id on
#                                                 an artifact, each resolved
#                                                 through resolve_address().
#
# Output contract: JSON on stdout, ONE object per invocation -- deliberately
# distinct from session-liveness-cli's bool->exit convention, per the
# consuming repo's own ask (cross-repo/inbox/2026-08-13-coordinator-content-repo-em-peer-
# roster-doctrine-reply.md § Counter 1). Each subcommand's dataclass return
# is serialized field-for-field, mirroring the JSON-RPC op veneers
# (coordinator_core/ops/session_resolve_address.py,
# session_peer_roster.py, session_artifact_owner.py) exactly -- this
# trampoline direct-imports the underlying session module rather than
# going through the op registry, but the wire shape it emits is the SAME
# shape those op veneers already return, so a caller cannot tell the two
# surfaces apart from their JSON alone.
#
# Exit codes:
#   0  -- a successful resolution attempt, INCLUDING a `not_reachable`
#         outcome or an owners-less artifact read. `not_reachable` is a
#         legitimate answer, not an error (reachability.py's own module
#         docstring negative-spec) -- this trampoline never raises that to
#         a nonzero exit.
#   2  -- usage error (missing/unknown subcommand, wrong arity).
#   3  -- _TRANSPORT_FAIL: the engine root could not be resolved, the
#         coordinator_core.session.{reachability,peer_roster,artifact_owner}
#         modules were not importable, OR the wrapped
#         resolve_address/build_roster/resolve_artifact_owner call itself
#         raised at runtime (e.g. a harness_registry.snapshot() I/O error)
#         -- "the engine could not be reached" covers both the import-time
#         and the runtime-raise flavor of that failure (Review:
#         code-reviewer -- P3, exit-code table must name every state the
#         trampoline can actually reach; this table is exhaustively
#         {0, 2, 3}, never a bare uncaught traceback). The diagnostic goes
#         to stderr in the same terse register as the other _TRANSPORT_FAIL
#         paths -- stdout stays JSON-only or empty, never a stack trace
#         where a caller (e.g. a sibling repo's skill code) expects JSON.
#
# Spec backlink: cross-repo/inbox/2026-08-13-coordinator-content-repo-em-peer-roster-
# doctrine-reply.md § Counter 1, state/handoffs/2026-08-13-session-owner-
# reachability-registry.md.
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
        # Imported by name, not via artifact_owner_mod: the serializer is the
        # one shared with the op veneer, so a module stand-in must not shadow it.
        from coordinator_core.session.artifact_owner import to_dict as owner_result_to_dict

        return _emit(owner_result_to_dict(result))

    print(f"session-reachability-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-reachability-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
