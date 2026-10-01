"""Pure predicate for the phantom-staged-deletion guard: is a staged deletion
in this commit about to erase a file that is still in HEAD and still on disk?

THE HAZARD. On a tree a dozen sessions share, `.git/index` is shared mutable
state. A session loads the index at T0; another tool commits at T1 and HEAD
advances; the first session writes its T0-derived index back at T2. The index
is now BEHIND HEAD, and `git status` reports one path as both `D ` (staged
deletion, HEAD-vs-index) and `??` (untracked, index-vs-worktree) while the file
is present in HEAD and on disk. The next bare `git commit` carries that
deletion, erasing a live artifact inside a commit about something else. A
leaked staged ADD is visible in review as an unexpected file; a leaked staged
DELETE removes evidence.

Full write-up, mechanism, and what is NOT established:
`state/bug-backlog/2026-08-28-a-stale-shared-index-arms-a-phantom-deletion-of-any-freshly-committed-path.yaml`.

THREE VANTAGE POINTS, NOT TWO. This is the design constraint, and it is why the
hazard survived six sessions misdiagnosed. Index-versus-worktree alone reads as
"a file was deleted and an untracked file appeared." HEAD-versus-index alone
reads as "a committed file is staged for deletion." Both are ordinary. Only
adding disk-versus-HEAD shows that the file the index says is gone is sitting
on disk with HEAD's own content. `classify()` therefore takes all three as
separate inputs and refuses to conclude from any two.

WHAT THIS DELIBERATELY DOES NOT DO. It does not distinguish the stale-index
phantom from a deliberate `git rm --cached` -- measured, they are byte-identical
in `git status` (`D ` plus `??`, file on disk). Both mean a path in HEAD is
about to leave HEAD while its content sits on disk, so both are worth stopping;
the caller offers an override rather than pretending to tell them apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

#: `git diff --cached --name-status -z` status letters. A rename arrives as
#: `R<score>`, not `D` -- a sanctioned `git mv` into an archive dir is
#: reported as a rename and never reaches the deletion branch.
STATUS_DELETE = "D"
STATUS_ADD = "A"
STATUS_RENAME = "R"


@dataclass(frozen=True)
class Finding:
    """One staged deletion that would erase a path still present on disk."""

    path: str
    #: True when on-disk bytes equal HEAD's blob for this path: the
    #: stale-index phantom case (nobody edited the file, the index just
    #: forgot it). A deliberate untrack of a modified file would be False.
    disk_matches_head: bool

    def render(self) -> str:
        agreement = "disk = HEAD" if self.disk_matches_head else "disk differs from HEAD"
        return f"{self.path} ({agreement})"


def parse_name_status_z(raw: str) -> "list[tuple[str, str]]":
    """Parses `git diff --cached --name-status -z` into (status, path) rows.

    NUL-delimited by construction: a path with a space or a newline in it is
    exactly the path a naive line split would mangle, and mangling it here
    would drop it from the check silently.

    A rename or copy record spends THREE fields -- status, source, destination
    -- so its destination must be consumed or every subsequent row shifts by
    one and the whole parse walks off. Renames are returned under their
    DESTINATION path, since that is the path the commit ends up carrying.
    """
    fields = [f for f in raw.split("\0") if f != ""]
    rows: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in (STATUS_RENAME, "C"):
            if i + 2 >= len(fields):
                break
            rows.append((status[0], fields[i + 2]))
            i += 3
            continue
        if i + 1 >= len(fields):
            break
        rows.append((status[0], fields[i + 1]))
        i += 2
    return rows


def classify(
    rows: Iterable["tuple[str, str]"],
    *,
    exists_on_disk: Callable[[str], bool],
    disk_matches_head: Callable[[str], Optional[bool]],
) -> "list[Finding]":
    """`rows` is the staged change set for the commit being made, not the
    repo's whole dirty state -- a `git commit -- <pathspec>` excluding an
    armed path builds a temporary index without it, so this never fires
    for paths the commit doesn't touch.

    `exists_on_disk`/`disk_matches_head` are injected so this is testable
    without a repository; the module runs inside a git hook."""
    rows = list(rows)
    added = {path for status, path in rows if status == STATUS_ADD}

    findings: list[Finding] = []
    for status, path in rows:
        if status != STATUS_DELETE:
            continue
        if not exists_on_disk(path):
            continue  # ordinary deletion: the file really is gone
        if path in added:
            continue  # deleted and re-added in one commit; not a disappearance
        same = disk_matches_head(path)
        if same is None:
            continue  # not in HEAD, so this commit cannot remove it from HEAD
        findings.append(Finding(path=path, disk_matches_head=same))
    return findings


def render_report(findings: "list[Finding]") -> str:
    """Says what will happen, not what is wrong -- a guard that only names a
    rule gets overridden without being read. The override lives in the wiki
    page the last line points at, never in this text."""
    lines = [
        f"BLOCKED: this commit deletes {len(findings)} path(s) still in HEAD and on disk"
        " (stale shared index?):",
    ]
    lines += [f"  {f.render()}" for f in findings]
    lines += [
        "Fix: git reset -- <path>, then commit again.",
        "Intended deletion: coordinator/docs/wiki/concurrent-em-git-operations/concurrent-em-hazards.md H2.",
    ]
    return "\n".join(lines)
