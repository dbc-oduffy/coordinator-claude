"""block-discharge -- the agent-authored discharge write, and the check that
reads it back from outside the session it audits.

A blocking Stop guard calls `record_fire` immediately before it returns 2,
minting a nonce and appending a `fire` record to
`<settings-home>/machine-local/block-discharge/<session-id>.jsonl` (the
per-box store, `coordinator_core.block_discharge.ledger_dir()`). The store is
box-wide and flat: session ids are box-unique, so a nonce is found wherever the
guard fired from. Nothing here touches git; the ledger is per-box telemetry,
never committed, and `check` needs only files on this box -- no registry
lookup, no session liveness probe, no transcript read, no network, no
third-party import.

Three verbs, no more:

  record --nonce <n> --action "<text>"
      The agent-authored post-fire write. Searches every ledger in the store
      for a `fire` record carrying `nonce`; refuses (exit non-zero) when none
      matches, which stops a fabricated discharge -- an invented nonce cannot
      self-discharge. `--repo-root` is accepted and ignored.

  check [--session <id>] [--all] [--repo-root <dir>]
      Exits non-zero and names every fire record with no matching discharge,
      by nonce, guard, and session. With no `--session`, sweeps ledgers
      modified within the last 14 days (by file mtime); `--all` opts into the
      unscoped historical sweep; `--session <id>` reads exactly that ledger,
      unscoped by recency. `--repo-root` narrows to fires whose recorded
      `repo` equals it (paths compared normcase+realpath).

  archive --session <id>
      Moves one session's ledger (os.replace, no git) to
      `<store>/archive/<YYYY-MM>/`, where `<YYYY-MM>` is the archiving month.
      The store's top-level `*.jsonl` listing excludes that subdirectory.
      `--repo-root` is accepted and ignored.

`--repo-root` stays on every verb because coordinator-content-repo's guards print
`block-discharge record --nonce ... --repo-root "<repo>"` verbatim.

Invocation is always `python coordinator/bin/block-discharge.py <verb> ...`,
resolved relative to repo root -- there is no bare `block-discharge` PATH shim.

Port of coordinator-content-repo's `coordinator/bin/block-discharge.py`; the ledger logic is
`coordinator_core.block_discharge`, imported the ordinary way.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

bd = None  # type: ignore[assignment]
_bootstrap_done = False

_RECENT_WINDOW_SECONDS = 14 * 24 * 60 * 60


def _bootstrap() -> None:
    global bd, _bootstrap_done
    if _bootstrap_done:
        return
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core import block_discharge as _bd

        bd = _bd
    except Exception:  # noqa: BLE001 -- see main(): a usage-error exit, not a crash
        bd = None
    _bootstrap_done = True


def _ledger_dir() -> Path:
    _bootstrap()
    return Path(bd.ledger_dir())


def _norm(path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def _session_id_from_ledger_path(path: Path) -> str:
    return path.stem


def _iter_ledger_files() -> list:
    try:
        return sorted(p for p in _ledger_dir().glob("*.jsonl") if p.is_file())
    except OSError:
        return []


def cmd_record(args: argparse.Namespace) -> int:
    _bootstrap()
    nonce = args.nonce
    for ledger_path in _iter_ledger_files():
        session_id = _session_id_from_ledger_path(ledger_path)
        records, _skipped = bd.read_ledger("", session_id=session_id)
        has_fire = any(
            record.get("kind") == "fire" and record.get("nonce") == nonce for record in records
        )
        if not has_fire:
            continue
        ok = bd.record_discharge("", session_id, nonce, args.action)
        if not ok:
            print(
                f"block-discharge record: found fire for nonce {nonce} in session "
                f"{session_id} but the discharge write failed",
                file=sys.stderr,
            )
            return 1
        print(f"block-discharge record: discharged {nonce} (session {session_id})")
        return 0
    print(
        f"block-discharge record: no fire record matches nonce {nonce} in any ledger "
        f"under {_ledger_dir()} -- refusing to record a self-issued discharge.",
        file=sys.stderr,
    )
    return 1


def _undischarged_for_session(session_id: str, repo_filter: Optional[str] = None) -> tuple:
    _bootstrap()
    records, skipped = bd.read_ledger("", session_id=session_id)
    fires = {}
    discharged_nonces = set()
    for record in records:
        if record.get("kind") == "fire":
            if repo_filter is not None and _norm(record.get("repo") or "") != repo_filter:
                continue
            fires[record.get("nonce")] = record
        elif record.get("kind") == "discharge":
            discharged_nonces.add(record.get("nonce"))
    undischarged = []
    for nonce, fire in fires.items():
        if nonce in discharged_nonces:
            continue
        undischarged.append((nonce, fire.get("guard"), fire.get("session_id") or session_id))
    return undischarged, skipped


def _unsafe_session(session_id: str) -> bool:
    return not session_id or "/" in session_id or "\\" in session_id or session_id.startswith(".")


def cmd_check(args: argparse.Namespace) -> int:
    if args.session and _unsafe_session(args.session):
        print(f"block-discharge check: unsafe session id {args.session!r}", file=sys.stderr)
        return 2
    repo_filter = _norm(args.repo_root) if args.repo_root else None
    if args.session:
        ledger_paths = [_ledger_dir() / f"{args.session}.jsonl"]
    else:
        all_paths = _iter_ledger_files()
        if args.all:
            ledger_paths = all_paths
        else:
            cutoff = time.time() - _RECENT_WINDOW_SECONDS
            ledger_paths = [p for p in all_paths if _safe_mtime(p) >= cutoff]

    total_skipped = 0
    all_undischarged = []
    for ledger_path in ledger_paths:
        if not ledger_path.exists():
            continue
        session_id = _session_id_from_ledger_path(ledger_path)
        undischarged, skipped = _undischarged_for_session(session_id, repo_filter)
        total_skipped += skipped
        all_undischarged.extend(undischarged)

    if total_skipped:
        print(
            f"block-discharge check: {total_skipped} ledger line(s) could not be parsed "
            "-- an unreadable ledger is an unresolved audit, not a clean one",
            file=sys.stderr,
        )

    if not all_undischarged:
        if total_skipped:
            return 1
        print("block-discharge check: no undischarged fires")
        return 0

    for nonce, guard, session_id in all_undischarged:
        print(f"undischarged: nonce={nonce} guard={guard} session={session_id}")
    return 1


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def cmd_archive(args: argparse.Namespace) -> int:
    session_id = args.session
    if _unsafe_session(session_id):
        print(f"block-discharge archive: unsafe session id {session_id!r}", file=sys.stderr)
        return 2
    store = _ledger_dir()
    source = store / f"{session_id}.jsonl"
    if not source.exists():
        print(f"block-discharge archive: no ledger for session {session_id} at {source}", file=sys.stderr)
        return 1
    month = time.strftime("%Y-%m", time.gmtime())
    dest_dir = store / "archive" / month
    dest = dest_dir / f"{session_id}.jsonl"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        os.replace(source, dest)
    except OSError as exc:
        print(f"block-discharge archive: move failed: {exc}", file=sys.stderr)
        return 1
    print(f"block-discharge archive: moved {source} -> {dest}")
    return 0


def main(argv: Optional[list] = None) -> int:
    _bootstrap()
    if bd is None:
        print(
            "block-discharge.py: ERROR -- coordinator_core.block_discharge unresolvable",
            file=sys.stderr,
        )
        return 3

    parser = argparse.ArgumentParser(prog="block-discharge")
    subparsers = parser.add_subparsers(dest="verb", required=True)

    record_parser = subparsers.add_parser("record", help="record a post-fire discharge")
    record_parser.add_argument("--nonce", required=True)
    record_parser.add_argument("--action", required=True)
    record_parser.add_argument("--repo-root", default=None, help="accepted and ignored")

    check_parser = subparsers.add_parser("check", help="check for undischarged fires")
    check_parser.add_argument("--session", default=None)
    check_parser.add_argument("--all", action="store_true")
    check_parser.add_argument(
        "--repo-root", default=None, help="only fires recorded from this checkout"
    )

    archive_parser = subparsers.add_parser("archive", help="archive one session's ledger")
    archive_parser.add_argument("--session", required=True)
    archive_parser.add_argument("--repo-root", default=None, help="accepted and ignored")

    args = parser.parse_args(argv)

    if args.verb == "archive":
        return cmd_archive(args)
    if args.verb == "record":
        return cmd_record(args)
    if args.verb == "check":
        return cmd_check(args)
    parser.error(f"unknown verb {args.verb!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
