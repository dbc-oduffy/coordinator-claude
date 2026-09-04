"""sweep-terminal-sizings.py — on-demand CLI fire for the terminal-sizings sweep.

Purpose: the manual human/ceremony-invoked surface over
`fleet.archive_terminal_sizings` (`coordinator_core.ops.fleet.archive_sizings`),
the sizings sibling of `sweep-terminal-handoffs.py` (structural mirror — same
`--dry-run`, same not-in-a-git-repo / `git_common_dir` failure messages, same
usage shape). The op already existed (landed 2026-08-13, `4dfb0846dc`) with a
dry-run preview and an act mode, both `_common.archive_and_commit`-backed —
the gap this script closes is that nothing ever called it (C3,
docs/plans/2026-09-03-close-verb-archival-stops-asking-for-wri.md).

Unlike `sweep-terminal-handoffs.py`, which reaches straight past its op's
dispatch route into the shared `plan_sweep` + `archive_and_commit` primitives
(no separately-exposed classification function exists for this op), this
script invokes the REGISTERED op handler itself,
`coordinator_core.ops.fleet.archive_sizings._archive_terminal_sizings`,
in-process — never through `cc_invoke.route()`'s JSON-RPC round trip, and
never by reimplementing any scan/classify/move logic of its own. `mode` is
required and fail-closed (contract §4 version-skew guard): "already-terminal"
is the only value slice A accepts, so both calls below pass it explicitly.

Two in-process calls to the SAME handler, T1 then T3 (mirrors the op's own
confirm→act wire contract): a `dry_run:true` preview enumerates candidates
(mutates nothing), and — unless `--dry-run` was passed — every returned
candidate id feeds straight into a `dry_run:false` act call. `--dry-run`
returns after the preview call alone. This is two calls to one in-process
async function, not two process spawns — the DR-344 cost this avoids is the
`-m coordinator_core.invoke` cold-interpreter round trip `sweep-terminal-
handoffs.py`'s own docstring measures at ~1046ms/30 processes; calling the
handler directly, in this one process, pays for neither round trip.

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
Wraps: coordinator_core.ops.fleet.archive_sizings._archive_terminal_sizings
(the registered "fleet.archive_terminal_sizings" op handler, called directly —
not through cc_invoke.route()'s dispatch round trip).

Negative-spec:
  - Does NOT reimplement any of the op's scan, classification, or move
    logic — every candidate id this script acts on came straight out of the
    op's own preview response.
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

_MODE = "already-terminal"


def _ensure_claude_klabauter_on_path() -> str:
    """Idempotently put the engine root on sys.path; returns it.

    The file's ONE claude-klabauter-root path-resolution site, mirroring
    `sweep-terminal-handoffs.py`'s own `_ensure_claude_klabauter_on_path` helper.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke  # pyright: ignore[reportMissingImports] — added to sys.path at runtime by the _LIB_DIR injection above, not statically resolvable

    return cc_invoke.require_engine_on_path(__file__)


def _stamp_archive_sweeps_liveness(repo_root: str) -> None:
    """Best-effort stamp the shared `archive_sweeps` housekeeping-liveness key.

    Called from the sweep-processing tail only (never on the internal-error
    exit). One swallow point, not two: engine-root resolution, the seam
    import, and the stamp call itself are all best-effort together — a
    failure anywhere in this chain means "no liveness stamp this run", never
    a reason to mask the real sweep result the caller already computed.
    """
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
    """Print the records a `--dry-run` census would move.

    Mirrors `sweep-terminal-handoffs.py :: _print_planned_moves` — prints the
    id, since that is the whole of what the op's preview candidate carries
    that identifies the record (unlike the handoffs sweep, this op's preview
    response does not carry a pre-computed destination path).
    """
    if not candidates:
        print("dry run: no terminal sizings would be archived")
        return
    print(f"dry run: {len(candidates)} terminal sizing-object(s) would be archived:")
    for cand in candidates:
        print(f"  {cand.get('id')}")


