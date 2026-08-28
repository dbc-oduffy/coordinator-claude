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

#: `git diff --cached --name-status -z` status letters this module reasons
#: about. A rename arrives as `R<score>` and is NOT a deletion: measured, a
#: sanctioned `git mv` of a queue entry into `archive/<queue>/<YYYY-MM>/` is
#: reported `R100`, so it never reaches the deletion branch at all.
STATUS_DELETE = "D"
STATUS_ADD = "A"
STATUS_RENAME = "R"


@dataclass(frozen=True)
class Finding:
    """One staged deletion that would erase a path still present on disk."""

    path: str
    #: True when the on-disk bytes equal HEAD's blob for this path. The
    #: stale-index phantom always looks like this -- nobody edited the file,
    #: an old index simply forgot it. A deliberate untrack of a file the
    #: author has since modified would not.
    disk_matches_head: bool

    def render(self) -> str:
        agreement = (
            "on-disk content is byte-identical to HEAD"
            if self.disk_matches_head
            else "on-disk content differs from HEAD"
        )
        return f"{self.path} -- staged for deletion, still on disk, {agreement}"


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
    """Returns the staged deletions that would erase a still-present file.

    `rows` is the staged change set for THE COMMIT BEING MADE -- not the
    repository's whole dirty state. That distinction is what keeps this quiet:
    measured on a real armed tree, a `git commit -- <pathspec>` that excludes
    the armed path builds a temporary index without it, so the hook never sees
    it and never fires. Firing on an armed path the commit does not touch
    would make this noise on a tree where the state is common, and noise gets
    disabled.

    `exists_on_disk` and `disk_matches_head` are injected so the whole
    predicate is testable without a repository -- this module runs inside a
    git hook, where the suite cannot follow it without spawning.
    """
    rows = list(rows)
    added = {path for status, path in rows if status == STATUS_ADD}

    findings: list[Finding] = []
    for status, path in rows:
        if status != STATUS_DELETE:
            continue
        if not exists_on_disk(path):
            continue  # an ordinary deletion: the file really is gone
        if path in added:
            continue  # deleted and re-added in one commit; not a disappearance
        same = disk_matches_head(path)
        if same is None:
            continue  # not in HEAD, so this commit cannot remove it from HEAD
        findings.append(Finding(path=path, disk_matches_head=same))
    return findings


def render_report(findings: "list[Finding]", override_env: str) -> str:
    """The message the hook prints. Says what will happen, not what is wrong --
    a guard that only names a rule gets overridden without being read."""
    lines = [
        "BLOCKED: this commit stages the deletion of "
        f"{len(findings)} path(s) that are still in HEAD and still on disk.",
        "",
        "On a shared tree this is usually a stale `.git/index`: a peer loaded the",
        "index before HEAD advanced and wrote it back after, so the index has",
        "forgotten a file that was committed in between. Committing now erases a",
        "live artifact inside a commit about something else.",
        "",
    ]
    lines += [f"  {f.render()}" for f in findings]
    lines += [
        "",
        "To fix rather than bypass -- refresh the index against HEAD:",
        "    git reset -- <path>        # drop the phantom staged deletion",
        "    git status -- <path>       # expect the path to go quiet",
        "",
        "Committing a narrower pathspec also avoids it: a `git commit -- <paths>`",
        "that excludes these paths cannot carry them.",
        "",
        f"If the deletion is genuinely intended, set {override_env}=1 for this commit.",
    ]
    return "\n".join(lines)
