"""Land exactly N writes and D deletions on a destination repo's HEAD.

Cost scales with the diff: writes whose (blob sha, mode) already equal HEAD's are dropped,
only the surviving paths are dirty-checked, written, and committed. Any failure after the
first write restores every touched path from its HEAD blob.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from coordinator_core.git import commit as _gcommit
from coordinator_core.git.git_dir import resolve_git_common_dir
from coordinator_core.git.git_objects import read_object
from coordinator_core.git.git_state import head_blobs

_EXEC = 0o100755
_LINK = 0o120000


@dataclass(frozen=True)
class DestWrite:
    rel: str
    data: bytes
    mode: int  # 0o100644 | 0o100755 | 0o120000


@dataclass(frozen=True)
class LandOutcome:
    commit_sha: Optional[str]
    written: Tuple[str, ...]
    deleted: Tuple[str, ...]
    unchanged: Tuple[str, ...]


class DestDirtyError(RuntimeError):
    """A path to be touched differs from HEAD in the worktree. Nothing was written."""


class RemovalSourceLiveError(RuntimeError):
    """A removal names a path whose source still exists. Raised before any write."""


def refuse_removals_with_live_source(source_root: Path, removals: Sequence[str], row: str) -> None:
    """Refuse a row's removals when any one's source path still exists.

    Invariant (coordinator-content-repo-em's condition of assent for the removal side, "in the code,
    not in the procedure"): a stale or misrecorded delta must not delete a live file from
    a mirror every box resolves its engine from. Loud, never a silent skip: a live source
    behind a removal means the delta is wrong. `lexists`, not `exists`: a symlink whose
    target is missing is still a live path."""
    present = [rel for rel in removals if os.path.lexists(Path(source_root) / rel)]
    if not present:
        return
    shown = present[:20]
    more = len(present) - len(shown)
    raise RemovalSourceLiveError(
        f"publish: row {row} names {len(present)} removal(s) whose source still exists at "
        f"{source_root} -- refusing the round before any write.\n"
        + "".join(f"    ! {rel} (manifest.removed, row {row})\n" for rel in shown)
        + (f"    ... and {more} more\n" if more else "")
    )


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _read_head_blob(common: Path, sha: str) -> bytes:
    obj = read_object(common, sha)
    if obj is None:
        raise RuntimeError(f"diff_commit: HEAD blob {sha} unreadable")
    return obj[1]


def _worktree_shas(path: Path) -> Tuple[str, ...]:
    """Blob shas the worktree bytes stand for: raw, plus CRLF->LF when they differ.

    Trap: a `core.autocrlf=true` checkout holds CRLF bytes for an LF blob, and git calls
    that clean; comparing raw bytes alone reads every such path as dirty."""
    try:
        data = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return ()
    lf = data.replace(b"\r\n", b"\n")
    return (_blob_sha(data),) if lf == data else (_blob_sha(data), _blob_sha(lf))


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == _LINK and os.name != "nt":
        tmp = path.with_name(f".{path.name}.dc-{os.getpid()}")
        tmp.unlink(missing_ok=True)
        os.symlink(data.decode("utf-8"), tmp)
        os.replace(tmp, path)
        return
    tmp = path.with_name(f".{path.name}.dc-{os.getpid()}")
    try:
        tmp.write_bytes(data)
        if os.name != "nt":
            tmp.chmod(0o755 if mode == _EXEC else 0o644)
        try:
            os.replace(tmp, path)
        except PermissionError:
            if not path.exists():
                raise
            from coordinator_core.install.door_install import _replace_possibly_running_image

            _replace_possibly_running_image(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _prune_empty_parents(root: Path, path: Path) -> None:
    parent = path.parent
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _restore(root: Path, common: Path, touched: Sequence[str], head: Dict[str, Tuple[int, str]]) -> None:
    for rel in reversed(touched):
        path = root / rel
        entry = head.get(rel)
        try:
            if entry is None:
                path.unlink(missing_ok=True)
                _prune_empty_parents(root, path)
            else:
                mode, sha = entry
                _atomic_write(path, _read_head_blob(common, sha), mode)
        except OSError as exc:
            print(f"diff_commit: restore failed for {rel}: {exc}", file=sys.stderr)


def land_diff(
    dest_repo_root: Path,
    writes: Sequence[DestWrite],
    deletions: Sequence[str],
    message: str,
    *,
    commit: bool,
    derived: frozenset = frozenset(),
) -> LandOutcome:
    """Write `writes`, remove `deletions`, and (if `commit`) commit exactly those paths.

    Raises `DestDirtyError` before any write when a surviving path's worktree bytes differ
    from HEAD -- except a path in `derived`, which only the publish writes: its worktree
    drift is a prior round's uncommitted output, never a hand edit. A lost CAS race or any failure after the first write restores the worktree
    and re-raises. Returns `commit_sha=None` when nothing differs from HEAD or `commit` is False.
    """
    root = Path(dest_repo_root)
    common = resolve_git_common_dir(root)
    by_rel = {w.rel.replace("\\", "/"): w for w in writes}
    dels = sorted({d.replace("\\", "/") for d in deletions} - set(by_rel))
    head = head_blobs(root, list(by_rel) + dels)

    todo: Dict[str, DestWrite] = {}
    unchanged = []
    for rel, w in by_rel.items():
        if head.get(rel) == (w.mode, _blob_sha(w.data)):
            unchanged.append(rel)
        else:
            todo[rel] = w
    dels = [d for d in dels if d in head]
    if not todo and not dels:
        return LandOutcome(None, (), (), tuple(sorted(unchanged)))

    for rel in list(todo) + dels:
        entry = head.get(rel)
        have = _worktree_shas(root / rel)
        if not have and entry is None:
            continue
        if not have or entry is None or entry[1] not in have:
            if rel in todo and (_blob_sha(todo[rel].data) in have or rel in derived):
                continue
            raise DestDirtyError(f"{rel}: destination worktree differs from HEAD; nothing written")

    touched: list = []
    try:
        for rel, w in todo.items():
            touched.append(rel)
            _atomic_write(root / rel, w.data, w.mode)
        for rel in dels:
            touched.append(rel)
            (root / rel).unlink(missing_ok=True)
            _prune_empty_parents(root, root / rel)
        sha = None
        if commit:
            sha = _gcommit.commit_paths(
                root,
                list(todo),
                message,
                deleted_paths=dels,
                modes={rel: w.mode for rel, w in todo.items()},
            ).sha
    except BaseException:
        _restore(root, common, touched, head)
        raise
    return LandOutcome(sha, tuple(sorted(todo)), tuple(dels), tuple(sorted(unchanged)))
