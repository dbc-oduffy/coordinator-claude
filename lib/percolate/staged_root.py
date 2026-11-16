"""Assemble a destination's candidate tree beside the live root, then make it live in one step.

The unit of swap is a top-level entry of the root (a directory such as `coordinator_core/`, or a
root-level file); the root itself and `.git` are never renamed. `stage_tree` builds, for each unit
the diff touches, a full copy under a sibling container (unchanged files enter by hardlink, so
cost scales with the unit's file count, not its bytes) and writes nothing under the live root.
`swap_root` then renames each live unit out to a sibling graveyard and each staged unit in,
rolling every completed rename back on the first failure. A failed rename is never retried.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

EXEC = 0o100755
LINK = 0o120000
_MANIFEST = ".staged-root.json"
_STALE_AFTER_S = 3600.0


class StageError(RuntimeError):
    """The diff cannot be staged (a path escapes the root, names `.git`, or a unit is a symlink)."""


class SwapError(OSError):
    """A rename failed mid-swap. Every completed rename was rolled back; nothing was retried."""


def _norm(rel: str) -> str:
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or parts[0] == ".git" or rel.startswith(("/", "\\")) or os.path.isabs(rel):
        raise StageError(f"staged_root: refusing path {rel!r}")
    return "/".join(parts)


def _sibling(dest: Path, kind: str) -> Path:
    return dest.parent / f".{dest.name}.{kind}-{os.getpid()}"


def sweep_stale(dest: Path) -> None:
    """Remove `.{root}.(stage|old)-*` siblings older than an hour (a crashed or DLL-locked round's leftovers)."""
    cutoff = time.time() - _STALE_AFTER_S
    for kind in ("stage", "old"):
        for leftover in dest.parent.glob(f".{dest.name}.{kind}-*"):
            try:
                if leftover.stat().st_mtime < cutoff:
                    discard(leftover)
            except OSError:
                continue


def discard(path: Optional[Path]) -> None:
    """Remove a staging container or graveyard; a missing one or a locked leftover is not an error."""
    if path is not None and os.path.lexists(path):
        shutil.rmtree(path, ignore_errors=True)


def write_entry(path: Path, data: bytes, mode: int) -> None:
    """Write `data` at `path` as a fresh file (or symlink), never through an existing hardlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    if mode == LINK and os.name != "nt":
        os.symlink(data.decode("utf-8"), path)
        return
    path.write_bytes(data)
    if os.name != "nt":
        path.chmod(0o755 if mode == EXEC else 0o644)


def replace_file(tmp: Path, path: Path) -> None:
    """`os.replace`, with the running-image fallback when Windows refuses the overwrite."""
    try:
        os.replace(tmp, path)
    except PermissionError:
        if not path.exists():
            raise
        from coordinator_core.install.door_install import _replace_possibly_running_image

        _replace_possibly_running_image(tmp, path)


def _link_or_copy(src: str, dst: str) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _copy_link(src: str, dst: str, is_dir: bool) -> None:
    try:
        os.symlink(os.readlink(src), dst, target_is_directory=is_dir)
    except OSError:
        if is_dir:
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _mirror(src: str, dst: str, seen: Optional[list] = None) -> None:
    os.makedirs(dst, exist_ok=True)
    with os.scandir(src) as it:
        entries = list(it)
    for e in entries:
        target = os.path.join(dst, e.name)
        if e.is_symlink():
            if seen is not None:
                st = e.stat(follow_symlinks=False)
                seen.append((e.path, st.st_size, st.st_mtime_ns))
            _copy_link(e.path, target, e.is_dir())
        elif e.is_dir(follow_symlinks=False):
            if e.name != "__pycache__":
                _mirror(e.path, target, seen)
            else:
                _mirror(e.path, target)
        else:
            if seen is not None:
                st = e.stat(follow_symlinks=False)
                seen.append((e.path, st.st_size, st.st_mtime_ns))
            _link_or_copy(e.path, target)


def _fingerprint(root: str) -> list:
    """(path, size, mtime_ns) of every non-`__pycache__` file under `root`, sorted."""
    seen: list = []
    stack = [root]
    while stack:
        with os.scandir(stack.pop()) as it:
            for e in it:
                if e.is_symlink() or not e.is_dir(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    seen.append((e.path, st.st_size, st.st_mtime_ns))
                elif e.name != "__pycache__":
                    stack.append(e.path)
    return sorted(seen)


def _prune_empty_parents(stop: Path, path: Path) -> None:
    parent = path.parent
    while parent != stop and stop in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def stage_tree(dest_root: Path, writes: Sequence, deletions: Sequence[str], *, last: Optional[str] = None) -> Path:
    """Build the candidate tree for `writes` (objects with .rel/.data/.mode) and `deletions`.

    Returns a container beside `dest_root` holding one entry per touched top-level unit.
    Deletions apply before writes; the write whose rel equals `last` lands last in staging
    and its unit swaps last in `swap_root`. Nothing under `dest_root` is written."""
    dest = Path(dest_root)
    ordered = sorted(((_norm(w.rel), w) for w in writes), key=lambda p: p[0] == (last and _norm(last)))
    dels = sorted({_norm(d) for d in deletions})
    staged = _sibling(dest, "stage")
    sweep_stale(dest)
    discard(staged)
    staged.mkdir(parents=True)
    try:
        fingerprints = {}
        unit_dirs = sorted({r.split("/")[0] for r in [p[0] for p in ordered] + dels if "/" in r})
        for name in unit_dirs:
            live = dest / name
            if live.is_symlink():
                raise StageError(f"staged_root: top-level unit {name} is a symlink")
            if live.is_dir():
                seen: list = []
                _mirror(str(live), str(staged / name), seen)
                fingerprints[name] = sorted(seen)
            else:
                (staged / name).mkdir()
        removed = {d for d in dels if "/" not in d and os.path.lexists(dest / d)}
        for rel in (d for d in dels if "/" in d):
            (staged / rel).unlink(missing_ok=True)
            _prune_empty_parents(staged, staged / rel)
        for rel, w in ordered:
            write_entry(staged / rel, w.data, w.mode)
        for name in unit_dirs:
            unit = staged / name
            if not unit.is_dir() or not os.listdir(unit):
                if unit.is_dir():
                    unit.rmdir()
                if os.path.lexists(dest / name):
                    removed.add(name)
        present = sorted(p.name for p in staged.iterdir())
        last_unit = _norm(last).split("/")[0] if last else None
        (staged / _MANIFEST).write_text(
            json.dumps({"present": present, "removed": sorted(removed), "last": last_unit, "mirrored": fingerprints}),
            encoding="utf-8",
        )
    except BaseException:
        discard(staged)
        raise
    return staged


def _backup_file(live: Path, old: Path) -> None:
    if live.is_symlink():
        _copy_link(str(live), str(old), False)
    else:
        _link_or_copy(str(live), str(old))


def swap_root(staged: Path, dest_root: Path) -> Path:
    """Make a staged tree live; return the graveyard holding the replaced entries.

    Each unit is a rename (directories) or an atomic replace (files), so a root-level file
    never has an absent window. Any failure rolls back every completed step and raises
    `SwapError` naming the unit; the caller `discard`s the returned graveyard after lowering
    its landing marker."""
    dest, staged = Path(dest_root), Path(staged)
    manifest = json.loads((staged / _MANIFEST).read_text(encoding="utf-8"))
    removed = set(manifest["removed"])
    names = sorted(set(manifest["present"]) | removed)
    if manifest["last"] in names:
        names.remove(manifest["last"])
        names.append(manifest["last"])
    for name, before in manifest.get("mirrored", {}).items():
        live = dest / name
        if live.is_dir() and _fingerprint(str(live)) != [tuple(r) for r in before]:
            raise SwapError(f"unit {name!r} changed in the live root after it was staged; nothing swapped")
    grave = _sibling(dest, "old")
    discard(grave)
    grave.mkdir(parents=True)
    undo: List[Callable[[], None]] = []
    current = ""
    try:
        for name in names:
            current = name
            live, new, old = dest / name, staged / name, grave / name
            has_live = os.path.lexists(live)
            if name in removed:
                if has_live:
                    os.rename(live, old)
                    undo.append(lambda live=live, old=old: os.rename(old, live))
            elif new.is_dir() and not new.is_symlink():
                if has_live:
                    os.rename(live, old)
                    undo.append(lambda live=live, old=old: os.rename(old, live))
                os.rename(new, live)
                undo.append(lambda live=live, new=new: os.rename(live, new))
            else:
                if has_live:
                    _backup_file(live, old)
                    undo.append(lambda live=live, old=old: os.replace(old, live))
                replace_file(new, live)
                if not has_live:
                    undo.append(lambda live=live: os.unlink(live))
    except BaseException as exc:
        failed = []
        for step in reversed(undo):
            try:
                step()
            except OSError as undo_exc:
                failed.append(str(undo_exc))
        if failed:
            print(f"staged_root: rollback incomplete: {'; '.join(failed)}", file=sys.stderr)
        discard(grave)
        if isinstance(exc, OSError):
            raise SwapError(
                f"swap of {current!r} failed ({exc}); {len(undo)} completed step(s) rolled back, not retried"
            ) from exc
        raise
    return grave
