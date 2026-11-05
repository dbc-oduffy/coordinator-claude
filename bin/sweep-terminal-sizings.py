"""sweep-terminal-sizings.py — on-demand CLI fire for the terminal-sizings sweep.

Purpose: the manual human/ceremony-invoked surface over
`fleet.archive_terminal_sizings` (`coordinator_core.ops.fleet.archive_sizings`),
the sizings sibling of `sweep-terminal-handoffs.py` (structural mirror — same
`--dry-run`, same not-in-a-git-repo / `git_common_dir` failure messages, same
usage shape). The op already existed (landed 2026-08-13, `4dfb0846dc`) with a
dry-run preview and an act mode, both `_common.archive_and_commit`-backed —
the gap this script closes is that nothing ever called it (C3,
docs/plans/2026-09-03-close-verb-archival-stops-asking-for-wri.md).

A thin caller of `coordinator_core.ops.fleet.terminal_sizing_drain.drain`, the
single-pass drain the close verbs also run in-process: one call, no
`candidate_ids`, no JSON-RPC round trip. `--dry-run` calls `drain(dry_run=True)`
and mutates nothing; otherwise the drain archives every movable terminal
sizing in one commit and this script prints its counters.

Exit codes:
    0 — normal (including zero-candidates, all-retained, a completed
        `--dry-run` census, and a fully successful sweep).
    1 — the sweep failed: either the preview or act call returned
        `exit_code != 0` (setup error, or DETERMINATE-PARTIAL with a
        non-empty `failed[]`). Candidates are retained for the next sweep
        either way. A `--dry-run` census that fails the same way returns 1.
    2 — internal error (not inside a git repo), or a malformed argv.

Big-bang cutover (2026-07-19 Windows de-bash campaign, Wave F1): no legacy
bash fallback — a genuinely seam-absent install surfaces as a transport
failure (RuntimeError), caught below and logged (best-effort ceremony).

Liveness stamp: mirrors `sweep-terminal-handoffs.py`'s own liveness contract
— every ACT-path completion that reaches the sweep-processing tail (exit 0,
including zero-candidates/all-retained, AND exit 1, a failed sweep) stamps
the SAME shared `archive_sweeps` housekeeping-liveness key
(`coordinator_core.ops.ceremony.housekeeping_liveness.stamp_liveness`) — one
key shared across every archival family, not a per-family key. The
internal-error path (exit 2 — not a git repo) returns before reaching the
tail and never stamps. A `--dry-run` census also never stamps — a census is
not a sweep, for the same reason `sweep-terminal-handoffs.py` gives.

Spec backlink: docs/plans/2026-09-03-close-verb-archival-stops-asking-for-wri.md § C3
Wraps: coordinator_core.ops.fleet.terminal_sizing_drain.drain.

Negative-spec:
  - Does NOT reimplement any scan, classification, or move logic — the
    drain owns all of it.
  - Does NOT resurrect `coordinator/bin/sweep-boot.py` — that file is a
    gravestone (see its own docstring: a boot-time sweep, if ever wanted
    again, is a NEW plan spiked from first principles, never a repoint of
    that file). This script is fired from the close verbs, not from boot.
  - Does NOT pass `--dry-run` as an op-level directive arg from either close
    verb's directive builder — see `directives_session_hygiene.py ::
    build_terminal_sizing_sweep_directive`'s own negative-spec.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")

_USAGE = "usage: python sweep-terminal-sizings.py [-h] [--dry-run]"
_DRY_RUN_FLAG = "--dry-run"


def _ensure_claude_klabauter_on_path() -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    return cc_invoke.require_engine_on_path(__file__)


def _is_consumer_box() -> bool:
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.machine_profile import machine_profile

        return machine_profile() == "consumer"
    except Exception:  # noqa: BLE001 -- unknown profile keeps the author behavior
        return False


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    try:
        _ensure_claude_klabauter_on_path()
        from coordinator_core.ops.ceremony.housekeeping_liveness import (
            ARCHIVE_SWEEPS,
            stamp_liveness,
        )

        stamp_liveness(repo_root, ARCHIVE_SWEEPS)
    except Exception:  # noqa: BLE001 -- best-effort; never raise out of a liveness stamp
        pass


def _print_planned_moves(candidates: "list[dict]") -> None:
    if not candidates:
        print("dry run: no terminal sizings would be archived")
        return
    print(f"dry run: {len(candidates)} terminal sizing-object(s) would be archived:")
    for cand in candidates:
        print(f"  {cand.get('id')}")


def _print_refusal_census(scan_skipped: "list[dict]", act_skipped: "list[dict]") -> None:
    if scan_skipped:
        print(f"scan refused {len(scan_skipped)} record(s):")
        for item in scan_skipped:
            print(f"  {item.get('id')} -- {item.get('reason')}")
    if act_skipped:
        print(f"terminal but not moved -- {len(act_skipped)} record(s):")
        for item in act_skipped:
            print(f"  {item.get('id')} -- {item.get('reason')}")


def main(argv: "list[str] | None" = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from repo_identity import resolve_checked_repo_root
    from sweep_argv import parse_repo_root_argv

    argv = sys.argv[1:] if argv is None else argv
    _positional, flags, early_exit = parse_repo_root_argv(
        argv,
        prog="sweep-terminal-sizings.py",
        usage=_USAGE,
        known_flags=frozenset({_DRY_RUN_FLAG}),
        max_positional=0,
    )
    if early_exit is not None:
        return early_exit
    dry_run = _DRY_RUN_FLAG in flags

    git_repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if git_repo_root is None:
        print("sweep-terminal-sizings.py: not inside a git repo", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        if _is_consumer_box():
            print(f"warning: {verdict['message']}")
        else:
            print(verdict["message"], file=sys.stderr)

    repo_root = git_repo_root

    _ensure_claude_klabauter_on_path()
    from coordinator_core.git.repo_root import git_common_dir
    from coordinator_core.lifecycle import main_worktree_root
    from coordinator_core.ops.fleet.terminal_sizing_drain import drain

    try:
        worktree_root = main_worktree_root(Path(git_common_dir(cwd=str(repo_root))))
    except Exception as exc:
        print(f"sweep-terminal-sizings.py: git_common_dir failed: {exc}", file=sys.stderr)
        return 1

    try:
        result = drain(worktree_root, dry_run=dry_run)
    except Exception as exc:
        print(f"sweep-terminal-sizings.py: drain failed: {exc}", file=sys.stderr)
        if not dry_run:
            _stamp_archive_sweeps_liveness(repo_root)
        return 1

    if dry_run:
        _print_planned_moves(result.get("candidates", []))
        _print_refusal_census(result.get("scan_skipped", []), [])
        return 0

    archived = len(result.get("acted", []))
    failed = result.get("failed", [])
    if failed:
        print(
            f"sweep-terminal-sizings.py: WARN: {len(failed)} "
            f"move(s) failed (acted={archived}) -- check claude-klabauter logs",
            file=sys.stderr,
        )

    if archived == 0:
        print("no terminal sizings archived")
    else:
        print(f"{archived} terminal sizings archived")

    scan_skipped = result.get("scan_skipped", [])
    _print_refusal_census(scan_skipped, [s for s in result.get("skipped", []) if s not in scan_skipped])

    _stamp_archive_sweeps_liveness(repo_root)
    return 1 if failed else 0


if __name__ == "__main__":
    _ensure_claude_klabauter_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        _exit_code = main()
    sys.exit(_exit_code)
