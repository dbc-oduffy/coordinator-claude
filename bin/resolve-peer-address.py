#!/usr/bin/env python3
"""
coordinator.bin.resolve-peer-address -- resolve a session id to the peer name cross-session
messaging can actually address, at point of use.

Purpose: `claimed_by` on a handoff, `Session-Id` on a commit trailer, and `created_by_session` on a
queue entry are all SESSION IDS. `SendMessage` addresses a PEER NAME. Sessions carrying a claim get
that join for free -- a computed claim decision hands them `send_message_address` on its
`competing_claim[]` entry, and they must use that field rather than re-derive one
(`coordinator/docs/wiki/execute-plan-residue.md`). This module is for every OTHER lookup: a session
id read off a commit, a queue entry, or a plan body, where no claim decision exists to consult and
the alternative is guessing.

The registry is `~/.claude/sessions/<pid>.json` (or `$CLAUDE_CONFIG_DIR/sessions/`), one record per
live session carrying `name`, `pid`, `cwd`, `status` and `sessionId`. This module's on-disk reader
is `coordinator_core.group_em.session_registry` (ported from DoE's own `bin/lib/session_registry.py`
at W2-C1) -- the same primitive `group-em-nomination.py`, `navi-singleton.py` and `uhura-mode.py`
import, not a second copy. `coordinator_core/session/reachability.py :: resolve_advisory_address`
wraps the same join for a session carrying a computed claim decision; this module is for every
OTHER lookup, where no claim decision exists to consult.

NEGATIVE SPEC -- what this deliberately does NOT do, and why each absence is load-bearing:

  - It does NOT cache, stamp, or return an address for later replay. An address is per-process, and
    a session id churns INSIDE one session's lifetime: a resume or `/clear` mints a new `sessionId`
    while the peer name and pid persist (measured by claude-klabauter-22, 2026-08-25). A sid stamped
    forty minutes ago can resolve to nothing while its author runs on under the same name. Resolve
    at point of use, every time. A `claimed_by_name`-style stamped field was proposed, built, and
    reverted for exactly this reason (`2000aab5a`); do not reintroduce one.

  - It does NOT report `no-record` as "the session is gone". That conflation is the failure this
    tool exists to prevent, so the outcomes are kept distinct and the CLI gives them distinct exit
    codes. `--near` answers the follow-up question doctrine actually asks -- is there a live row on
    the same workstream? -- rather than leaving the caller to infer death from silence.

  - It does NOT fall back to inferring a name from `ListAgents` ordering, start times, or name
    similarity. That inference has already delivered a message to an unrelated session while the
    real holder kept working from a stale artifact. There is no heuristic arm here on purpose: when
    resolution comes back empty, the sanctioned move is to write what the holder needs into the
    artifact it is working from, not to guess.

  - It spawns NOTHING. No subprocess, no `tasklist`, no `ps`. Liveness is a direct kernel query, on
    a machine that routinely runs twenty-plus concurrent sessions and where this may be called from
    a hook path.

Exit codes: 0 resolved (name on stdout) | 3 no record for that sid | 4 record found but its process
is dead | 2 usage error.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C4.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, NamedTuple, Optional

RESOLVED = "resolved"
NO_RECORD = "no-record"
DEAD = "dead"


def _resolve_modules():
    """Bootstrap and return `coordinator_core.group_em.session_registry` -- the "engine" class
    resolution (§ Path resolution): this module's own tree, via the standard
    `require_dispatch_engine_on_path` trampoline `group-em-nomination.py`/`navi-singleton.py` share,
    never a DoE-side `bin/lib` sys.path shim. Resolved lazily, inside a function body, so importing
    this module stays module-body-inert -- a module-scope `from coordinator_core... import ...` is
    exactly the `coordinator_core.warm.serve_classifier` "module-scope non-stdlib import" violation
    (see that module's docstring, delta 3) this port must not reintroduce.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.group_em import session_registry

    return session_registry


class Resolution(NamedTuple):
    """Outcome plus the row it came from, if any.

    `outcome` is one of RESOLVED / NO_RECORD / DEAD. NO_RECORD and DEAD are deliberately not
    merged: the first means nothing on disk claims that sid, the second means a record exists but
    its process is gone. Neither is evidence that the WORK is unowned -- see `live_rows_near`.
    """

    outcome: str
    row: Optional[Any]  # coordinator_core.group_em.session_registry.RegistryRow, resolved lazily

    @property
    def address(self) -> str:
        """Bare `SendMessage` address, or `""` for any non-resolved outcome."""
        return self.row.name if (self.outcome == RESOLVED and self.row) else ""


def read_rows(directory: Optional[Any] = None) -> list:
    """Every parseable record in the registry with a resolvable name, live or not.

    Unreadable and malformed files are skipped rather than raised on: the directory is written by
    concurrent sessions, so a torn or half-written record is an expected transient, not an error
    worth failing a caller's lookup over. A row with no `name` is unaddressable over SendMessage,
    so it is skipped here even though the shared reader parses it.
    """
    session_registry = _resolve_modules()
    return [row for row in session_registry.read_rows(directory) if row.name]


def resolve(session_id: str, directory: Optional[Any] = None) -> Resolution:
    """Resolve one session id to an addressable peer name."""
    if not session_id:
        return Resolution(NO_RECORD, None)
    session_registry = _resolve_modules()
    for row in read_rows(directory):
        if row.session_id == session_id:
            return Resolution(RESOLVED if session_registry.pid_alive(row.pid) else DEAD, row)
    return Resolution(NO_RECORD, None)


def live_rows_near(path: str, directory: Optional[Any] = None) -> list:
    """Live sessions whose cwd matches `path`, case-insensitively on Windows.

    The follow-up to an unresolved sid. A session that resumed or `/clear`ed is still working the
    same tree under the same name with a NEW sid, so a live row here is the likely holder even
    though the recorded sid resolved to nothing.
    """
    session_registry = _resolve_modules()
    target = os.path.normcase(os.path.normpath(path)) if path else ""
    hits = []
    for row in read_rows(directory):
        if not row.cwd or not session_registry.pid_alive(row.pid):
            continue
        if os.path.normcase(os.path.normpath(row.cwd)) == target:
            hits.append(row)
    return hits


def _format(row: Any) -> str:
    return f"{row.name}\t{row.session_id}\tpid {row.pid}\t{row.status or '-'}\t{row.cwd}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resolve-peer-address",
        description="Resolve a session id to the peer name SendMessage can address.",
    )
    parser.add_argument("session_id", nargs="?", help="session id to resolve")
    parser.add_argument(
        "--near",
        metavar="PATH",
        help="list live sessions whose cwd is PATH -- the follow-up when a sid does not resolve",
    )
    parser.add_argument("--list", action="store_true", help="list every live session record")
    args = parser.parse_args(argv)

    if args.list:
        session_registry = _resolve_modules()
        for row in read_rows():
            if session_registry.pid_alive(row.pid):
                print(_format(row))
        return 0

    if args.near and not args.session_id:
        hits = live_rows_near(args.near)
        for row in hits:
            print(_format(row))
        return 0 if hits else 3

    if not args.session_id:
        parser.error("give a session id, --near PATH, or --list")

    result = resolve(args.session_id)
    if result.outcome == RESOLVED:
        print(result.address)
        return 0

    if result.outcome == DEAD and result.row:
        print(
            f"record found but its process is gone: {result.row.name} (pid {result.row.pid}). "
            "Not proof the work is unowned -- re-check with --near "
            f"{result.row.cwd or '<workstream path>'}",
            file=sys.stderr,
        )
        return 4

    print(
        f"no live-session record for {args.session_id}. This is NOT proof the session ended: a "
        "resume or /clear mints a new session id while the name and pid persist. Re-check with "
        "--near <workstream path>; if that is empty too, write what the holder needs into the "
        "artifact it is working from rather than guessing a name.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
