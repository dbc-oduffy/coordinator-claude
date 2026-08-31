# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""archive-session-scope.py — archives a session's claim directory at SessionEnd.

Renamed here on 2026-08-30 from a WSC-prefixed name that had outlived its
meaning: nothing in `/workstream-complete` calls this file, and its whole job
is the SessionEnd archive below. Agreed with DoE-claude, which owns the sole
caller, and sequenced so the caller never resolved a missing path -- rename
plus a temporary forwarder at the old path, DoE's `_archive` repointed
(DoE-claude `edbbf7fd48`), forwarder deleted. The old path is recorded in
`docs/install/relocation-ledger.json`; nothing resolves it any more.

Formerly also carried `tail-args`, which assembled optional
`--deleted-paths`/`--kept-entries`/`--review-*` argv for a `wsc-tail.py`
trampoline call. K-046 deleted `coordinator/bin/wsc-tail.py` on 2026-08-23
(`c07062c99`; relocation-ledger disposition `retired`), taking the only
consumer of those tokens with it, and the `d-close-tail-args` directive that
produced them went in the same kill. `tail-args` and its tests were removed
2026-08-30 — 198 lines that could only ever have emitted argv for a parser that
no longer exists. Nothing replaced it and nothing needs to: the requirement it
served died with its consumer, and this file's whole remaining job is the one
subcommand below.

Subcommands
-----------
archive-session
    Archive this session's claim directory (`coordinator_core.session.scope
    .archive(sid)`), lifting the `python3 -c` heredoc the SKILL.md's Step 3.5
    used to inline. Idempotent (a missing session dir is treated as
    already-archived) and non-fatal-by-design: a failure here prints a
    diagnostic to stderr but the subcommand exits `0` regardless. `--sid` is
    required (the op's own ``archive()`` raises ``ValueError`` on an empty
    sid; this CLI checks the same precondition before the call so the error
    message names the CLI, not a bare Python traceback).

    Caller: DoE-claude's SessionEnd hook,
    `coordinator/hooks/scripts/sessionend-archive-session.py` (wired via
    `hooks.json`) — the SOLE archival occasion in the system as of
    `e510140a` (`ceremony.wsc_tail`'s own `tail_ops.cs_archive` call site
    was removed; a 24h live-excluding reap in `ops/session/reap.py` is the
    backstop). The `/workstream-complete` Step 3.5 mid-session invocation
    this docstring used to describe no longer exists — do NOT call this
    subcommand mid-session; it must fire only at SessionEnd, after the
    session's own work (including receipt emit and sentinel clear) is done.

Spec backlink: pln-wsc-tail-slim-down-op-scoped-c-e9a265 (WSC-3 chunk —
port residual bash logic OUT of DoE-claude's `workstream-complete/SKILL.md`
Step 3/3.5 into a naked-Python CLI here).
Spec backlink (source bash this ports): DoE-claude
`coordinator/skills/workstream-complete/SKILL.md` lines ~2085-2099 (tail-arg
assembly) and ~2350-2358 (session-scope archive-on-exit).
"""
from __future__ import annotations

import argparse
import json
import sys

require_colocated_engine_on_path = None  # type: ignore  # bound by _bootstrap_cc_invoke()


def _bootstrap_cc_invoke() -> None:
    """Import `require_colocated_engine_on_path` and bind it at module
    scope, called from `_cmd_archive_session()` (module body stays inert on
    both the warm door and the un-bootstrapped settings-home forwarder load
    routes).

    Guarded on its own current value so a caller's
    `mock.patch.object(mod, "require_colocated_engine_on_path", ...)` set
    BEFORE the subcommand runs is never clobbered by this bootstrap.
    """
    global require_colocated_engine_on_path
    if require_colocated_engine_on_path is not None:
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path


def _cmd_archive_session(args: argparse.Namespace) -> int:
    if not args.sid:
        print("archive-session-scope.py archive-session: --sid required", file=sys.stderr)
        return 1

    _bootstrap_cc_invoke()

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as exc:
        print(
            f"archive-session-scope.py archive-session: engine-root resolution failed: {exc} "
            "(non-fatal — skipping, per module docstring)",
            file=sys.stderr,
        )
        return 0

    try:
        from coordinator_core.session.scope import archive
    except ImportError as exc:
        print(
            f"archive-session-scope.py archive-session: coordinator_core.session.scope not "
            f"importable: {exc} (non-fatal — skipping, per module docstring)",
            file=sys.stderr,
        )
        return 0

    try:
        ok = archive(args.sid)
    except Exception as exc:  # noqa: BLE001 — non-fatal by design, see docstring
        print(
            f"archive-session-scope.py archive-session: archive({args.sid!r}) raised {exc!r} "
            "(non-fatal — reported, not raised)",
            file=sys.stderr,
        )
        return 0

    if not ok:
        print(
            f"archive-session-scope.py archive-session: archive({args.sid!r}) returned False "
            "(non-fatal — 24h reaper is the backstop)",
            file=sys.stderr,
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archive-session-scope.py",
        description="Archive a session's claim directory at SessionEnd.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    archive_session_p = subparsers.add_parser(
        "archive-session",
        help="Archive this session's claim directory (idempotent, non-fatal).",
    )
    archive_session_p.add_argument("--sid", required=True, help="Session id to archive.")
    archive_session_p.set_defaults(func=_cmd_archive_session)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
