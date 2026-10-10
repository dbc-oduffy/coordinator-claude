"""Warm-base discovery and delta planning for a diff-scaled klabauter publish.

The destination's own history records the source head and transform signature of the last
complete round (publish trailers). A round is warm only when that record is intact and nothing
that changes transform output moved since; otherwise it is cold with a named reason. Everything
here reads git objects in process: zero spawns.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Tuple, Union

from coordinator_core.git.git_dir import resolve_git_common_dir
from coordinator_core.git.git_objects import read_object
from coordinator_core.git.git_state import (
    _parse_tree_entries,
    diff_commit_trees,
    head_sha,
    parse_publish_trailers,
    read_commit,
)

TRANSFORM_RULE_PATHS: Tuple[str, ...] = (
    "setup/percolate-hooks/",
    "setup/publish-targets.portable",
    "setup/publish-allowlist-declarations.yaml",
    "coordinator/bin/publish.py",
    "coordinator/lib/percolate/",
    "coordinator_core/percolate/",
    "coordinator_core/ops/percolate_run.py",
)
TRANSFORM_RULE_BASENAMES: FrozenSet[str] = frozenset({".percolate-ignore"})

_TREE = 0o40000


@dataclass(frozen=True)
class PublishBase:
    dest_commit: str
    source_head: str
    signature: str


@dataclass(frozen=True)
class ColdReason:
    """`code` is one of: no-stamp, foreign-commit, partial-round, object-unreadable,
    signature-changed, rule-path-changed, multi-source-toplevel, sync-module-lacks-only-paths,
    requested."""

    code: str
    detail: str


@dataclass(frozen=True)
class WarmPlan:
    base: PublishBase
    changed: Mapping[str, FrozenSet[str]]
    deleted: Mapping[str, FrozenSet[str]]


def find_publish_base(dest_repo_root: Path) -> Union[PublishBase, ColdReason]:
    """Classify destination HEAD alone: a commit with source-head and signature trailers is the
    base; a round-only commit is `partial-round`; any other commit is `foreign-commit`."""
    sha = head_sha(dest_repo_root)
    if sha is None:
        return ColdReason("no-stamp", "destination has no HEAD")
    info = read_commit(dest_repo_root, sha)
    if info is None:
        return ColdReason("object-unreadable", sha[:12])
    t = parse_publish_trailers(info.message)
    if t.source_head and t.signature:
        return PublishBase(sha, t.source_head, t.signature)
    if t.round_id:
        return ColdReason("partial-round", sha[:12])
    subject = info.message.strip().split("\n", 1)[0]
    return ColdReason("foreign-commit", f"{sha[:12]} {subject}")


def _under(path: str, prefix: str) -> bool:
    p = prefix.strip("/")
    return not p or path == p or path.startswith(p + "/")


def _is_rule_path(path: str) -> bool:
    if path.rsplit("/", 1)[-1] in TRANSFORM_RULE_BASENAMES:
        return True
    if "tests" in path.split("/")[:-1]:
        return False
    for rule in TRANSFORM_RULE_PATHS:
        if rule.endswith("/"):
            if path.startswith(rule):
                return True
        elif path == rule:
            return True
    return False


def plan_publish_round(
    *,
    source_toplevel: Path,
    head_sha: str,
    base: Union[PublishBase, ColdReason],
    signature: str,
    row_source_prefixes: Mapping[str, Tuple[str, ...]],
) -> Union[WarmPlan, ColdReason]:
    """Warm plan: per row, changed (A/M/T) and deleted (D) source paths within its prefixes.
    A path inside several rows' prefixes lands in each of those rows."""
    if isinstance(base, ColdReason):
        return base
    if base.signature != signature:
        return ColdReason(
            "signature-changed", f"{base.signature[:12]} -> {signature[:12]}"
        )
    changes = diff_commit_trees(source_toplevel, base.source_head, head_sha)
    if changes is None:
        return ColdReason("object-unreadable", f"{base.source_head[:12]}..{head_sha[:12]}")
    for c in changes:
        if _is_rule_path(c.path):
            return ColdReason("rule-path-changed", c.path)
    changed: Dict[str, set] = {row: set() for row in row_source_prefixes}
    deleted: Dict[str, set] = {row: set() for row in row_source_prefixes}
    for c in changes:
        bucket = deleted if c.status == "D" else changed
        for row, prefixes in row_source_prefixes.items():
            if any(_under(c.path, p) for p in prefixes):
                bucket[row].add(c.path)
    return WarmPlan(
        base,
        {r: frozenset(v) for r, v in changed.items()},
        {r: frozenset(v) for r, v in deleted.items()},
    )


def _lookup(common: Path, tree_sha: str, rel: str) -> Optional[Tuple[int, str]]:
    cur = tree_sha
    parts = rel.split("/")
    for i, name in enumerate(parts):
        obj = read_object(common, cur)
        if obj is None or obj[0] != "tree":
            return None
        entries = _parse_tree_entries(obj[1])
        entry = entries.get(name) if entries else None
        if entry is None:
            return None
        if i == len(parts) - 1:
            return entry
        if entry[0] != _TREE:
            return None
        cur = entry[1]
    return None


def materialize_paths(
    source_toplevel: Path, sha: str, paths: Iterable[str], into: Path
) -> Dict[str, int]:
    """Write each named blob of commit `sha` under `into` at its rel path; return rel -> git
    mode. Symlinks become files holding the link text. Paths absent at `sha` raise."""
    info = read_commit(source_toplevel, sha)
    if info is None:
        raise RuntimeError(f"publish_delta: commit {sha} unreadable")
    common = resolve_git_common_dir(source_toplevel)
    modes: Dict[str, int] = {}
    for rel in paths:
        entry = _lookup(common, info.tree, rel)
        if entry is None or entry[0] == _TREE:
            raise RuntimeError(f"publish_delta: {rel} is not a blob at {sha[:12]}")
        obj = read_object(common, entry[1])
        if obj is None:
            raise RuntimeError(f"publish_delta: blob {entry[1]} for {rel} unreadable")
        target = Path(into) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(obj[1])
        modes[rel] = entry[0]
    return modes


def materialize_subtree(source_toplevel: Path, sha: str, rel: str, into: Path) -> Dict[str, int]:
    """`rel` (a blob or a tree) of commit `sha` written under `into` at its rel path, nothing
    else of the commit read; return rel -> git mode for every blob written. Absent at `sha`
    raises."""
    info = read_commit(source_toplevel, sha)
    if info is None:
        raise RuntimeError(f"publish_delta: commit {sha} unreadable")
    common = resolve_git_common_dir(source_toplevel)
    entry = _lookup(common, info.tree, rel)
    if entry is None:
        raise RuntimeError(f"publish_delta: {rel} is absent at {sha[:12]}")
    if entry[0] != _TREE:
        return materialize_paths(source_toplevel, sha, [rel], into)
    modes: Dict[str, int] = {}
    stack = [(rel, entry[1])]
    while stack:
        prefix, tree_sha = stack.pop()
        obj = read_object(common, tree_sha)
        entries = _parse_tree_entries(obj[1]) if obj is not None and obj[0] == "tree" else None
        if entries is None:
            raise RuntimeError(f"publish_delta: tree {tree_sha} for {prefix} unreadable")
        for name, (mode, child) in entries.items():
            child_rel = f"{prefix}/{name}"
            if mode == _TREE:
                stack.append((child_rel, child))
                continue
            blob = read_object(common, child)
            if blob is None:
                raise RuntimeError(f"publish_delta: blob {child} for {child_rel} unreadable")
            target = Path(into) / child_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob[1])
            modes[child_rel] = mode
    return modes
