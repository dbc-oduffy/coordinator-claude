"""Resolves project-rag's multi-rag "planes" (per-repo sqlite/db files under a plane
root) and reads a named table from whichever plane file actually carries it, reporting
a `PlaneDeclineReason` rather than raising when the plane, file, or table is absent."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

_PLANE_FILE_GLOBS = ("*.sqlite3", "*.db")
_SQLITE_TIMEOUT_SECONDS = 5.0


class PlaneDeclineReason(str, Enum):
    """The five states a plane read can report short of a clean find.

    A missing root is the ordinary state of a fresh clone, not a defect.
    TABLE_FOUND_ELSEWHERE is not silently followed and not silently
    failed — it is the signal that tells a future reader which of the
    tree's two `md_symbols` memos was right, the moment a box with planes
    first runs this code.
    """

    ROOT_MISSING = "plane_root_missing"
    FILE_MISSING = "plane_file_missing"
    TABLE_ABSENT = "table_absent"
    TABLE_FOUND_ELSEWHERE = "table_found_elsewhere"
    TABLE_EMPTY = "table_present_empty"


@dataclass(frozen=True)
class PlaneDecline:

    reason: PlaneDeclineReason
    table: str
    detail: str
    file: Path | None = None
    row_count: int | None = None


@dataclass(frozen=True)
class PlaneTable:

    table: str
    file: Path
    row_count: int


def resolve_plane_root(repo_root: Path) -> Path | None:
    root = Path(repo_root) / "Saved" / "ProjectRag"
    return root if root.is_dir() else None


def _plane_files(plane_root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in _PLANE_FILE_GLOBS:
        files.update(plane_root.glob(pattern))
    return sorted(files)


def _ro_connect(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=_SQLITE_TIMEOUT_SECONDS)


def _probe_file(path: Path, table: str) -> int | None:
    conn = _ro_connect(path)
    try:
        cursor = conn.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            (table,),
        )
        if cursor.fetchone() is None:
            return None
        count_cursor = conn.execute(f'select count(*) from "{table}"')
        row = count_cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def locate_table(
    repo_root: Path,
    table: str,
    expected_file: str | None = None,
) -> PlaneTable | PlaneDecline:
    """Locate `table` among project-rag's on-disk planes under `repo_root`.

    Read-only on every branch: `mode=ro` URI connections, one connection per
    plane file, no per-row spawn. `expected_file` is documentation of what
    the memos say (e.g. `"structural_project.sqlite3"`), never a shortcut
    that skips the probe — the probe is what the read resolves against, and
    a mismatch is reported as TABLE_FOUND_ELSEWHERE rather than followed or
    swallowed.
    """
    plane_root = resolve_plane_root(repo_root)
    if plane_root is None:
        return PlaneDecline(
            reason=PlaneDeclineReason.ROOT_MISSING,
            table=table,
            detail=f"Saved/ProjectRag/ not found under {repo_root}",
        )

    plane_files = _plane_files(plane_root)
    if not plane_files:
        return PlaneDecline(
            reason=PlaneDeclineReason.FILE_MISSING,
            table=table,
            detail=f"no plane files (*.sqlite3, *.db) found under {plane_root}",
        )

    found: tuple[Path, int] | None = None
    for path in plane_files:
        row_count = _probe_file(path, table)
        if row_count is not None:
            found = (path, row_count)
            break

    if found is None:
        return PlaneDecline(
            reason=PlaneDeclineReason.TABLE_ABSENT,
            table=table,
            detail=f"'{table}' not present in any plane file under {plane_root}",
        )

    file_, row_count = found

    if expected_file is not None and file_.name != expected_file:
        return PlaneDecline(
            reason=PlaneDeclineReason.TABLE_FOUND_ELSEWHERE,
            table=table,
            file=file_,
            row_count=row_count,
            detail=(
                f"'{table}' found in {file_.name}, not the expected "
                f"{expected_file}"
            ),
        )

    if row_count == 0:
        return PlaneDecline(
            reason=PlaneDeclineReason.TABLE_EMPTY,
            table=table,
            file=file_,
            row_count=0,
            detail=f"'{table}' present in {file_.name} but has 0 rows",
        )

    return PlaneTable(table=table, file=file_, row_count=row_count)
