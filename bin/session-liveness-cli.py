# session-liveness-cli — CLI trampoline over claude-klabauter
# coordinator_core.session.liveness (the two-layer session/claim liveness
# module: is_session_live / session_live / claim_holder_live /
# claim_held_by_me / active_sessions / live_session_ids). Direct-import
# variant, mirroring coordinator/bin/session-claim-cli's resolve/import/
# dispatch/exit shape (2026-07-21 liveness-trampoline-flip, sibling of the
# same-day claim-lock-trampoline-flip).
#
# Subcommands (argv[1] selects; remaining argv forwarded to the mapped
# coordinator_core.session.liveness function):
#   is-session-live <pid> <elapsed_sec>       -> liveness.is_session_live(...)     bool->exit
#   session-live <sid>                        -> liveness.session_live(...) for the exit
#                                                 code (AC1: boolean contract unchanged,
#                                                 unmigrated), plus liveness.session_verdict(...)
#                                                 (read-only, for stdout text alone) to name
#                                                 the state explicitly: prints one of
#                                                 "live (<basis>)", "live-elsewhere[: <cwd>]",
#                                                 "dead (<basis>)", "unknown" -- no arm exits
#                                                 silently (C2, docs/plans/2026-08-13-liveness-
#                                                 stops-conflating-dead-with-elsewhere.md, AC4).
#   claim-holder-live <claim_dir>             -> liveness.claim_holder_live(...)  bool->exit
#   claim-held-by-me <claim_dir> [my_sid]     -> liveness.claim_held_by_me(...)   bool->exit
#   active-sessions                           -> liveness.active_sessions(): prints one
#                                                 formatted line per session (or the
#                                                 bash-parity placeholder lines), exit 0
#   live-session-ids                          -> liveness.live_session_ids(): prints one
#                                                 sid per line, SORTED for determinism
#                                                 (mirrors js_bridge_cli's live-session-ids
#                                                 sort rationale — directory-enumeration
#                                                 order was never a contract), exit 0
#   incident-claim <key> [--note TEXT] [--repo PATH] [--release]
#                                             -> incident_claims.set_claim / release_claim:
#                                                 prints one line per OTHER live holder of the
#                                                 key, exit 0 whether or not peers exist
#   incident-peers [<key>] [--repo PATH]      -> incident_claims.list_peers: prints one line per
#                                                 live holder (self included)
#   Peer line: "<session_id> <address|unreachable> <claimed_at> <key> -- <note>". --repo defaults
#   to core.git_root() of the cwd. A key refusal or unresolvable session id exits 2; a
#   peer never changes the exit code.
#
# Exit codes: the mapped bool-returning functions map True->0, False->1 (matches
# session-claim-cli's convention). The two print-returning subcommands
# (active-sessions, live-session-ids) always exit 0 on success. A missing/
# unresolvable engine root or an ImportError (this trampoline's own transport
# failure) exits 3 (_TRANSPORT_FAIL — "the claude-klabauter engine could not be reached,"
# never silently degraded to 0/1). A usage error (missing/unknown subcommand,
# wrong arity) exits 2.
#
# session-live only (C2): 0 and 1 keep their EXACT existing meanings ("live in
# THIS repo" / "not confirmed live in this repo") for every existing caller
# that branches on them -- never repurposed. A session confirmed live in
# ANOTHER repo (C1's "harness-registry-elsewhere" verdict) is a state no
# existing caller's 0/1 branching distinguishes today, so it gets its own new
# code, 4 (_EXIT_LIVE_ELSEWHERE), rather than silently folding into 1 the way
# it used to. A caller doing a plain `== 0` or `!= 0` check is unaffected
# either way, since "elsewhere" was already nonzero before this change.
from __future__ import annotations
"""session-liveness-cli — see the # comment block above for the RAG-bait purpose
text (the polyglot shebang line above makes THIS triple-quoted string a
silently-discarded expression statement, not the module __doc__ — same
convention as archive-stamp-cli / session-claim-cli)."""

import os
import sys

_TRANSPORT_FAIL = 3
_EXIT_LIVE_ELSEWHERE = 4


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.session.liveness as _mod

    return _mod


_SUBCOMMANDS = (
    "subcommands: is-session-live | session-live | claim-holder-live | "
    "claim-held-by-me | active-sessions | live-session-ids | incident-claim | "
    "incident-peers"
)

_HELP_FLAGS = ("--help", "-h", "help")


def _import_incident():
    import coordinator_core.session.core as _core
    import coordinator_core.session.incident_claims as _ic

    return _core, _ic


def _parse_incident_args(rest: list[str], *, positional_max: int, flags: dict[str, bool]):
    """Returns (positionals, options) or None on a usage error. flags maps option -> takes_value."""
    pos: list[str] = []
    opts: dict[str, object] = {}
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in flags:
            if flags[arg]:
                if i + 1 >= len(rest):
                    return None
                opts[arg] = rest[i + 1]
                i += 2
                continue
            opts[arg] = True
        elif arg.startswith("--"):
            return None
        else:
            pos.append(arg)
        i += 1
    if len(pos) > positional_max:
        return None
    return pos, opts


