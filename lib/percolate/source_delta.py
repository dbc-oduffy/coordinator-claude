"""In-process source delta between a destination's recorded source head and a round's pinned sha.

The base comes from the destination's publish trailers (`publish_delta.find_publish_base`); the
diff is a git tree diff over objects read in process, descending only into differing subtrees.
Zero spawns. Git blob identity is the change oracle, never mtime. A rename appears as one deleted
and one changed path (no rename detection).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Optional, Union

from coordinator_core.git.git_dir import resolve_git_common_dir
from coordinator_core.git.git_objects import read_object
from coordinator_core.git.git_state import _parse_tree_entries, diff_commit_trees, read_commit
from percolate.publish_delta import ColdReason, PublishBase, find_publish_base

_TREE = 0o40000


@dataclass(frozen=True)
class SourceDelta:
    """`changed`: rel -> blob sha at `head_sha` for every added, modified or mode-flipped path.
    `deleted`: rel paths present at `base_sha` and absent at `head_sha`.
    `unchanged_blob(rel)`: the blob sha at `head_sha` when `rel` is byte- and mode-identical at
    `base_sha`; None when `rel` is changed, deleted, absent or not a blob."""

    base_sha: str
    head_sha: str
    changed: Dict[str, str]
    deleted: FrozenSet[str]
    unchanged_blob: Callable[[str], Optional[str]]


def _blob_lookup(
    common: Path, root_tree: str, changed: Dict[str, str], deleted: FrozenSet[str]
) -> Callable[[str], Optional[str]]:
    trees: Dict[str, Optional[Dict[str, tuple]]] = {}

    def load(tree_sha: str) -> Optional[Dict[str, tuple]]:
        if tree_sha not in trees:
            obj = read_object(common, tree_sha)
            trees[tree_sha] = (
                _parse_tree_entries(obj[1]) if obj is not None and obj[0] == "tree" else None
            )
        return trees[tree_sha]

    def unchanged_blob(rel: str) -> Optional[str]:
        if rel in changed or rel in deleted:
            return None
        cur = root_tree
        parts = rel.split("/")
        for i, name in enumerate(parts):
            entries = load(cur)
            entry = entries.get(name) if entries else None
            if entry is None:
                return None
            if i == len(parts) - 1:
                return None if entry[0] == _TREE else entry[1]
            if entry[0] != _TREE:
                return None
            cur = entry[1]
        return None

    return unchanged_blob


def source_delta(
    dest_repo_root: Path, source_toplevel: Path, pinned_sha: str
) -> Union[SourceDelta, ColdReason]:
    """Delta from the destination's recorded source head to `pinned_sha`. A ColdReason (full pass)
    when the destination has no usable base or any object is unreadable; never raises."""
    try:
        base = find_publish_base(Path(dest_repo_root))
        if isinstance(base, ColdReason):
            return base
        assert isinstance(base, PublishBase)
        head = read_commit(source_toplevel, pinned_sha)
        if head is None:
            return ColdReason("object-unreadable", pinned_sha[:12])
        changes = diff_commit_trees(source_toplevel, base.source_head, pinned_sha)
        if changes is None:
            return ColdReason("object-unreadable", f"{base.source_head[:12]}..{pinned_sha[:12]}")
        changed = {c.path: c.new_sha for c in changes if c.status != "D" and c.new_sha}
        deleted = frozenset(c.path for c in changes if c.status == "D")
        common = resolve_git_common_dir(source_toplevel)
        return SourceDelta(
            base.source_head,
            pinned_sha,
            changed,
            deleted,
            _blob_lookup(common, head.tree, changed, deleted),
        )
    except Exception as exc:  # unreadable repo state is a full pass, not a refusal
        return ColdReason("object-unreadable", f"{type(exc).__name__}: {exc}")
