"""Spawn-free detection of a git operation left in progress in a clone, and
recognition of dest_refresh's own peer-merge message.

Trap: the default-message arm of ``is_own_peer_merge`` is safe only because
dest_refresh is the sole mover of the mirror; a human merge of the same
upstream with git's default message would be indistinguishable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from coordinator_core.git.git_dir import resolve_git_dir

PEER_MERGE_MARKER = "[dest-refresh peer-merge]"


def peer_merge_message(upstream: str, branch: Optional[str]) -> str:
    """The ``-m`` message both dest_refresh merges pass."""
    return f"{PEER_MERGE_MARKER} Merge {upstream} into {branch}"


@dataclass(frozen=True)
class InProgress:
    """kind is one of merge, cherry-pick, revert, rebase, bisect."""

    kind: str
    detail: str


def _first_line(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    return lines[0].strip() if lines else ""


def inspect_in_progress(repo_root: Path) -> Optional[InProgress]:
    """First in-progress operation found under the private git dir, else None.

    Order: MERGE_HEAD, CHERRY_PICK_HEAD, REVERT_HEAD, rebase-merge/,
    rebase-apply/, BISECT_LOG. File reads only; no git spawn.
    """
    gd = resolve_git_dir(repo_root)
    if (gd / "MERGE_HEAD").is_file():
        return InProgress("merge", _first_line(gd / "MERGE_MSG"))
    if (gd / "CHERRY_PICK_HEAD").is_file():
        return InProgress("cherry-pick", "")
    if (gd / "REVERT_HEAD").is_file():
        return InProgress("revert", "")
    if (gd / "rebase-merge").is_dir() or (gd / "rebase-apply").is_dir():
        return InProgress("rebase", "")
    if (gd / "BISECT_LOG").is_file():
        return InProgress("bisect", "")
    return None


def is_own_peer_merge(merge_msg_first_line: str, upstream: str) -> bool:
    """True for the marker form naming ``upstream`` or git's default
    ``Merge remote-tracking branch '<upstream>'`` (optionally ``into <b>``)
    for exactly that upstream. Anything else is not ours.
    """
    line = merge_msg_first_line.strip()
    up = re.escape(upstream)
    marker = re.escape(PEER_MERGE_MARKER)
    if re.fullmatch(rf"{marker} Merge {up}( into \S+)?", line):
        return True
    return re.fullmatch(rf"Merge remote-tracking branch '{up}'( into \S+)?", line) is not None
