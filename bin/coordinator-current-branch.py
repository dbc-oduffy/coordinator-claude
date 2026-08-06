#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-current-branch.py — output the canonical (on-disk) branch name.

Naked-Python port of coordinator-current-branch (2026-07-22 Windows de-bash
campaign, chunk C2 — live-defect carve-out for an uncaught WinError-193 on
Windows callers of the bash original).

Why this exists: on Windows's case-insensitive filesystem, `.git/HEAD` can
store a ref name in a case different from the actual on-disk ref file (e.g.
HEAD says `refs/heads/work/MACHINE-A/2026-05-07` but the ref file is
`refs/heads/work/machine-a/2026-05-07`). `git branch --show-current` reads
HEAD literally and returns the stored case; `git push origin <that-name>`
then fails with "cannot be resolved to branch" because git's ref lookup is
case-sensitive against the canonical name.

This helper canonicalizes via `git for-each-ref`, which returns the on-disk
case (the form the remote also expects). Use anywhere a script or doctrine
doc would otherwise call `git push origin "$(git branch --show-current)"` —
the unsafe pattern is a Windows-only latent failure waiting for a mixed-case
daily-branch.

Lesson source: state/lessons.md "git branch --show-current returns HEAD's
stored case, not the on-disk canonical case" (2026-05-07).

Falls back to the raw branch name on lookup failure so we don't regress on
Linux/macOS where the hazard doesn't exist.

Detached HEAD / no current branch: prints nothing and exits 0 (callers that
require a branch must check for empty output, same as
`git branch --show-current`).

Usage:
    coordinator-current-branch.py

Spec backlink: bash original retired this port — see git history (deleted, not
archived), commit 13e17751.
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    try:
        raw = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0

    if raw.returncode != 0:
        return 0

    raw_branch = raw.stdout.strip()
    if not raw_branch:
        return 0

    try:
        refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        refs = None

    branch = raw_branch
    if refs is not None and refs.returncode == 0:
        target = raw_branch.lower()
        for line in refs.stdout.splitlines():
            if line.lower() == target:
                branch = line
                break

    print(branch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
