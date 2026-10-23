"""Resolve a `merge --no-commit` whose only conflicts are round-derived files by regenerating them.

The stamp files keep HEAD's (this round's) bytes and the expected manifest is rebuilt over the
merged index; any other unmerged path leaves the merge untouched for the caller to abort. Never
commits. Every git call goes through the caller's runner, so no spawn escapes the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from coordinator_core.git.run import GitResult
from percolate.round_derived import (
    EXPECTED_MANIFEST_REL,
    REGENERATED_BASENAMES,
    blob_sha,
    is_peer_merge_derived,
    manifest_bytes,
    source_head_of,
)


@dataclass(frozen=True)
class RegenResult:
    """`ok` False means `unmerged_other` names the paths a human must reconcile."""

    ok: bool
    unmerged_other: Tuple[str, ...] = ()
    regenerated: Tuple[str, ...] = ()


def _is_stamp(rel: str) -> bool:
    return rel.replace("\\", "/").rsplit("/", 1)[-1] in REGENERATED_BASENAMES


def _source_head(git: Callable[[List[str]], GitResult]) -> Optional[str]:
    for ref in ("HEAD", "MERGE_HEAD"):
        res = git(["show", f"{ref}:{EXPECTED_MANIFEST_REL}"])
        if res.returncode == 0:
            head = source_head_of(res.stdout.encode("utf-8"))
            if head:
                return head
    return None


def resolve_derived_after_merge(
    repo_root: Path, git: Callable[[List[str]], GitResult]
) -> RegenResult:
    """Precondition: `merge --no-commit <upstream>` just ran, clean or conflicted.

    Spawns: diff, ls-files, checkout, show, add.
    """
    diff = git(["diff", "--name-only", "--diff-filter=U", "-z"])
    unmerged = tuple(p for p in diff.stdout.split("\0") if p)
    other = tuple(p for p in unmerged if not is_peer_merge_derived(p))
    if diff.returncode != 0 or other:
        return RegenResult(ok=False, unmerged_other=other)

    ls = git(["ls-files", "-s", "-z"])
    if ls.returncode != 0:
        return RegenResult(ok=False, unmerged_other=unmerged)
    paths: Dict[str, str] = {}
    staged_any = set()
    for entry in ls.stdout.split("\0"):
        if not entry:
            continue
        meta, _, rel = entry.partition("\t")
        fields = meta.split()
        staged_any.add(rel)
        if len(fields) == 3 and fields[2] == "0":
            paths[rel] = fields[1]

    stamps = sorted(r for r in staged_any if _is_stamp(r))
    restored: List[str] = []
    if stamps:
        co = git(["checkout", "HEAD", "--", *stamps])
        if co.returncode == 0:
            restored = stamps
        else:
            for rel in stamps:
                if git(["checkout", "HEAD", "--", rel]).returncode == 0:
                    restored.append(rel)
    stuck = tuple(r for r in unmerged if _is_stamp(r) and r not in restored)
    if stuck:
        return RegenResult(ok=False, unmerged_other=stuck)
    for rel in restored:
        paths[rel] = blob_sha((Path(repo_root) / rel).read_bytes())

    to_add = list(restored)
    manifest_written = False
    head = _source_head(git)
    if head is not None:
        (Path(repo_root) / EXPECTED_MANIFEST_REL).write_bytes(manifest_bytes(paths, head))
        to_add.append(EXPECTED_MANIFEST_REL)
        manifest_written = True
    if EXPECTED_MANIFEST_REL in unmerged and not manifest_written:
        return RegenResult(ok=False, unmerged_other=(EXPECTED_MANIFEST_REL,))

    if to_add:
        add = git(["add", "--", *to_add])
        if add.returncode != 0:
            return RegenResult(ok=False, unmerged_other=tuple(to_add))
    return RegenResult(ok=True, regenerated=tuple(to_add))
