#!/usr/bin/env python3
"""Mirror sync engine for setup/publish.sh.

Replaces the per-file bash loops in sync_mirror() and sync_flat_mirror() with
a single Python process. Motivation: Cygwin/MSYS fork() costs ~50-100ms on
Windows, so the bash version was spending 60s+ on ~150-file syncs and
intermittently exhausting the cygwin1.dll heap (manifests as
`fork: retry: Resource temporarily unavailable`).

Bash still owns target dispatch, hook discovery, audit-pattern enforcement,
and CI smoke. This script just does the copy/delete work for one target
directory and emits the same `NEW:/UPDATE:/REMOVE:` lines bash's caller
already parses.

Usage:
  publish_sync.py mirror      SRC DST [--ignore=PATH] [--dry-run]
  publish_sync.py flat-mirror SRC DST [--ignore=PATH] [--dry-run]

Output (stdout):
  Per-file action lines, then trailing machine-readable summary:
    SUMMARY synced=<N> removed=<N>
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# .percolate-ignore — same semantics as bash is_ignored()
# ---------------------------------------------------------------------------
class IgnoreMatcher:
    """Matches the bash is_ignored() contract:

    - `dir/` (trailing slash) → directory pattern; match prefix OR any-depth
      occurrence (`dir/...` or `*/dir/...`)
    - `*<glob>` (starts with `*`) → basename glob via fnmatch
    - else → exact relative-path match
    """

    def __init__(self, patterns: list[str]) -> None:
        self.dir_patterns: list[str] = []
        self.glob_patterns: list[str] = []
        self.exact_patterns: list[str] = []
        for raw in patterns:
            p = raw.strip()
            if not p or p.startswith("#"):
                continue
            if p.endswith("/"):
                self.dir_patterns.append(p.rstrip("/"))
            elif p.startswith("*"):
                self.glob_patterns.append(p)
            else:
                self.exact_patterns.append(p)

    def matches(self, rel_path: str) -> bool:
        for d in self.dir_patterns:
            if rel_path.startswith(f"{d}/"):
                return True
            if f"/{d}/" in rel_path:
                return True
        if self.glob_patterns:
            base = rel_path.rsplit("/", 1)[-1]
            for g in self.glob_patterns:
                if fnmatch.fnmatchcase(base, g):
                    return True
        return rel_path in self.exact_patterns


def load_ignore(path: Path | None) -> IgnoreMatcher:
    if path is None or not path.is_file():
        return IgnoreMatcher([])
    return IgnoreMatcher(path.read_text(encoding="utf-8", errors="replace").splitlines())


# ---------------------------------------------------------------------------
# Skip rules common to both modes
# ---------------------------------------------------------------------------
def _archived_or_orphan(rel_path: str) -> bool:
    """Defense-in-depth filters that match bash logic verbatim."""
    if rel_path == "_archived" or rel_path.startswith("_archived/") or "/_archived/" in rel_path:
        return True
    if rel_path.rsplit("/", 1)[-1] == ".orphaned_at":
        return True
    return False


# ---------------------------------------------------------------------------
# Copy / compare primitives
# ---------------------------------------------------------------------------
def _needs_copy(src: Path, dst: Path) -> bool:
    """Match rsync default semantics: copy iff dst missing OR size differs OR
    src mtime > dst mtime. Single os.stat per side, no subprocess."""
    if not dst.is_file():
        return True
    try:
        s_src = src.stat()
        s_dst = dst.stat()
    except OSError:
        return True
    if s_src.st_size != s_dst.st_size:
        return True
    if s_src.st_mtime > s_dst.st_mtime:
        return True
    return False


def _walk_files(root: Path) -> Iterable[Path]:
    """Yield every regular file under root, depth-first. Skips symlinked dirs
    to match bash `find -type f` behaviour."""
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            yield entry


# ---------------------------------------------------------------------------
# Mirror mode — per-plugin subdir sync
# ---------------------------------------------------------------------------
def sync_mirror(src_dir: Path, dst_dir: Path, ignore: IgnoreMatcher, dry_run: bool) -> tuple[int, int]:
    synced = 0
    removed = 0

    for src_plugin in sorted(p for p in src_dir.iterdir() if p.is_dir()):
        plugin_name = src_plugin.name
        dst_plugin = dst_dir / plugin_name
        print(f"  --- {plugin_name} ---")

        per_plugin_synced = 0
        per_plugin_removed = 0

        if not dst_plugin.exists():
            if dry_run:
                print(f"    NEW DIR: {plugin_name}/ (would create)")
            else:
                dst_plugin.mkdir(parents=True)
                print(f"    NEW DIR: {plugin_name}/")

        # Phase 1: copy new/changed
        for src_file in _walk_files(src_plugin):
            rel_path = src_file.relative_to(src_plugin).as_posix()
            if _archived_or_orphan(rel_path):
                continue
            if ignore.matches(rel_path):
                continue
            dst_file = dst_plugin / rel_path
            if not _needs_copy(src_file, dst_file):
                continue
            is_new = not dst_file.exists()
            if dry_run:
                print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
            per_plugin_synced += 1

        # Phase 2: delete dst files not in src
        if dst_plugin.is_dir():
            for dst_file in _walk_files(dst_plugin):
                rel_path = dst_file.relative_to(dst_plugin).as_posix()
                if _archived_or_orphan(rel_path):
                    continue
                if ignore.matches(rel_path):
                    continue
                if (src_plugin / rel_path).is_file():
                    continue
                if dry_run:
                    print(f"    REMOVE: {rel_path} (not in source)")
                else:
                    dst_file.unlink()
                    print(f"    REMOVE: {rel_path} (not in source)")
                per_plugin_removed += 1

        if per_plugin_synced == 0 and per_plugin_removed == 0:
            print("    (up to date)")

        synced += per_plugin_synced
        removed += per_plugin_removed

    # Orphan plugin dirs (present in dst, absent in src) — preserve dotfiles.
    if dst_dir.is_dir():
        for dst_plugin in sorted(p for p in dst_dir.iterdir() if p.is_dir()):
            plugin_name = dst_plugin.name
            if plugin_name.startswith("."):
                continue
            if (src_dir / plugin_name).is_dir():
                continue
            file_count = sum(1 for _ in _walk_files(dst_plugin))
            if dry_run:
                print(f"    REMOVE DIR: {plugin_name}/ ({file_count} file(s), not in source)")
            else:
                shutil.rmtree(dst_plugin)
                print(f"    REMOVE DIR: {plugin_name}/ ({file_count} file(s), not in source)")
            removed += file_count

    return synced, removed


# ---------------------------------------------------------------------------
# Flat-mirror mode — top-level .md only, no subdirs
# ---------------------------------------------------------------------------
def sync_flat_mirror(src_dir: Path, dst_dir: Path, ignore: IgnoreMatcher, dry_run: bool) -> tuple[int, int]:
    synced = 0
    removed = 0

    # Phase 1: top-level .md from src → dst
    for src_file in sorted(src_dir.glob("*.md")):
        if not src_file.is_file():
            continue
        rel_path = src_file.name
        if rel_path == "_archived" or rel_path == ".orphaned_at":
            continue
        if ignore.matches(rel_path):
            continue
        dst_file = dst_dir / rel_path
        if not _needs_copy(src_file, dst_file):
            continue
        is_new = not dst_file.exists()
        if dry_run:
            print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
        synced += 1

    # Phase 2: delete top-level .md from dst that src no longer has
    if dst_dir.is_dir():
        for dst_file in sorted(dst_dir.glob("*.md")):
            if not dst_file.is_file():
                continue
            rel_path = dst_file.name
            if rel_path == "_archived" or rel_path == ".orphaned_at":
                continue
            if ignore.matches(rel_path):
                continue
            if (src_dir / rel_path).is_file():
                continue
            if dry_run:
                print(f"    REMOVE: {rel_path} (not in source)")
            else:
                dst_file.unlink()
                print(f"    REMOVE: {rel_path} (not in source)")
            removed += 1

    return synced, removed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("mirror", "flat-mirror"))
    p.add_argument("src", type=Path)
    p.add_argument("dst", type=Path)
    p.add_argument("--ignore", type=Path, default=None, help="Path to .percolate-ignore")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if not args.src.is_dir():
        print(f"ERROR: src not a directory: {args.src}", file=sys.stderr)
        return 1

    ignore = load_ignore(args.ignore)

    if args.mode == "mirror":
        synced, removed = sync_mirror(args.src, args.dst, ignore, args.dry_run)
    else:
        synced, removed = sync_flat_mirror(args.src, args.dst, ignore, args.dry_run)

    print(f"SUMMARY synced={synced} removed={removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
