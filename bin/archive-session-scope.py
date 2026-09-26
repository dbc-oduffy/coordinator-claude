# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import argparse
import json
import sys

require_colocated_engine_on_path = None  # type: ignore  # bound by _bootstrap_cc_invoke()


def _bootstrap_cc_invoke() -> None:
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
