# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
stub-file-gate.py — generic disk-first stub gate.

Purpose: assert each of a list of paths exists and has at least N lines,
printing a one-line PASS/FAIL verdict per path plus an overall verdict. Ports
the deep-research repo-driver.md GATE_FAIL block (~7 lines, loops 4 inventory
paths, fails if any missing or `<30` lines) into a reusable, generic CLI —
any ceremony that needs a disk-first "did the prior step actually write real
content" check can invoke this instead of hand-rolling the loop.

Usage:
    stub-file-gate --min-lines N <path> [<path> ...]

Output: one line per path (`GATE PASS: <path> (<n> lines)` or
`GATE FAIL: <reason>`), followed by the overall verdict line.

Exit codes:
    0 — every path exists and has >= N lines.
    1 — any path missing, unreadable, or has < N lines.
    2 — usage error.

Spec backlink: scratchpad/scout-D-claude-klabauter-sizing.md § Item 7a (deep-research
GATE_FAIL block, repo-driver.md:338).

Negative-spec:
  - Does NOT treat a trailing-newline-less final line as absent — line count
    is computed by splitting on newlines, matching `wc -l`-adjacent intent
    (a file with content but no trailing newline still counts its last line).
  - Does NOT stop at the first failure — every path is checked and reported
    so a caller sees the full failure set in one invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _count_lines(path: Path) -> int:
    """Return the number of lines in *path*'s text content.

    A non-empty file with no trailing newline still counts its final line
    (splitlines() semantics), matching the intent of "how many lines of
    real content does this file hold" rather than a strict newline count.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if text == "":
        return 0
    return len(text.splitlines())


def _check_one(path_str: str, min_lines: int) -> tuple[bool, str]:
    """Check a single path. Returns (passed, message)."""
    path = Path(path_str)
    if not path.exists():
        return False, f"GATE FAIL: {path_str} does not exist"
    if not path.is_file():
        return False, f"GATE FAIL: {path_str} is not a regular file"
    try:
        n = _count_lines(path)
    except OSError as exc:
        return False, f"GATE FAIL: {path_str} unreadable: {exc}"
    if n < min_lines:
        return False, f"GATE FAIL: {path_str} has {n} line(s), need >= {min_lines}"
    return True, f"GATE PASS: {path_str} ({n} lines)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="stub-file-gate",
        description="Assert each path exists and has >= N lines.",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        required=True,
        metavar="N",
        help="minimum required line count per path",
    )
    parser.add_argument("paths", nargs="+", metavar="path")
    args = parser.parse_args(argv)

    if args.min_lines < 0:
        print("ERROR: --min-lines must be >= 0", file=sys.stderr)
        return 2

    all_passed = True
    for path_str in args.paths:
        passed, message = _check_one(path_str, args.min_lines)
        print(message)
        if not passed:
            all_passed = False

    if all_passed:
        print(f"GATE PASS: all {len(args.paths)} path(s) satisfy >= {args.min_lines} lines")
        return 0
    print("GATE FAIL: one or more paths failed the gate")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
