#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
migrate-archive-week-changelogs.py — one-shot migration of archived
week-changelog daily files from the retired per-machine naming
(`YYYY-MM-DD-<machine>.md`, `YYYY-MM-DD-<machine>-backfill.md`) to the
machine-blind form (`YYYY-MM-DD.md`, `YYYY-MM-DD-backfill.md`) under
`archive/week-changelogs/<week-starting>/`.

Companion to the de-machine-changelog migration (Leg 4): the LIVE
`state/week-changelog/` directory is already machine-blind; this script
closes out the historical `archive/week-changelogs/` tree so both trees
share one naming convention.

Rename rule per file (applied only to files whose stem starts with a
`YYYY-MM-DD-` date prefix — bare `YYYY-MM-DD.md` and non-dated files
like `HEADER.priorities.*.md` are left untouched, they carry no machine
segment to strip):

  - `YYYY-MM-DD-pending-release.md` — already machine-blind, no rename.
  - `YYYY-MM-DD-backfill.md` — already machine-blind, no rename.
  - `YYYY-MM-DD-<machine>-backfill.md` (case-insensitive `backfill`
    suffix) → `YYYY-MM-DD-backfill.md`.
  - `YYYY-MM-DD-<machine>.md` → `YYYY-MM-DD.md`.

Two or more source files that would land on the same target name inside
one week directory (e.g. a machine's plain daily file and a *different*
machine's plain daily file for the same date) are a genuine ambiguity —
this script refuses those renames rather than silently picking one
(detect-then-fail-loud, not detect-then-silently-pick). They print as
CONFLICT and are left in place for manual reconciliation.

Modes:
  (default)  Dry-run. Prints every planned rename and every detected
             conflict. Modifies nothing.
  --apply    Performs the git-tracked renames (`git mv`) for every
             non-conflicting planned rename. Re-running after --apply
             is a no-op (idempotent): already-renamed files land on a
             blind suffix (`pending-release` or bare `backfill`) that
             `compute_target_name()` recognizes and skips, so nothing
             is replanned.

Usage:
  python3 migrate-archive-week-changelogs.py             # dry-run
  python3 migrate-archive-week-changelogs.py --apply      # perform renames
  python3 migrate-archive-week-changelogs.py --root PATH  # override repo root
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# archive/week-changelogs/ lives at repo root; this file resolves to
# <root>/coordinator/bin/migrate-archive-week-changelogs.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIRNAME = "week-changelogs"

_DATED_STEM_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")

# Already-machine-blind suffixes: no rename needed regardless of the
# machine-strip rule below.
_BLIND_SUFFIXES = frozenset({"pending-release", "backfill"})


def compute_target_name(source_name: str) -> str | None:
    """
    Return the machine-blind target filename for `source_name`, or None
    if the file is not a per-machine dated file (already bare, or a
    non-dated file such as HEADER.md / HEADER.priorities.*.md).
    """
    if not source_name.endswith(".md"):
        return None
    stem = source_name[: -len(".md")]
    match = _DATED_STEM_RE.match(stem)
    if not match:
        return None

    date_str, rest = match.group(1), match.group(2)

    # Already-machine-blind suffixes are a no-op. This guard is what makes the
    # script idempotent, and it is load-bearing: without the bare "backfill"
    # entry, a SECOND --apply run would see the output of the first
    # (`<date>-backfill.md`, whose stem no longer ends in `-backfill` because
    # the machine segment is gone) fall through to the machine-strip below and
    # collapse to `<date>.md` — silently colliding with the real daily file for
    # that date. Any new blind suffix must be added here, not just documented.
    if rest.lower() in _BLIND_SUFFIXES:
        return None

    if rest.lower().endswith("-backfill"):
        return f"{date_str}-backfill.md"

    return f"{date_str}.md"


def plan_week_dir(week_dir: Path) -> tuple[list[tuple[Path, Path]], list[tuple[str, list[Path]]]]:
    """
    Compute the rename plan for one week directory.

    Returns (renames, conflicts):
      - renames: list of (source_path, target_path) safe to apply.
      - conflicts: list of (target_name, [source_paths]) that collide —
        either two+ sources want the same target, or the target name
        is already occupied by a distinct on-disk file.
    """
    existing_names = {p.name for p in week_dir.iterdir() if p.is_file()}
    targets: dict[str, list[Path]] = {}

    for entry in sorted(week_dir.iterdir()):
        if not entry.is_file():
            continue
        target_name = compute_target_name(entry.name)
        if target_name is None:
            continue
        if target_name == entry.name:
            continue  # no-op; already at its target name
        targets.setdefault(target_name, []).append(entry)

    renames: list[tuple[Path, Path]] = []
    conflicts: list[tuple[str, list[Path]]] = []

    for target_name, sources in targets.items():
        target_occupied = target_name in existing_names
        if len(sources) > 1 or target_occupied:
            conflicts.append((target_name, sources))
            continue
        renames.append((sources[0], week_dir / target_name))

    return renames, conflicts


def discover_week_dirs(archive_root: Path) -> list[Path]:
    if not archive_root.is_dir():
        return []
    return sorted(p for p in archive_root.iterdir() if p.is_dir())


def git_mv(repo_root: Path, source: Path, target: Path) -> None:
    subprocess.run(
        ["git", "mv", "--", str(source.relative_to(repo_root)), str(target.relative_to(repo_root))],
        cwd=repo_root,
        check=True,
    )


def run(repo_root: Path, apply: bool) -> int:
    archive_root = repo_root / "archive" / ARCHIVE_DIRNAME
    week_dirs = discover_week_dirs(archive_root)
    if not week_dirs:
        print(f"No week directories found under {archive_root} — nothing to migrate.")
        return 0

    total_renames = 0
    total_conflicts = 0

    for week_dir in week_dirs:
        renames, conflicts = plan_week_dir(week_dir)
        if not renames and not conflicts:
            continue

        print(f"\n{week_dir.relative_to(repo_root)}:")
        for source, target in renames:
            verb = "RENAME (applied)" if apply else "RENAME (dry-run)"
            print(f"  {verb}: {source.name} -> {target.name}")
            if apply:
                git_mv(repo_root, source, target)
        for target_name, sources in conflicts:
            names = ", ".join(s.name for s in sources)
            print(f"  CONFLICT: [{names}] all map to {target_name} — left in place, resolve manually")

        total_renames += len(renames)
        total_conflicts += len(conflicts)

    print(
        f"\nSummary: {total_renames} rename(s) "
        f"{'applied' if apply else 'planned'}, {total_conflicts} conflict(s) requiring manual review."
    )
    if not apply and total_renames:
        print("Dry-run only — re-run with --apply to perform the renames.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-archive-week-changelogs.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the planned git mv renames. Default is dry-run (no mutation).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        metavar="PATH",
        help=f"Repo root to migrate under. Default: {_REPO_ROOT}",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run(repo_root=args.root.resolve(), apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