def _peer_line(h) -> str:
    return f"{h.session_id} {h.address or 'unreachable'} {h.claimed_at} {h.key} -- {h.note}"


def _run_incident(subcmd: str, rest: list[str]) -> int:
    prog = f"session-liveness-cli {subcmd}"
    if subcmd == "incident-claim":
        parsed = _parse_incident_args(
            rest, positional_max=1, flags={"--note": True, "--repo": True, "--release": False}
        )
        if parsed is None or len(parsed[0]) != 1:
            return _usage(f"{prog} <key> [--note TEXT] [--repo PATH] [--release]")
    else:
        parsed = _parse_incident_args(rest, positional_max=1, flags={"--repo": True})
        if parsed is None:
            return _usage(f"{prog} [<key>] [--repo PATH]")
    pos, opts = parsed
    try:
        core, ic = _import_incident()
    except (RuntimeError, ImportError) as exc:
        print(f"session-liveness-cli: incident_claims not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    if subcmd == "incident-claim":
        from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv

        try:
            refuse_newline_argv(opts.get("--note"), flag_name="--note", remedy="keep the note to one line.")
        except ArgvFidelityError as exc:
            print(f"session-liveness-cli: {subcmd}: {exc}", file=sys.stderr)
            return 2
    repo = opts.get("--repo") or core.git_root()
    if not repo:
        print(f"session-liveness-cli: {subcmd}: not in a git repo; pass --repo", file=sys.stderr)
        return 2
    try:
        if subcmd == "incident-claim":
            if opts.get("--release"):
                ic.release_claim(repo, pos[0])
                return 0
            result = ic.set_claim(repo, pos[0], opts.get("--note"))
            holders = result.peers
        else:
            holders = ic.list_peers(repo, pos[0] if pos else None)
    except ValueError as exc:
        print(f"session-liveness-cli: {subcmd}: {exc}", file=sys.stderr)
        return 2
    for h in holders:
        print(_peer_line(h))
    return 0


def _usage(prog: str) -> int:
    print(f"usage: {prog} <subcommand> <args...>\n{_SUBCOMMANDS}", file=sys.stderr)
    return 2


def _bool_to_exit(result: bool) -> int:
    return 0 if result else 1


def main(argv: list[str]) -> int:
    if not argv:
        return _usage("session-liveness-cli")
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(f"usage: session-liveness-cli <subcommand> <args...>\n{_SUBCOMMANDS}")
        return 0

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"session-liveness-cli: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"session-liveness-cli: coordinator_core.session.liveness not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    if subcmd == "is-session-live":
        if len(rest) != 2:
            return _usage("session-liveness-cli is-session-live <pid> <elapsed_sec>")
        pid, elapsed_sec = rest
        return _bool_to_exit(mod.is_session_live(pid, elapsed_sec))

    if subcmd == "session-live":
        if len(rest) != 1:
            return _usage("session-liveness-cli session-live <sid>")
        sid = rest[0]
        live = mod.session_live(sid)
        try:
            verdict = mod.session_verdict(sid)
        except Exception:
            verdict = None
        if live:
            basis = verdict[1] if verdict else "unknown"
            print(f"live ({basis})")
            return 0
        if verdict is not None and verdict[0] and verdict[1] == "harness-registry-elsewhere":
            peer_cwd = verdict[2]
            print(f"live-elsewhere: {peer_cwd}" if peer_cwd else "live-elsewhere")
            return _EXIT_LIVE_ELSEWHERE
        if verdict is not None and not verdict[0]:
            print(f"dead ({verdict[1]})")
            return 1
        print("unknown")
        return 1

    if subcmd == "claim-holder-live":
        if len(rest) != 1:
            return _usage("session-liveness-cli claim-holder-live <claim_dir>")
        try:
            return _bool_to_exit(mod.claim_holder_live(rest[0]))
        except ValueError as exc:
            print(f"session-liveness-cli: claim-holder-live: {exc}", file=sys.stderr)
            return 2

    if subcmd == "claim-held-by-me":
        if len(rest) not in (1, 2):
            return _usage("session-liveness-cli claim-held-by-me <claim_dir> [my_sid]")
        claim_dir = rest[0]
        my_sid = rest[1] if len(rest) > 1 else ""
        try:
            return _bool_to_exit(mod.claim_held_by_me(claim_dir, my_sid))
        except ValueError as exc:
            print(f"session-liveness-cli: claim-held-by-me: {exc}", file=sys.stderr)
            return 2

    if subcmd == "active-sessions":
        for line in mod.active_sessions():
            print(line)
        return 0

    if subcmd == "live-session-ids":
        for sid in sorted(mod.live_session_ids()):
            print(sid)
        return 0

    if subcmd in ("incident-claim", "incident-peers"):
        return _run_incident(subcmd, rest)

    print(f"session-liveness-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-liveness-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
