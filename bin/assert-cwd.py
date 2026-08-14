# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
assert-cwd.py — standalone CLI: assert the current git worktree's top-level
directory equals an expected absolute path.

Purpose: a generic session-cwd inheritance guard. Ports the one-line Phase-3
new-project ceremony assert `[ "$(git rev-parse --show-toplevel)" = "<abs>" ]
|| exit 1` (DoE new-project/SKILL.md) into a naked-Python CLI so the ceremony
fence can invoke a settings-home forwarder instead of hand-rolling the git
subprocess + string-compare inline.

Standalone: no coordinator_core / claude-klabauter import — this is pure git + pathlib,
resolvable from any git worktree without a claude-klabauter checkout on PATH.

Usage:
    assert-cwd <expected-abs-path>

Exit codes:
    0 — cwd's git toplevel resolves to the same path as <expected-abs-path>
        (both compared as resolved absolute paths).
    1 — mismatch, or `git rev-parse --show-toplevel` failed (not inside a
        git working tree, or git not on PATH) — either way printed to stderr.
    2 — usage error (wrong arg count).

Spec backlink: scratchpad/scout-D-claude-klabauter-sizing.md § Item 2 (new-project
cwd-assert, SKILL.md:76).

Negative-spec:
  - Does NOT `cd` anywhere itself — reads the CALLING process's cwd only.
  - Does NOT accept a relative expected path silently mismatching — the
    expected path is resolved to absolute before comparison, same as the
    actual toplevel.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: assert-cwd <expected-abs-path>", file=sys.stderr)
        return 2

    expected = str(Path(argv[0]).resolve())

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"ERROR: cannot invoke git: {exc}", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        print(
            f"ERROR: git rev-parse --show-toplevel failed (not inside a git "
            f"working tree?): {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    actual = str(Path(proc.stdout.strip()).resolve())

    if actual != expected:
        print(f"ERROR: cwd is {actual}, expected {expected}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
