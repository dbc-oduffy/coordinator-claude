# guard-not-a-hook-entrypoint
# Native git pre-commit hook, not a hooks.json entrypoint. Same shape and same
# reasoning as guard-doctrine-surface-ratio-precommit.py: a PreToolUse guard
# fires before any commit exists and sees one tool call, so it cannot know
# which paths the commit will actually carry. At pre-commit time the staged set
# for THIS commit exists and is directly readable.
"""Native git pre-commit hook: refuse a commit that would delete a path still
present in HEAD and on disk.

WHY THIS LAYER AND NOT THE BASH GUARD. The obvious cheaper answer is to extend
the existing scope guard, which already notices part of this and reports it as
an ownership question ("staged but not in this session's touch list"). That
guard's decision logic lives in the engine plane, not in this repo, so
extending it is a cross-plane change with no standing grant behind it. This
layer is complete on its own and needs no such grant.

WHY IT IS QUIET BY CONSTRUCTION, measured rather than argued. With an armed
phantom present on a real tree:

    git commit -m "..." -- other.md     hook sees:  A other.md
                                        commit carries: other.md only
    git commit -m "..."   (bare)        hook sees:  A another.md
                                                    D sent-memo.md
                                        commit carries BOTH -- the second
                                        being a file still in HEAD and on disk

A pathspec commit makes git build a temporary index holding only those paths,
so the armed path is invisible here and this hook stays silent. It fires on
exactly the case that loses data: a commit that would actually carry the
deletion. Firing merely because the tree has an armed path would make it noise
on a tree where that state is common, and noise gets disabled.

ALL LOGIC LIVES IN `_phantom_staged_deletion.py`, which is pure and unit
tested. This file is the untested wrapper: run git, hand the rows over, print,
exit. Do not move predicate logic in here -- a git hook is not reachable from
`pytest` without spawning, and the suite's spawn budget is already in breach.

INHERITING `GIT_INDEX_FILE` IS LOAD-BEARING, NOT INCIDENTAL. Git sets it (and
`GIT_DIR`/`GIT_WORK_TREE`) when it fires a pre-commit hook, pointing at the
index for THIS commit -- which for a pathspec commit is a temporary one holding
only those paths. That inheritance is exactly why the scoped-commit case above
stays quiet. Do not scrub the git environment or pass an explicit `--git-dir`
here to make the subprocess "cleaner": that repoints these reads at the
repository index instead, and the guard would start firing on armed paths the
commit does not touch -- the noise mode that gets a guard disabled. The
opposite hazard, a hook spawning git in a *different* cwd and staging into the
real index through the inherited variable, is
`concurrent-em-hazards.md` H-`GIT_INDEX_FILE`; nothing here changes directory.

NEVER TAKES `.git/index.lock`. Every git call here is a read
(`diff --cached`, `rev-parse`, `cat-file`) and passes `--no-optional-locks` so
none of them opportunistically refreshes the index. A detector that serialises
commits on a tree this busy would be worse than the bug it prevents.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _phantom_staged_deletion import (  # noqa: E402
    classify,
    parse_name_status_z,
    render_report,
)

OVERRIDE_ENV = "COORDINATOR_OVERRIDE_PHANTOM_STAGED_DELETION"


def _git(*args: str) -> "subprocess.CompletedProcess[bytes]":
    return subprocess.run(
        ["git", "--no-optional-locks", *args],
        capture_output=True,
        check=False,
        # A git hook runs on every commit, including from headless Windows
        # shells where a console-spawning child flashes a window each time.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main() -> int:
    if os.environ.get(OVERRIDE_ENV):
        return 0

    staged = _git("diff", "--cached", "--name-status", "-z")
    if staged.returncode != 0:
        # An unreadable staged set is not evidence of a phantom. Fail OPEN and
        # say so: a pre-commit hook that blocks whenever git hiccups gets
        # uninstalled, and this guard is worth more alive than strict.
        print(
            "[phantom-deletion-guard] could not read the staged set "
            f"(git exited {staged.returncode}); allowing the commit",
            file=sys.stderr,
        )
        return 0

    rows = parse_name_status_z(staged.stdout.decode("utf-8", "surrogateescape"))
    if not any(status == "D" for status, _ in rows):
        return 0

    def exists_on_disk(path: str) -> bool:
        return Path(path).exists()

    def disk_matches_head(path: str):
        """None when the path is not in HEAD -- then this commit cannot be
        removing it from HEAD, whatever the index says."""
        head = _git("cat-file", "blob", f"HEAD:{path}")
        if head.returncode != 0:
            return None
        try:
            return Path(path).read_bytes() == head.stdout
        except OSError:
            return None

    findings = classify(
        rows,
        exists_on_disk=exists_on_disk,
        disk_matches_head=disk_matches_head,
    )
    if not findings:
        return 0

    print(render_report(findings, OVERRIDE_ENV), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
