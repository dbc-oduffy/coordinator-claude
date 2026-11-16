"""Land exactly N writes and D deletions on a destination repo's HEAD.

Writes whose (blob sha, mode) already equal HEAD's are dropped, only the surviving paths are
dirty-checked and committed; staging mirrors every top-level unit a surviving path touches, so
cost scales with those units' file counts, not the diff alone. Content lands in the live root
only by one `staged_root.swap_root` (unchanged paths' disk modes converge just before staging);
a failure after it restores every touched path from its HEAD blob.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, ContextManager, Dict, Mapping, Optional, Sequence, Tuple

from . import staged_root as _staged
from coordinator_core import _engine_landing as _landing
from coordinator_core.git import commit as _gcommit
from coordinator_core.git.git_dir import resolve_git_common_dir
from coordinator_core.git.git_objects import read_object
from coordinator_core.git.git_state import head_blobs

_EXEC = _staged.EXEC
_STAMP = "coordinator_core/_engine_stamp"
_SWAP_BOUND_S = 30.0


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
    remoded: Tuple[str, ...] = ()


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


def converge_worktree_modes(root: Path, modes: Mapping[str, int]) -> Tuple[str, ...]:
    """Make each regular file's disk exec bits match its declared mode; return the rels changed.

    Only 0o100644 / 0o100755 entries are considered. Missing files are skipped. A chmod the
    filesystem ignores (NTFS) is read back and not reported. No-op on Windows, which has no
    disk exec bit. Zero subprocesses."""
    if os.name == "nt":
        return ()
    converged = []
    for rel, mode in modes.items():
        if mode not in (0o100644, _EXEC):
            continue
        path = Path(root) / rel
        want = mode == _EXEC
        try:
            st = os.stat(path)
            if bool(st.st_mode & 0o111) == want:
                continue
            perm = st.st_mode & 0o7777
            os.chmod(path, perm | 0o111 if want else perm & ~0o111)
            if bool(os.stat(path).st_mode & 0o111) == want:
                converged.append(rel)
        except OSError:
            continue
    return tuple(sorted(converged))


def _converge_unchanged(
    root: Path, by_rel: Dict[str, DestWrite], unchanged: Sequence[str], head: Dict[str, Tuple[int, str]]
) -> Tuple[str, ...]:
    """Converge the disk bit of unchanged paths whose bytes still equal HEAD's.

    Trap: a path with hand-edited bytes is dirty, not mode-drifted; it is left alone.
    The disk bit is stat'ed first so only a drifted path pays the read-and-hash."""
    if os.name == "nt":
        return ()
    clean = {}
    for rel in unchanged:
        mode = by_rel[rel].mode
        if mode not in (0o100644, _EXEC):
            continue
        try:
            drifted = bool(os.stat(root / rel).st_mode & 0o111) != (mode == _EXEC)
        except OSError:
            continue
        if drifted and head[rel][1] in _worktree_shas(root / rel):
            clean[rel] = mode
    return converge_worktree_modes(root, clean)


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


def _stage(path: Path, data: bytes, mode: int) -> Path:
    """Write `data` to a sibling temp file (or symlink) and return it; `_swap` publishes it.

    Restore-path only: `land_diff` stages whole units through `staged_root`."""
    tmp = path.with_name(f".{path.name}.dc-{os.getpid()}")
    try:
        _staged.write_entry(tmp, data, mode)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


