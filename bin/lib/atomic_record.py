"""Shared helpers for atomic JSON record writes and repo-keyed filenames, used by
callers that hold a per-repo advisory record on disk (write-tmp-then-rename, tolerant
read, and owner-checked removal)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Iterator, Optional

def settings_home() -> Path:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    return Path.home() / ".coordinator-claude-settings"


def _safe_stem(text: str) -> str:
    return "".join(c for c in text if c.isalnum() or c in "-_")


def repo_key(repo_root: str) -> str:
    """Deterministic, collision-resistant filename stem for a repo root.

    A bare `_safe_stem` of the full path (statusline's pattern) risks collision once path
    separators are stripped -- two different repo roots can share the same trailing component.
    Appending a short hash of the case/separator-normalised path keeps the read path
    deterministic (no directory scan) while making that specific collision practically
    impossible.

    NOT NORMALISED, DELIBERATELY UNCLAIMED: two spellings of the SAME on-disk tree that are not
    merely a case/separator difference -- a mapped drive letter versus its UNC equivalent
    (`<drive>:\\repo` vs `\\\\<host>\\<share>\\repo`), or two different drive letters mapped to the
    same network share -- resolve to different keys here, because unifying them needs a
    filesystem-level identity check (volume GUID / resolving the mapping / `os.stat`
    device+inode) that this function does not perform. A nomination made under one spelling will
    not be found under the other. Only case and path-separator normalisation are covered;
    drive-letter/UNC identity is not.
    """
    normalised = os.path.normcase(os.path.normpath(repo_root))
    digest = hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:10]
    stem = _safe_stem(Path(repo_root).name) or "repo"
    return f"{stem}-{digest}"


def write_json_atomic(target: Path, record: dict) -> None:
    """Writes via a sibling temp file + `os.replace`, so a reader never observes a
    partially-written record; the temp file is removed on any failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def read_json_tolerant(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def remove_holder_record(
    path: Path, existing: dict, session_id: Optional[str]
) -> tuple[bool, int, Optional[str]]:
    """Removes `path` only if `session_id` matches the record's own holder (or no
    `session_id` is given). Returns `(removed, exit_code, detail)`; refuses removal
    on a holder mismatch rather than letting one session evict another's record."""
    holder = str(existing.get("session_id") or "")
    if session_id and holder != session_id:
        return False, 5, holder
    try:
        path.unlink()
    except OSError as exc:
        return False, 4, f"{exc.strerror or exc}, errno={exc.errno}"
    return True, 0, None


class LockTimeout(RuntimeError):
    pass


def _try_lock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def holder_lock(
    path: Path,
    *,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fd)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"could not acquire lock {lock_path} within {timeout}s")
                time.sleep(poll_interval)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def load_by_path(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
