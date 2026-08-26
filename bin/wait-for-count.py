# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""wait-for-count.py — generic poll-until-directory-count-threshold CLI.

Blocks (polling at a fixed interval) until a directory's matching-entry
count reaches a minimum, or a wall-clock timeout elapses, whichever comes
first. Exits 0 on threshold-met, 1 on timeout -- callers get an unambiguous
signal instead of the bare `until ... || ...; do sleep; done` bash idiom's
silent fall-through (that idiom has no exit-code contract at all: it just
stops looping, success or timeout indistinguishable to the caller).

Replaces the inline polling fence in DoE-claude
coordinator/commands/architecture-survey.md (waiting for N scout-agent
output files to land in a scratch directory before fanning out analysts) --
a genuinely atomic single-op idiom (poll-until-condition) that a
skills-carry-no-code fence-elimination pass cannot decompose into N
metachar-free lines, so it needed a real entrypoint rather than a
presentation-only fix.

Usage:
    wait-for-count --dir <path> --min N
        [--pattern GLOB] [--timeout-sec SECS] [--poll-interval-sec SECS]

    --dir               Directory to poll. Need not exist yet (a
                         not-yet-created directory counts as 0 entries, not
                         an error -- the common case for a scratch dir a
                         background wave is about to populate).
    --min N             Required. Threshold entry count (>=).
    --pattern GLOB      Glob pattern (non-recursive, Path.glob semantics)
                         entries must match to count. Default `*` (every
                         entry, files and directories alike -- matches bare
                         `ls | wc -l` counting behavior).
    --timeout-sec SECS  Wall-clock budget. Default 600 (10 minutes, matching
                         the architecture-survey.md fence this replaces).
                         Capped at MAX_TIMEOUT_SEC (1200) — see "Timeout
                         ceiling" below.
    --poll-interval-sec SECS
                         Sleep between checks. Default 30 (matching the same
                         fence). Capped at MAX_POLL_INTERVAL_SEC (60). The final
                         wait before the deadline is clamped so the CLI does not
                         oversleep past the timeout by a whole extra interval.

Timeout ceiling: both dials are clamped silently, via `min()`, to the module
constants below — a caller may ask for LESS, never for more. This CLI is a
deliberate wait on ANOTHER agent's output, not our own compute, so it is NOT
held to the 2s process regime and a tight bound would make it useless. The
ceiling is a runaway bound, not a budget: it separates "this wave is slow" from
"this process is parked forever" on a box shared with ~50 concurrent sessions.

`MAX_TIMEOUT_SEC`'s value is not invented here — it is
`coordinator_core.composition_budget.FLEET_AGGREGATE_ELAPSED_BUDGET`, the
already-ratified fleet aggregate elapsed ceiling, imported so the two move
together. The principle: a waiter must never outlive the composition it is
waiting inside. A wait that outlives its own composition is waiting on something
nothing will deliver. Same ceiling, same reasoning, as the in-engine twin
`coordinator_core/ops/poll_scratch_dir.py` (op `fanout.poll_scratch_dir`).

The poll interval is bounded separately because an interval larger than the
remaining budget is pure latency — the loop cannot observe the count it waits on
while asleep.

Exit codes:
    0   threshold met before the deadline. Prints
        `count=<n> threshold=<min> dir=<path>` to stdout.
    1   timeout elapsed with the threshold still unmet. Prints
        `TIMEOUT: count=<n> threshold=<min> dir=<path> after <secs>s` to
        stderr.
    2   usage error (argparse).

Negative-spec: does not create <dir>, does not inspect entry contents
(count-only -- an empty file and a populated one both count as one entry),
and is not recursive (a nested scratch/<run-id>/sub/ entry does not count
unless <pattern> is itself written to traverse it, which Path.glob's single-
level semantics do not support -- use `**/GLOB` deliberately if recursion is
ever needed, `Path.glob` supports it natively).

Spec backlink: coordinator/commands/architecture-survey.md (DoE-claude) --
    scout-wave completion poll, "Run with run_in_background: true".
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # coordinator/bin -> coordinator -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from coordinator_core.composition_budget import FLEET_AGGREGATE_ELAPSED_BUDGET  # noqa: E402

