#!/usr/bin/env python3
"""block-discharge -- the agent-authored discharge write, and the check that
reads it back from the committed tree alone, with no cooperation from the
session it audits.

WHY THIS EXISTS. A blocking Stop guard now calls `record_fire` immediately
before it returns 2, minting a nonce and appending a `fire` record to
`state/block-discharge/<session-id>.jsonl`. That record has no reader until
something either (a) lets the blocked agent close the loop, or (b) reads the
ledger back from outside the blocked session. This module is both: `record`
is the agent-authored post-fire write; `check` is the outside reader, and by
design needs nothing beyond files already on disk -- no registry lookup, no
session liveness probe, no transcript read. `archive` is the retention
escape hatch (see below) -- without it every historical fire, including one
from a session that ended legitimately, predates this mechanism, or was
killed mid-turn before it could discharge, would stay in the default sweep
forever and `check` would go permanently red within days.

Three verbs, no more:

  record --nonce <n> --action "<text>"
      The agent-authored post-fire write. Searches every ledger under
      `state/block-discharge/` for a `fire` record carrying `nonce` --
      refuses (exit non-zero) when none matches, which is what stops a
      fabricated discharge; an invented nonce cannot self-discharge. On
      success, also `git add`s the ledger path it just wrote -- a single
      explicit pathspec, never `-A`/`.` -- so the record is staged for
      whatever commit the session makes next rather than depending on the
      agent remembering to include it. Staging is not committing: it closes
      the careless-omission case, not a deliberate suppression, which is out
      of this mechanism's trust model (an agent that wants to hide a fire
      can decline to run `record` at all, or run it and then unstage; both
      are visible to `check` as an undischarged fire, and to the EM's own
      judgement of the run, not to this script).

  check [--session <id>] [--all]
      Exits non-zero and names every fire record with no matching discharge,
      by nonce, guard, and session. Reads files and nothing else. With no
      `--session`, sweeps ledgers modified within the last 14 days (by file
      mtime) -- the bounded-recency default, so a legitimately-ended session
      from months ago cannot make every future `check` permanently red.
      `--all` opts into the unscoped historical sweep instead. `--session
      <id>` reads exactly that one ledger, unscoped by recency, so a
      caller who already knows the session it wants (e.g.
      `/workstream-complete` closing itself out) is never subject to the
      default window.

  archive --session <id>
      `git mv`s one session's ledger to `archive/block-discharge/<YYYY-MM>/`
      (structured-queue closure convention), where `<YYYY-MM>` is the
      archiving month, not the ledger's own dates. A ledger whose only fire
      predates the session's own end (no crash, no kill) and was never
      discharged is not agent misconduct by itself -- `check` names it
      `undischarged`, the same disposition as every other unmatched fire; a
      fire from a session killed mid-turn is indistinguishable, from the
      committed tree alone, from one an agent chose to ignore, and this
      script does not claim otherwise.

Negative-spec: no registry lookup, no session liveness probe, no transcript
read, no network, no third-party import. `check`'s correctness must not
depend on any session process being alive.

Invocation is always `python coordinator/bin/block-discharge.py <verb>
...`, resolved relative to repo root -- there is no bare `block-discharge`
PATH shim anywhere in `coordinator/bin/`.

Port of DoE-claude's `coordinator/bin/block-discharge.py`
(`docs/plans/2026-09-06-block-discharge-durable-artifact.md`, chunk C3) per
`docs/plans/2026-09-18-doe-holds-no-scripts.md` chunk W2-C8. The ledger
logic this CLI drove by loading DoE's `coordinator/hooks/scripts/
_block_discharge.py` by file path (a DoE-only module, not published) now
lives as `coordinator_core.block_discharge` (ported at chunk W2-C3) and is
imported the ordinary way -- no more by-path `importlib` load, no
`sys.modules` keying, no defensive `_engine_root` import: the module IS the
engine here, per this plan's § Path resolution "engine" class.

Ledger-root resolution is the "session repo" class in the same table:
resolved against the CALLER's cwd via `coordinator_core.git.repo_root`,
never against this file's own `__file__` location -- this CLI ships from
Claude-klabauter but a fire it discharges was very likely recorded by a hook running
in the CONSUMING repo (see `_resolve_ledger_root` below for the DoE-claude@
b644d5a9 lesson this table entry exists to prevent a repeat of).

Spec: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C8.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

_CLI_ROOT = Path(__file__).resolve().parents[2]

#: Populated by `_bootstrap()`, deferred out of module scope so the non-stdlib imports it
#: performs are not a module-body-inertness violation
#: (`coordinator_core.warm.serve_classifier`). Every caller that needs either name below calls
#: `_bootstrap()` first; the cache makes repeat calls in one process free.
_show_toplevel = None  # type: ignore[assignment]
bd = None  # type: ignore[assignment]
_bootstrap_done = False


def _bootstrap() -> None:
    """Import the engine-bootstrap chain exactly once per process. Failure (missing `lib`/
    `cc_invoke`, or the engine not resolvable) leaves `_show_toplevel`/`bd` at `None` -- see
    main(): a usage-error exit, not a crash."""
    global _show_toplevel, bd, _bootstrap_done
    if _bootstrap_done:
        return
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.git.repo_root import show_toplevel as _st
        from coordinator_core import block_discharge as _bd

        _show_toplevel = _st
        bd = _bd
    except Exception:  # noqa: BLE001 -- see main(): a usage-error exit, not a crash
        _show_toplevel = None
        bd = None
    _bootstrap_done = True

# conhost on Windows spawns a visible window for a console-subsystem child
# (git.exe included) unless this flag suppresses it; a no-op on other OSes.
# Used only by `_git_add`/`cmd_archive` below (real `git add`/`git mv` calls)
# -- ledger-root resolution itself is zero-spawn (`_show_toplevel` walks,
# never spawns; see `coordinator_core.git.repo_root`).
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _resolve_ledger_root(explicit_repo_root: Optional[str] = None) -> Path:
    """The repo whose ledger this invocation reads and writes -- the CONSUMING
    repo, which is usually not the one this CLI lives in.

    The Stop guard fires in whatever repo the session is working in and
    writes its fire record to that repo's `state/block-discharge/`. Pinning
    the ledger root to this file's own `__file__` chain made the discharge
    instruction the guard prints unrunnable from any OTHER repo (the
    DoE-claude@b644d5a9 lesson, § Path resolution): it looked in the wrong
    repo for a fire recorded elsewhere, and reported it as an unmatched
    nonce. This resolution order is what makes the guard's printed
    instruction true as written, from whichever repo it fired in.

    Order:
      1. `explicit_repo_root` -- the `--repo-root` CLI flag, when the caller
         passed one. Wins over everything: an explicit argument beats any
         ambient signal.
      2. `COORDINATOR_BLOCK_DISCHARGE_ROOT` env override, for a session whose
         cwd is outside any checkout.
      3. `CLAUDE_PROJECT_DIR` env, when set and a real directory -- carried
         over from the DoE original's `_session_repo_root()` rung 1, since
         `coordinator_core.git.repo_root.show_toplevel()` does not consult
         it (cwd-walk only, by design -- see that function's own
         docstring).
      4. `coordinator_core.git.repo_root.show_toplevel()` -- the shared,
         zero-spawn (parent-walk only) repo-root resolver, keyed on cwd.
      5. This CLI's own `__file__`-derived checkout -- unchanged fallback,
         reached only when rung 4 yields nothing (e.g. cwd is outside any
         `.git` tree).
    """
    _bootstrap()

    if explicit_repo_root:
        return Path(explicit_repo_root).resolve()

    override = os.environ.get("COORDINATOR_BLOCK_DISCHARGE_ROOT", "").strip()
    if override:
        resolved = Path(override).resolve()
        # Review carried over from DoE (coordinator:code-reviewer P2): a typo'd or
        # partially-wrong override previously produced no error at all. This is a
        # warning, not a refusal: the mechanism's whole trust model is an
        # operator-controlled env var, not attacker input, and a hard failure here
        # would be worse than a noisy but working ledger path.
        if not resolved.is_dir():
            print(
                f"block-discharge: COORDINATOR_BLOCK_DISCHARGE_ROOT={override!r} "
                f"resolves to {resolved}, which is not a directory",
                file=sys.stderr,
            )
        return resolved

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if project_dir:
        resolved = Path(project_dir).resolve()
        if resolved.is_dir():
            return resolved

    if _show_toplevel is not None:
        try:
            toplevel = _show_toplevel()
        except Exception:  # noqa: BLE001
            toplevel = None
        if toplevel:
            return Path(toplevel).resolve()

    return _CLI_ROOT


REPO_ROOT = _CLI_ROOT
_LEDGER_DIR = REPO_ROOT / "state" / "block-discharge"

_RECENT_WINDOW_SECONDS = 14 * 24 * 60 * 60


def _session_id_from_ledger_path(path: Path) -> str:
    return path.stem


def _git_add(path: Path) -> None:
    """Best-effort `git add` of a single explicit pathspec. Never `-A`/`.`.
    Staging failure (e.g. not a git work tree in some test harness) must
    never turn a successful ledger write into a non-zero exit -- the write
    already durably happened; staging is a courtesy on top of it."""
    try:
        subprocess.run(
            ["git", "add", "--", str(path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
            **_NO_CONSOLE,
        )
    except OSError:
        pass


def _iter_ledger_files() -> list:
    try:
        return sorted(p for p in _LEDGER_DIR.glob("*.jsonl") if p.is_file())
    except OSError:
        return []


def cmd_record(args: argparse.Namespace) -> int:
    _bootstrap()
    nonce = args.nonce
    for ledger_path in _iter_ledger_files():
        session_id = _session_id_from_ledger_path(ledger_path)
        records, _skipped = bd.read_ledger(str(REPO_ROOT), session_id=session_id)
        has_fire = any(
            record.get("kind") == "fire" and record.get("nonce") == nonce for record in records
        )
        if not has_fire:
            continue
        ok = bd.record_discharge(str(REPO_ROOT), session_id, nonce, args.action)
        if not ok:
            print(
                f"block-discharge record: found fire for nonce {nonce} in session "
                f"{session_id} but the discharge write failed",
                file=sys.stderr,
            )
            return 1
        _git_add(ledger_path)
        print(f"block-discharge record: discharged {nonce} (session {session_id})")
        return 0
    # Name the likelier cause first. Saying only that the NONCE did not match reads
    # as "you typed the wrong id" and invites a retry -- when the actual fact is
    # almost always that the fire was recorded in a DIFFERENT repo's ledger, because
    # the guard writes into whichever repo the session works in.
    hint = ""
    if not _LEDGER_DIR.is_dir() or not any(_iter_ledger_files()):
        hint = (
            f"\n  This ledger directory holds no fire records at all, so the nonce is "
            f"probably fine and the ROOT is wrong. Run this from the repo whose session "
            f"was blocked, or name it explicitly:\n"
            f"    python coordinator/bin/block-discharge.py record --nonce {nonce} "
            f"--action ... --repo-root <that repo>\n"
            f"  or:\n"
            f"    COORDINATOR_BLOCK_DISCHARGE_ROOT=<that repo> <this command>"
        )
    print(
        f"block-discharge record: no fire record matches nonce {nonce} in any ledger "
        f"under {_LEDGER_DIR} -- refusing to record a self-issued discharge.{hint}",
        file=sys.stderr,
    )
    return 1


def _undischarged_for_session(session_id: str) -> tuple:
    """Return `(undischarged, skipped)` for one session's ledger --
    undischarged is a list of `(nonce, guard, session_id)` tuples."""
    _bootstrap()
    records, skipped = bd.read_ledger(str(REPO_ROOT), session_id=session_id)
    fires = {}
    discharged_nonces = set()
    for record in records:
        if record.get("kind") == "fire":
            fires[record.get("nonce")] = record
        elif record.get("kind") == "discharge":
            discharged_nonces.add(record.get("nonce"))
    undischarged = []
    for nonce, fire in fires.items():
        if nonce in discharged_nonces:
            continue
        undischarged.append((nonce, fire.get("guard"), fire.get("session_id") or session_id))
    return undischarged, skipped


def cmd_check(args: argparse.Namespace) -> int:
    if args.session:
        ledger_paths = [_LEDGER_DIR / f"{args.session}.jsonl"]
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
        undischarged, skipped = _undischarged_for_session(session_id)
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
    source = _LEDGER_DIR / f"{session_id}.jsonl"
    if not source.exists():
        print(f"block-discharge archive: no ledger for session {session_id} at {source}", file=sys.stderr)
        return 1
    month = time.strftime("%Y-%m", time.gmtime())
    dest_dir = REPO_ROOT / "archive" / "block-discharge" / month
    dest = dest_dir / f"{session_id}.jsonl"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # `git mv` refuses a source that was written but never staged (e.g. a
    # ledger whose owning session never got as far as `record`'s own `git
    # add`, or a ledger this same invocation is archiving before anything
    # committed it) -- stage it first so the move always has a tracked
    # source to act on.
    _git_add(source)
    try:
        result = subprocess.run(
            ["git", "mv", "--", str(source), str(dest)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
            **_NO_CONSOLE,
        )
    except OSError as exc:
        print(f"block-discharge archive: git mv failed to invoke: {exc}", file=sys.stderr)
        return 1
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        print(f"block-discharge archive: git mv failed: {stderr_text}", file=sys.stderr)
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

    _REPO_ROOT_HELP = (
        "repo whose ledger to use; defaults to COORDINATOR_BLOCK_DISCHARGE_ROOT, "
        "then the invoking repo's git toplevel (walked from cwd), "
        "then this CLI's own checkout"
    )

    record_parser = subparsers.add_parser("record", help="record a post-fire discharge")
    record_parser.add_argument("--nonce", required=True)
    record_parser.add_argument("--action", required=True)
    record_parser.add_argument("--repo-root", default=None, help=_REPO_ROOT_HELP)

    check_parser = subparsers.add_parser("check", help="check for undischarged fires")
    check_parser.add_argument("--session", default=None)
    check_parser.add_argument("--all", action="store_true")
    check_parser.add_argument("--repo-root", default=None, help=_REPO_ROOT_HELP)

    archive_parser = subparsers.add_parser("archive", help="archive one session's ledger")
    archive_parser.add_argument("--session", required=True)
    archive_parser.add_argument("--repo-root", default=None, help=_REPO_ROOT_HELP)

    args = parser.parse_args(argv)

    # Re-resolve the ledger root for THIS invocation now that `--repo-root`
    # (if any) is known -- the module-level REPO_ROOT/_LEDGER_DIR computed at
    # import time are only the no-argument default. Every command function
    # below reads REPO_ROOT/_LEDGER_DIR as module globals, so updating them
    # here is what makes `--repo-root` (and the ladder under it) apply to
    # `record`, `check`, and `archive` alike.
    global REPO_ROOT, _LEDGER_DIR
    REPO_ROOT = _resolve_ledger_root(args.repo_root)
    _LEDGER_DIR = REPO_ROOT / "state" / "block-discharge"

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
