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
    --poll-interval-sec SECS
                         Sleep between checks. Default 30 (matching the same
                         fence). The final wait before the deadline is
                         clamped so the CLI does not oversleep past the
                         timeout by a whole extra interval.

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
    timeout_sec of 0) returns immediately without blocking."""
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
    parser.add_argument("--timeout-sec", type=float, default=600.0, help="Wall-clock budget (default: 600).")
    parser.add_argument(
        "--poll-interval-sec", type=float, default=30.0, help="Sleep between checks (default: 30)."
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    dir_path = Path(args.dir)

    met, count = wait_for_count(
        dir_path, args.pattern, args.min, args.timeout_sec, args.poll_interval_sec
    )

    if met:
        print(f"count={count} threshold={args.min} dir={dir_path}")
        return 0

    print(
        f"TIMEOUT: count={count} threshold={args.min} dir={dir_path} after {args.timeout_sec}s",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
