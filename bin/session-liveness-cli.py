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

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

_TRANSPORT_FAIL = 3
_EXIT_LIVE_ELSEWHERE = 4


def _import_module():
    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.session.liveness as _mod

    return _mod


_SUBCOMMANDS = (
    "subcommands: is-session-live | session-live | claim-holder-live | "
    "claim-held-by-me | active-sessions | live-session-ids"
)

_HELP_FLAGS = ("--help", "-h", "help")


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
        # session_live()'s boolean drives the exit code (AC1: unchanged,
        # unmigrated -- this is not a new reachability oracle, AC8). The
        # verdict below is read ONLY to pick the stdout message; it never
        # feeds the exit code.
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
        # Review: staff-eng-review Finding 1 — gate on the flag, not merely
        # on presence. The two-read window between session_live() and
        # session_verdict() (a session dir created, or Layer-2 recency
        # crossing the threshold, in between) can leave `live` False while
        # `verdict` carries a True-flagged tuple on a non-elsewhere basis;
        # printing "dead (<basis>)" over that would assert dead over a
        # verdict that says live. Only a False-flagged verdict is dead here.
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

    print(f"session-liveness-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-liveness-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