def _print_refusal_census(skipped: "list[dict]") -> None:
    """Print every id the act call refused, grouped by reason FAMILY.

    Mirrors `sweep-terminal-handoffs.py :: _print_refusal_census`'s "terminal
    but not moved" half — this op's T1 preview carries no skip list at all
    (`build_dry_run_result` hardcodes `skipped: []`; a non-terminal/AC6-held
    record is simply not enumerated as a candidate), so there is no scan-skip
    half to print here the way the handoffs sweep prints one.
    """
    if not skipped:
        return
    print(f"terminal but not moved -- {len(skipped)} record(s):")
    for item in skipped:
        print(f"  {item.get('id')} -- {item.get('reason')}")


def main(argv: "list[str] | None" = None) -> int:
    """`argv` carries one flag, `--dry-run` — mirrors `sweep-terminal-
    handoffs.py :: main`'s own contract, including the `None`-means-
    `sys.argv[1:]` default the sibling sweep-script test harnesses rely on.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from repo_identity import resolve_checked_repo_root  # pyright: ignore[reportMissingImports] — same runtime lib-bootstrap sys.path injection as above
    from sweep_argv import parse_repo_root_argv  # pyright: ignore[reportMissingImports] — same runtime lib-bootstrap sys.path injection as above

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
        print(verdict["message"], file=sys.stderr)

    repo_root = git_repo_root

    _ensure_claude_klabauter_on_path()
    from coordinator_core.git.repo_root import git_common_dir
    from coordinator_core.ops.fleet.archive_sizings import _archive_terminal_sizings

    try:
        common_dir = Path(git_common_dir(cwd=str(repo_root)))
    except Exception as exc:
        print(f"sweep-terminal-sizings.py: git_common_dir failed: {exc}", file=sys.stderr)
        return 1

    import asyncio

    async def _preview() -> dict:
        return await _archive_terminal_sizings(
            {"mode": _MODE, "dry_run": True}, repo_root=common_dir,
        )

    try:
        preview_result = asyncio.run(_preview())
    except Exception as exc:
        print(f"sweep-terminal-sizings.py: preview failed: {exc}", file=sys.stderr)
        return 1

    candidates = preview_result.get("candidates", [])
    preview_exit_code = preview_result.get("exit_code", 1)

    if dry_run:
        if preview_exit_code != 0:
            print(
                "sweep-terminal-sizings.py: dry run failed "
                f"(exit_code={preview_exit_code})",
                file=sys.stderr,
            )
            return 1
        _print_planned_moves(candidates)
        return 0

    if preview_exit_code != 0:
        print(
            f"sweep-terminal-sizings.py: preview failed (exit_code={preview_exit_code}) "
            "-- nothing acted",
            file=sys.stderr,
        )
        _stamp_archive_sweeps_liveness(repo_root)
        return 1

    dispatch_failed = False
    act_result: dict = {}

    if candidates:
        candidate_ids = [c.get("id") for c in candidates if c.get("id")]

        async def _act() -> dict:
            return await _archive_terminal_sizings(
                {"mode": _MODE, "dry_run": False, "candidate_ids": candidate_ids},
                repo_root=common_dir,
            )

        try:
            act_result = asyncio.run(_act())
        except Exception as exc:
            print(f"sweep-terminal-sizings.py: sweep failed: {exc}", file=sys.stderr)
            dispatch_failed = True
            act_result = {}

    acted = act_result.get("acted", [])
    archived = len(acted)
    failed = act_result.get("failed", [])
    act_exit_code = act_result.get("exit_code", 0)
    if act_exit_code != 0 or failed:
        print(
            f"sweep-terminal-sizings.py: WARN: {len(failed)} "
            f"move(s) failed (acted={archived}) -- check claude-klabauter logs",
            file=sys.stderr,
        )
        dispatch_failed = True

    if archived == 0:
        print("no terminal sizings archived")
    else:
        print(f"{archived} terminal sizings archived")

    _print_refusal_census(act_result.get("skipped", []))

    _stamp_archive_sweeps_liveness(repo_root)
    if dispatch_failed:
        return 1
    return 0


if __name__ == "__main__":
    _ensure_claude_klabauter_on_path()
    from coordinator_core.cli_entry import recording_declared_writes

    with recording_declared_writes():
        _exit_code = main()
    sys.exit(_exit_code)