_UNARMED_FLEET_BUDGET_FALLBACK_SEC: float = 1200.0
"""Ceiling used when the fleet budget is disarmed (`FLEET_AGGREGATE_ELAPSED_BUDGET
is None` — its documented "no aggregate ceiling" state). Disarming the
composition instrument must not silently unbound this waiter: "no ceiling on the
composition" is a decision about telemetry, not a licence for one process to
block forever."""

MAX_TIMEOUT_SEC: float = (
    FLEET_AGGREGATE_ELAPSED_BUDGET
    if FLEET_AGGREGATE_ELAPSED_BUDGET is not None
    else _UNARMED_FLEET_BUDGET_FALLBACK_SEC
)
"""Hard ceiling on --timeout-sec — see module docstring "Timeout ceiling"."""

MAX_POLL_INTERVAL_SEC: float = 60.0
"""Hard ceiling on --poll-interval-sec — see module docstring "Timeout
ceiling"."""


def clamp_dials(timeout_sec: float, poll_interval_sec: float) -> tuple[float, float]:
    """Clamp the two caller-supplied wait dials to their ceilings.

    Idempotent, so both `wait_for_count` (the authority, covering any importer)
    and `main` (which reports the budget in its TIMEOUT line) can call it without
    the value being reduced twice.
    """
    return (
        min(float(timeout_sec), MAX_TIMEOUT_SEC),
        min(float(poll_interval_sec), MAX_POLL_INTERVAL_SEC),
    )


def count_matches(dir_path: Path, pattern: str) -> int:
    """Count directory entries matching `pattern` (non-recursive). A
    not-yet-existing directory counts as 0, not an error."""
    if not dir_path.is_dir():
        return 0
    return sum(1 for _ in dir_path.glob(pattern))


def wait_for_count(
    dir_path: Path,
    pattern: str,
    minimum: int,
    timeout_sec: float,
    poll_interval_sec: float,
    *,
    now_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[bool, int]:
    """Poll until count_matches(dir_path, pattern) >= minimum or the
    timeout elapses. Returns (met, final_count). Always checks at least
    once before ever sleeping, so a threshold already satisfied (or a
    timeout_sec of 0) returns immediately without blocking.

    Both dials are clamped via `clamp_dials` before the loop starts — a caller
    asking above either ceiling gets the ceiling, never what it asked for."""
    timeout_sec, poll_interval_sec = clamp_dials(timeout_sec, poll_interval_sec)
    deadline = now_fn() + timeout_sec
    while True:
        count = count_matches(dir_path, pattern)
        if count >= minimum:
            return True, count
        remaining = deadline - now_fn()
        if remaining <= 0:
            return False, count
        sleep_fn(min(poll_interval_sec, remaining))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wait-for-count",
        description="Block until a directory's matching-entry count reaches a "
        "threshold, or a timeout elapses.",
    )
    parser.add_argument("--dir", required=True, help="Directory to poll.")
    parser.add_argument("--min", required=True, type=int, help="Threshold entry count (>=).")
    parser.add_argument("--pattern", default="*", help="Glob pattern entries must match (default: *).")
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=600.0,
        help=f"Wall-clock budget (default: 600, capped at {MAX_TIMEOUT_SEC:g}).",
    )
    parser.add_argument(
        "--poll-interval-sec",
        type=float,
        default=30.0,
        help=f"Sleep between checks (default: 30, capped at {MAX_POLL_INTERVAL_SEC:g}).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    dir_path = Path(args.dir)
    timeout_sec, poll_interval_sec = clamp_dials(args.timeout_sec, args.poll_interval_sec)

    met, count = wait_for_count(dir_path, args.pattern, args.min, timeout_sec, poll_interval_sec)

    if met:
        print(f"count={count} threshold={args.min} dir={dir_path}")
        return 0

    print(
        f"TIMEOUT: count={count} threshold={args.min} dir={dir_path} after {timeout_sec}s",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
