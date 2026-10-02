"""Gate for /architecture-survey: a survey write must not add or bump a `last_attested:` line.

Lists every added, modified, or renamed page under the systems directory whose diff against
HEAD touches a `last_attested:` line. Diffs the worktree, not the index, because the survey's
pathspec commit commits worktree contents. Deleted pages and renames carrying the value forward
unchanged are not listed.

Usage: check-survey-attestation.py [--repo-root <dir>] [--systems-dir <repo-relative dir>]

Exit 0: nothing listed. Exit 1: listed paths on stdout, one per line. Exit 2: could not check.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_SYSTEMS_DIR = "docs/architecture/systems/"


def git_argv(systems_dir: str) -> list[str]:
    return [
        "git", "--no-optional-locks", "diff", "HEAD", "-G", "^last_attested:",
        "--diff-filter=AMR", "--name-only", "--", systems_dir,
    ]


def listed_paths(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--systems-dir", default=DEFAULT_SYSTEMS_DIR)
    args = parser.parse_args(argv)

    root = Path(args.repo_root)
    try:
        proc = subprocess.run(
            git_argv(args.systems_dir), cwd=root, capture_output=True, text=True,
            encoding="utf-8", check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"could not check: {exc}", file=sys.stderr)
        return 2
    if proc.returncode != 0:
        print(f"could not check: {proc.stderr.strip()}", file=sys.stderr)
        return 2

    paths = listed_paths(proc.stdout)
    for path in paths:
        print(path)
    return 1 if paths else 0


if __name__ == "__main__":
    sys.exit(main())