_swap = _staged.replace_file


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    tmp = _stage(path, data, mode)
    try:
        _swap(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


_MACHINE_LOCAL_EXCLUDE = ".coordinator-local/"


def _exclude_machine_local(common: Path) -> None:
    """Keep the commit lock sidecar dir `<checkout>/.coordinator-local/` out of the dest's status.

    `commit_paths` creates it in the checkout, not in `.git`; a dest without its own ignore rule
    would show it untracked after every landing. Best effort: an unwritable `.git/info` only
    leaves the dir visible."""
    if common.name != ".git":
        return
    path = common / "info" / "exclude"
    try:
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        if _MACHINE_LOCAL_EXCLUDE in have.split():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        sep = "" if not have or have.endswith("\n") else "\n"
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{sep}{_MACHINE_LOCAL_EXCLUDE}\n")
    except OSError:
        return


def _is_engine_root(root: Path, rels) -> bool:
    return _STAMP in rels or (root / _STAMP).exists()


def _raise_marker(root: Path) -> bool:
    """Raise the landing marker and wait out the grace; False when the root cannot carry one."""
    if _landing.begin_swap(root, deadline_s=_landing.SWAP_GRACE_S + _SWAP_BOUND_S) is None:
        print(
            f"diff_commit: {root} has no .git directory; landing is unguarded against hook readers",
            file=sys.stderr,
        )
        return False
    time.sleep(_landing.SWAP_GRACE_S)
    return True


_prune_empty_parents = _staged._prune_empty_parents


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


@dataclass(frozen=True)
class StampOutcome:
    """`sha` is the stamp commit, or None with `reason` naming why none was written."""

    sha: Optional[str]
    reason: str


def land_stamp_only(dest_repo_root: Path, source_head: str, signature: str, message: str) -> StampOutcome:
    """Commit `message` with no tree change unless HEAD already carries `source_head` and `signature`.

    The commit names one HEAD-tracked file at HEAD's own blob, so the worktree is never read and
    a dirty destination file is never swept in. Returns `sha=None` when HEAD already carries
    `source_head`, HEAD is unborn, or the commit is refused."""
    from coordinator_core.git.git_state import head_sha, parse_publish_trailers, read_commit
    from coordinator_core.git.run import run_git

    root = Path(dest_repo_root)
    sha = head_sha(root)
    info = read_commit(root, sha) if sha else None
    if sha is None or info is None:
        return StampOutcome(None, "destination has no readable HEAD")
    held = parse_publish_trailers(info.message)
    if held.source_head == source_head and held.signature == signature:
        return StampOutcome(None, f"HEAD {sha[:12]} already carries Percolate-Source-Head {source_head[:12]}")
    ls = run_git(["ls-tree", "-r", "-z", "HEAD"], cwd=str(root))
    entries = []
    for row in (ls.stdout.split("\0") if ls.ok else ()):
        meta, _, rel = row.partition("\t")
        fields = meta.split()
        if rel and len(fields) == 3 and fields[0] in ("100644", "100755"):
            entries.append((rel, int(fields[0], 8), fields[2]))
    if not entries:
        return StampOutcome(None, "destination HEAD tracks no regular file to anchor the stamp commit")
    last: Optional[Exception] = None
    for rel, mode, blob in entries[:3]:
        try:
            out = _gcommit.commit_paths(
                root, [rel], message, allow_empty=True, supplied_blobs={rel: blob}, modes={rel: mode}
            )
            return StampOutcome(out.sha, "")
        except _gcommit.CommitRefused as exc:
            last = exc
    return StampOutcome(None, f"stamp commit refused: {last}")


def land_diff(
    dest_repo_root: Path,
    writes: Sequence[DestWrite],
    deletions: Sequence[str],
    message: str,
    *,
    commit: bool,
    derived: frozenset = frozenset(),
    hold: Optional[Callable[[], ContextManager]] = None,
) -> LandOutcome:
    """Write `writes`, remove `deletions`, and (if `commit`) commit exactly those paths.

    Raises `DestDirtyError` before any write when a surviving path's worktree bytes differ
    from HEAD -- except a path in `derived`, which only the publish writes: its worktree
    drift is a prior round's uncommitted output, never a hand edit. Unchanged paths' disk modes
    converge before staging, so the stamp unit's swap is the last thing that lands. `hold`, when given,
    is a context-manager factory entered after the tree is staged and exited right after the swap,
    before the commit, so a caller's quiesce spans the swap only. A lost CAS race or any failure after the first write restores the worktree
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
        return LandOutcome(None, (), (), tuple(sorted(unchanged)), _converge_unchanged(root, by_rel, unchanged, head))

    for rel in list(todo) + dels:
        entry = head.get(rel)
        have = _worktree_shas(root / rel)
        if not have and entry is None:
            continue
        if not have or entry is None or entry[1] not in have:
            if rel in todo and (_blob_sha(todo[rel].data) in have or rel in derived):
                continue
            raise DestDirtyError(f"{rel}: destination worktree differs from HEAD; nothing written")

    guarded = _is_engine_root(root, todo)
    ordered = [w for r, w in todo.items() if r != _STAMP] + ([todo[_STAMP]] if _STAMP in todo else [])
    staged: Optional[Path] = None
    graveyard: Optional[Path] = None
    touched: list = []
    sha = None
    # Mode-only writes to clean paths that already match HEAD's mode: a later failure needs no undo.
    remoded = _converge_unchanged(root, by_rel, unchanged, head)
    try:
        staged = _staged.stage_tree(root, ordered, dels, last=_STAMP if _STAMP in todo else None)
        with hold() if hold is not None else contextlib.nullcontext():
            raised = guarded and _raise_marker(root)
            try:
                graveyard = _staged.swap_root(staged, root)
            finally:
                if raised:
                    _landing.end_swap(root)
        touched = list(todo) + dels
        if commit:
            _exclude_machine_local(common)
            try:
                sha = _gcommit.commit_paths(
                    root,
                    list(todo),
                    message,
                    deleted_paths=dels,
                    modes={rel: w.mode for rel, w in todo.items()},
                    blob_fallback=partial(_gcommit.hash_worktree_blobs_via_spawn, cwd=root),
                ).sha
            except BaseException:
                restoring = False
                try:
                    restoring = guarded and _raise_marker(root)
                    _restore(root, common, touched, head)
                finally:
                    if restoring:
                        _landing.end_swap(root)
                raise
    finally:
        _staged.discard(staged)
        _staged.discard(graveyard)
    return LandOutcome(sha, tuple(sorted(todo)), tuple(dels), tuple(sorted(unchanged)), remoded)
