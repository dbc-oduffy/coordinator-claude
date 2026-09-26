# failure) exits 3 (_TRANSPORT_FAIL — "the claude-klabauter engine could not be reached,"
# code, 4 (_EXIT_LIVE_ELSEWHERE), rather than silently folding into 1 the way
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

    print(f"session-liveness-cli: unknown subcommand {subcmd!r}", file=sys.stderr)
    return _usage("session-liveness-cli")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
