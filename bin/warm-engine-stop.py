#!/usr/bin/env python3
"""warm-engine-stop.py — the operator hatch that takes down the warm pair
(supervisor, front door, then server) of the clone this file lives in.

Spec backlink: docs/plans/2026-10-25-publish-stops-warm-pair-and-blocks-respawn.md (C3);
originally AC9a of the warm-engine plan
(`docs/plans/2026-08-15-warm-engine-retires-the-per-invocation-cold-start.md`).

COLD-PATH RULE: this script is RUNNABLE, never a slash command. It must
work with no Claude Code session, no coordinator plane, nothing but a plain
interpreter (guard: `coordinator/tests/test_cold_path_remediation_is_runnable.py`):
naked argparse, no imported session/agent surface, every diagnostic a plain string.

INVOCATION BINDS TO THE CLONE THIS FILE LIVES IN. There is no `--engine-root`
flag: `_REPO_ROOT` is this script's own containing clone, so the copy shipped
inside the klabauter clone stops THAT clone's pair:

    python3 <klabauter-clone-root>/coordinator/bin/warm-engine-stop.py

IDENTIFICATION AND MECHANISM live in `coordinator_core.warm.pair_stop.
stop_warm_pair`: the supervisor is stopped first, then the front door, then the server (graceful
ask, then a direct signal), and a final exact-argv command-line sweep under
the engine root decides success.

EXIT CODES: 0 when neither process survives ("stopped", or "no warm engine running for <root>"
plus any servers running from other roots, when no process was found; "nothing to stop" when psutil is not importable and warmth is disabled
by configuration); `_EXIT_COULD_NOT_STOP` (4) otherwise, with every
survivor's pid and role on stderr; `_EXIT_PSUTIL_MISSING` (5) when warmth is
on and psutil is not importable (one-line stderr message, no traceback).

Negative-spec:
  - Never signals a pid that a verified record or the exact command-line match
    did not identify; there is no "kill anything python-ish" fallback.
  - Never claims success while a survivor remains.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent


_BOOTSTRAP_DONE = False


_BOOTSTRAPPED_NAMES = ("pair_stop",)


def _bootstrap_engine() -> None:
    """Put `_REPO_ROOT` on `sys.path` and bind `pair_stop` -- idempotent.

    Trap: runs on first use, never at import, so importing this file does not
    mutate the `sys.path` of a warm server ~50 sessions share.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    from coordinator_core.warm import pair_stop

    _resolved = locals()
    for _name in _BOOTSTRAPPED_NAMES:
        if _name not in globals() and _name in _resolved:
            globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_EXIT_OK = 0
_EXIT_COULD_NOT_STOP = 4
_EXIT_PSUTIL_MISSING = 5


#: Twin of `coordinator_core.warm.server.DUMP_REQUEST_FILENAME` (pinned equal by test).
_DUMP_REQUEST_FILENAME = "dump-request"
_DUMP_WAIT_SECS = 0.5


def _request_server_dump(wait_secs: float = _DUMP_WAIT_SECS) -> bool:
    """Ask the live server for an all-threads record in `<svc>/stall-dumps/` via a
    request file its `dump-request-poll` thread answers by deleting it. Bounded at
    `wait_secs`; the caller stops the pair regardless. Never raises.

    Trap: the request write is itself unbounded on a stalled svc dir, and with no live
    server nothing acks, so a stop with no server pays the full `wait_secs`."""
    import time

    from coordinator_core.warm import breadcrumb

    try:
        request = breadcrumb.svc_dir(_REPO_ROOT) / _DUMP_REQUEST_FILENAME
        request.parent.mkdir(parents=True, exist_ok=True)
        request.write_text("", encoding="utf-8")
    except Exception:  # noqa: BLE001
        return False
    deadline = time.monotonic() + wait_secs
    acked = False
    while True:
        try:
            if not request.exists():
                acked = True
                break
        except OSError:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.02)
    if not acked:
        try:
            request.unlink(missing_ok=True)
        except OSError:
            pass
    return acked


def _stop_other_root_servers(others) -> int:
    """Stop the pair under every root in `others` (`(pid, root)` from
    `find_servers_under_other_roots`); exit code 0 when none survives, else `_EXIT_COULD_NOT_STOP`.

    Identity: the listed pid matched the exact `coordinator_core/warm/server.py` command line
    under that root. The root's breadcrumb is read as well: a live breadcrumb pid that is not
    the listed pid is another server of that root and is kept, never signalled.
    """
    from coordinator_core.warm import breadcrumb

    rc = _EXIT_OK
    for root in sorted({r for _pid, r in others}):
        listed = {pid for pid, r in others if r == root}
        crumb = pair_stop._record_pid(breadcrumb.read_breadcrumb(Path(root)))
        keep = frozenset({crumb[0]} - listed) if crumb is not None else frozenset()
        identity = "breadcrumb" if crumb is not None and crumb[0] in listed else "command-line"
        print(
            f"  stopping warm pair from {root} (pids {sorted(listed)}, identity={identity})",
            file=sys.stderr,
        )
        result = pair_stop.stop_warm_pair(Path(root), keep_pids=keep)
        if not result.ok():
            print(result.render_survivors(), file=sys.stderr)
            rc = _EXIT_COULD_NOT_STOP
    return rc


def main(argv=None) -> int:
    _bootstrap_engine()
    parser = argparse.ArgumentParser(
        description=(
            "Stop the warm supervisor, front door and server for the clone this script "
            "lives in. No arguments: the engine root is this clone."
        )
    )
    parser.add_argument(
        "--stop-other-roots",
        action="store_true",
        help=(
            "Also stop warm servers running from any other root (a publish clone, a moved "
            "tree), each identified by its exact server.py command line and its breadcrumb."
        ),
    )
    args = parser.parse_args(argv)

    from coordinator_core.warm import settings

    try:
        import psutil  # noqa: F401
    except ImportError:
        if not settings.is_warm_enabled():
            print("nothing to stop", file=sys.stderr)
            return _EXIT_OK
        print(
            f"warm-engine-stop: psutil is not importable under {sys.executable}",
            file=sys.stderr,
        )
        return _EXIT_PSUTIL_MISSING

    _request_server_dump()
    result = pair_stop.stop_warm_pair(_REPO_ROOT)
    if result.ok():
        if result.stopped:
            print("stopped", file=sys.stderr)
        else:
            print(f"no warm engine running for {_REPO_ROOT}", file=sys.stderr)
        others = (
            pair_stop.find_servers_under_other_roots(_REPO_ROOT)
            if args.stop_other_roots or not result.stopped
            else []
        )
        if args.stop_other_roots and others:
            for pid, root in others:
                print(f"  warm server pid={pid} is running from {root}", file=sys.stderr)
            return _stop_other_root_servers(others)
        if not result.stopped:
            for pid, root in others:
                print(f"  warm server pid={pid} is running from {root}", file=sys.stderr)
            if others:
                print("  stop them: warm-engine-stop.py --stop-other-roots", file=sys.stderr)
        return _EXIT_OK

    print(result.render_survivors(), file=sys.stderr)
    return _EXIT_COULD_NOT_STOP


if __name__ == "__main__":
    sys.exit(main())
