#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""sweep-consumed-handoffs.py — on-demand single-family archival sweep for CONSUMED
handoffs, via session.sweep_consumed_handoffs.

Purpose: before this CLI, the ONLY manual route to archive consumed handoffs was the
composite `sweep-boot.py`, which also runs the unintegrated-findings reap (a tracked
git-rm delete of state/review-trail/findings/*.md sidecars) — so an EM who wanted "just
archive the consumed batons" had to accept an unrelated destructive sweep alongside it.
`sweep-shipped-handoffs.py` is NOT a substitute either: it covers the deployment_state
axis (shipped/abandoned/superseded), not the consumption axis this CLI covers.

Carries the SAME boot-path behavioral additions session.boot_sweep's consumed-leg has —
the 30-minute claimed_at recency floor and the DR-084 non-heir consumed+in_flight
skip-and-surface disposition — via session.sweep_consumed_handoffs, which wraps
session.boot_sweep._sweep_consumed_handoffs directly (same function, not a
reimplementation). Deliberately does NOT go through the weaker plain
fleet.archive_completed_handoffs op path, which lacks both and would happily archive a
live peer's just-claimed baton.

Usage:
    python3 sweep-consumed-handoffs.py [--dry-run] [<repo_root>]

    --dry-run    Preview candidates without mutating anything — no git-mv, no
                 shipped_in stamp, no WARN-marker write, no commit. See
                 session.sweep_consumed_handoffs' own dry_run docstring: a preview may
                 UNDER-count relative to a live run, never over-count.
    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.

Stdout contract: a human-readable summary — archived (or would-archive) count, and every
skip with its id and reason (never silently swallowed; the DR-084 awaiting-adjudication
disposition and the recency-floor disposition are each named explicitly). Not a bare
integer like the sibling sweep-terminal-plans.py — this CLI is meant to be read by a
human deciding whether to act, not solely consumed by a numeric boot-time guard.

Commit semantics: the op self-commits (archive_and_commit + _commit_consumed_metadata) —
this trampoline MUST NOT stage/commit itself. --dry-run never commits by construction.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1 posture): no legacy bash
fallback — a genuinely seam-absent install surfaces as a transport failure (RuntimeError),
reported to stderr, exit code 2.

Exit codes:
    0 — normal completion (including zero candidates, and dry-run preview).
    1 — op-level setup error (bad repo_root / state_common_dir).
    2 — transport failure (native seam absent, spawn error) or op-level partial failure.

Spec backlink: docs/plans/2026-07-23-wsc-tail-slim-down.md § C21
Wraps: session.sweep_consumed_handoffs (native op)

Liveness stamp (C2, 2026-07-23 wsc-tail-slim-down): a genuinely successful, non-dry-run
completion (exit 0 or the op-level partial exit 2) stamps the shared `archive_sweeps`
housekeeping-liveness key (`coordinator_core.ops.ceremony.housekeeping_liveness.
stamp_liveness`), mirroring `sweep-boot.py`'s own `_stamp_archive_sweeps_liveness`.
Multiple producers stamping the same key is additive-safe (last-writer-wins liveness
signal). `--dry-run` never stamps (a preview mutates nothing) and neither does a setup
error (exit 1) or transport failure (exit 2 before the op ever ran).
"""
from __future__ import annotations

import os
import subprocess
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
from sweep_argv import parse_repo_root_argv  # noqa: E402

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_USAGE = "usage: python3 sweep-consumed-handoffs.py [-h] [--dry-run] [<repo_root>]"


def _import_housekeeping_seam():
    """Resolve CLAUDE_KLABAUTER_ROOT and import `housekeeping_liveness.{stamp_liveness,ARCHIVE_SWEEPS}`.

    Mirrors `sweep-boot.py::_import_housekeeping_seam` / the copies in the sibling
    per-class CLIs -- best-effort; returns None on any resolution/import failure.
    """
    try:
        claude_klabauter_root = cc_invoke._resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )
    except Exception:  # noqa: BLE001 -- best-effort; never let seam-import failure mask the real error
        return None
    return stamp_liveness, ARCHIVE_SWEEPS


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the non-dry-run, op-ran success path only.
    """
    seam = _import_housekeeping_seam()
    if seam is None:
        return
    stamp_liveness, archive_sweeps = seam
    try:
        stamp_liveness(repo_root, archive_sweeps)
    except Exception:  # noqa: BLE001 -- never raise out of a best-effort liveness stamp
        pass


def _no_fallback() -> None:
    raise RuntimeError(
        "sweep-consumed-handoffs: native seam required (no bash fallback -- big-bang cutover)"
    )


def _resolve_repo_root(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    resolved = (proc.stdout or "").strip()
    if proc.returncode != 0 or not resolved:
        return None
    return resolved


def _parse_argv(argv: list[str]) -> tuple[bool, str | None]:
    """Returns (dry_run, explicit_repo_root).

    Delegates the leading-dash-argument scan to the shared
    `sweep_argv.parse_repo_root_argv` helper (also used by
    sweep-actioned-memos.py, sweep-terminal-plans.py, sweep-boot.py) —
    `--dry-run`/`-n` is this script's OWN known flag; any other leading-dash
    token is now rejected instead of silently falling through as the
    positional `<repo_root>`.
    """
    positional, flags_seen, early_exit = parse_repo_root_argv(
        argv,
        prog="sweep-consumed-handoffs.py",
        usage=__doc__,
        known_flags=frozenset({"--dry-run", "-n"}),
    )
    if early_exit is not None:
        raise SystemExit(early_exit)
    dry_run = "--dry-run" in flags_seen or "-n" in flags_seen
    return dry_run, (positional[0] if positional else None)


def _print_disposition(label: str, items: list) -> None:
    if not items:
        return
    print(f"{label} ({len(items)}):")
    for item in items:
        if isinstance(item, dict):
            cid = item.get("id", "?")
            reason = item.get("reason")
            if reason:
                print(f"  - {cid} — {reason}")
            else:
                heir = item.get("heir")
                suffix = " [heir]" if heir else ""
                print(f"  - {cid}{suffix}")
        else:
            print(f"  - {item!r}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry_run, explicit_repo_root = _parse_argv(argv)

    repo_root = _resolve_repo_root(explicit_repo_root)
    if repo_root is None:
        print("sweep-consumed-handoffs: cannot resolve git repo root", file=sys.stderr)
        return 2

    params = {"dry_run": dry_run}
    try:
        result = cc_invoke.route(
            "session.sweep_consumed_handoffs", params, repo_root, _no_fallback
        )
    except RuntimeError as exc:
        print(f"sweep-consumed-handoffs: transport failure: {exc}", file=sys.stderr)
        return 2

    if not isinstance(result, dict):
        print("sweep-consumed-handoffs: op returned a non-object result", file=sys.stderr)
        return 2

    exit_code = result.get("exit_code", 0)
    if exit_code == 1:
        print(f"sweep-consumed-handoffs: setup error: {result.get('error')}", file=sys.stderr)
        return 1

    bucket = result.get("consumed_handoffs", {})
    archived = bucket.get("archived", []) if isinstance(bucket, dict) else []
    skipped = bucket.get("skipped", []) if isinstance(bucket, dict) else []
    failed = bucket.get("failed", []) if isinstance(bucket, dict) else []
    warnings = result.get("warnings", [])

    verb = "would archive" if dry_run else "archived"
    print(f"{len(archived)} consumed handoff(s) {verb}")
    _print_disposition("Would archive" if dry_run else "Archived", archived)
    # Skips are always surfaced — never silently swallowed (recency floor +
    # DR-084 awaiting-adjudication are the two dispositions this CLI exists to
    # make visible; see module docstring).
    _print_disposition("Skipped", skipped)
    if failed:
        print(f"WARN: {len(failed)} item(s) failed — check claude-klabauter logs", file=sys.stderr)
        _print_disposition("Failed", failed)
    if warnings:
        for w in warnings:
            print(f"WARN: {w}", file=sys.stderr)

    if not dry_run:
        _stamp_archive_sweeps_liveness(repo_root)

    if exit_code == 2:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
