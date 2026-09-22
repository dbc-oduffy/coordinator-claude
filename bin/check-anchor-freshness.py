"""check-anchor-freshness — flag a coordinator plugin triple anchor that did not move this week.

WHY THIS EXISTS. `/workweek-complete` bumps the plugin triple anchor
(`.version` in `coordinator/.claude-plugin/plugin.json`). Nothing notices when a week goes by
without one, so a missed bump surfaces only if the operator happens to remember the last
release — the discharge test (`docs/wiki/invisible-doctrine.md`) names that as unfinished work.
`/workweek-start` Step 1 reads this instead of running the query by hand.

WHY `-G`, NOT A PATH-SCOPED LOG. A plain path-scoped `git log` counts any commit touching
`plugin.json`, so an unrelated edit to that file would silence a genuinely missed bump. The
pickaxe restricts the match to commits whose diff adds or removes a `"version"` line.

Scoped to the coordinator plugin triple only. The engine anchor has its own cadence question
pending a converged contract and is deliberately not checked here.

Exit status is 0 whether or not the anchor is stale — a missed bump is a finding for the
operator, not an error condition, and a non-zero exit would read as a broken ceremony step.
Exit 2 is reserved for an unusable repo (git absent, not a work tree).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# A console-subsystem child with no console of its own allocates a fresh
# conhost on Windows -- with a visible window. Every git spawn below is
# short-lived and output-captured, so without this each one flashes.
# 0 on POSIX, where the flag does not exist.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

ANCHOR = Path("coordinator") / ".claude-plugin" / "plugin.json"

FLAG = (
    "the coordinator plugin triple anchor did not move in the prior week — "
    "run `/workweek-complete` to bump it."
)


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _anchor_commits(root: Path, window: str) -> str | None:
    """Commits in `window` whose diff adds/removes a `"version"` line in the anchor.

    Returns None when git itself is unusable — distinct from an empty string, which is the
    stale-anchor finding.
    """
    try:
        proc = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(root),
                "log",
                f"--since={window}",
                "-G",
                '"version"',
                "--format=%h %s",
                "--",
                ANCHOR.as_posix(),
            ],
            capture_output=True,
            text=True,
            **_NO_CONSOLE,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-anchor-freshness",
        description="Flag a coordinator plugin triple anchor unbumped within the window.",
    )
    parser.add_argument(
        "--window",
        default="7 days ago",
        help='git --since window (default: "7 days ago")',
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repo root (default: auto-discover from cwd)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the fresh-anchor line")
    args = parser.parse_args(argv)

    root = args.root or _repo_root(Path.cwd().resolve())
    if root is None or not (root / ANCHOR).exists():
        print(
            f"check-anchor-freshness: no {ANCHOR.as_posix()} under "
            f"{root or Path.cwd()} — nothing to check",
            file=sys.stderr,
        )
        return 2

    found = _anchor_commits(root, args.window)
    if found is None:
        print("check-anchor-freshness: git unavailable or not a work tree", file=sys.stderr)
        return 2
    if found:
        if not args.quiet:
            print(f"anchor moved within {args.window}:\n{found}")
        return 0
    print(FLAG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
