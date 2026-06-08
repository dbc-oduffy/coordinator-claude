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
import filecmp
import fnmatch
import os
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
    """Defense-in-depth filters that match bash logic verbatim.

    rel_path is sub-plugin-relative (the plugin_name prefix is NOT included) —
    do NOT apply the .percolate-ignore plugin-qualification here; these markers
    (`_archived/`, `.orphaned_at`) are structural and plugin-agnostic.
    """
    if rel_path == "_archived" or rel_path.startswith("_archived/") or "/_archived/" in rel_path:
        return True
    if rel_path.rsplit("/", 1)[-1] == ".orphaned_at":
        return True
    return False


# ---------------------------------------------------------------------------
# Copy / compare primitives
# ---------------------------------------------------------------------------
def _needs_copy(src: Path, dst: Path) -> bool:
    """Decide whether dst needs (re)copying from src.

    Copy iff: dst missing, OR size differs, OR src mtime > dst mtime, OR
    (size-equal AND mtime tie-or-older) AND bytes differ.

    The trailing byte-compare is the content-aware fallback for the
    same-size + not-newer minority — the silent-skip class the prior
    mtime-only gate missed when a dest `git reset --hard` refreshed dest
    mtimes and a same-byte-length content change (e.g. version bump
    `2.5.1` → `2.7.0`) would otherwise be skipped.

    Perf bound on this leg differs from the bash files_differ leg:
    filecmp.cmp is an in-process read+memcmp with NO per-file subprocess
    fork, so the 2026-05-20 Cygwin/MSYS heap-fragmentation incident (a
    fork-storm class) cannot return here regardless of how many files
    fall through. Cost in the pathological all-mtime-tie case (e.g. after
    a dest hard-reset) is RAM/IO bound — for the coordinator main mirror
    (~800 same-size files) that is ~800 in-process memcmps, tolerable.
    Contrast: bash files_differ DOES fork cmp per file and relies on a
    leg-size bound (~70 manifest entries) for its perf safety."""
    if not dst.is_file():
        return True
    try:
        s_src = src.stat()
        s_dst = dst.stat()
    except OSError as exc:
        # Fail-safe to copy; log so a permission error doesn't hide silently
        # behind a downstream shutil.copy2 error. The forced copy may also
        # fail at copy2 time — this log is for diagnostic continuity, not
        # an assertion that recovery will succeed.
        print(f"WARNING: stat failed on {src} or {dst}: {exc} — forcing copy attempt (may also fail)",
              file=sys.stderr)
        return True
    if s_src.st_size != s_dst.st_size:
        return True
    if s_src.st_mtime > s_dst.st_mtime:
        return True
    # Size-equal + mtime tie-or-older: bounded byte compare.
    # Zero-byte short-circuit: two empty files are always byte-equal.
    if s_src.st_size == 0:
        return False
    return not filecmp.cmp(str(src), str(dst), shallow=False)


def _walk_files(root: Path) -> Iterable[Path]:
    """Yield every regular file under root, depth-first. Skips symlinked dirs
    to match bash `find -type f` behaviour. Symlinked files ARE followed —
    their dereferenced content is what gets copied (via shutil.copy2 in the
    caller); symlinks are not preserved as symlinks in the destination."""
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
            # .percolate-ignore patterns are SOURCE_DIR-relative (plugin-qualified):
            # the file is authored as `coordinator/bin/tests/`, `data/`, etc. rel_path
            # here is sub-plugin-relative, so qualify with plugin_name before matching —
            # otherwise every plugin-prefixed pattern silently no-ops and leaks. (2026-05-30)
            if ignore.matches(f"{plugin_name}/{rel_path}"):
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
                # Plugin-qualify before matching — see the Phase-1 copy-loop
                # comment above. Keeps ignored files untouched on the destination
                # (neither copied nor deleted).
                if ignore.matches(f"{plugin_name}/{rel_path}"):
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
    # Distinct local name (orphan_name) so the outer loop's plugin_name is never
    # shadowed if this block is ever moved inside it.
    if dst_dir.is_dir():
        non_dot_dst = [p for p in sorted(dst_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
        orphans = [p for p in non_dot_dst if not (src_dir / p.name).is_dir()]

        # Mass-deletion guard: a misconfigured src_dir makes EVERY dst plugin look
        # orphaned, so an unguarded rmtree loop would wipe the whole destination.
        # Fail loud when orphans would remove >50% of dst plugin dirs (and there are
        # ≥2 of them). Override with COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 for the rare
        # legitimate mass-prune. Dry-run reports but never aborts.
        if orphans and len(non_dot_dst) >= 2 and len(orphans) > len(non_dot_dst) / 2:
            override = os.environ.get("COORDINATOR_OVERRIDE_ORPHAN_SWEEP") == "1"
            names = ", ".join(p.name for p in orphans)
            if not override and not dry_run:
                print(
                    f"FATAL: orphan sweep would remove {len(orphans)} of {len(non_dot_dst)} "
                    f"destination plugin dirs ({names}) — refusing as a likely src_dir "
                    f"misconfiguration. Set COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 to force.",
                    file=sys.stderr,
                )
                raise SystemExit(3)
            if not override and dry_run:
                # Preview only — report the would-be-fatal condition, never abort
                # (the dry-run contract is non-aborting; a real run would SystemExit(3)).
                print(
                    f"    WARNING: orphan sweep WOULD remove {len(orphans)}/{len(non_dot_dst)} "
                    f"plugin dirs ({names}) — a real run would FATAL here without "
                    f"COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1.",
                    file=sys.stderr,
                )
            if override:
                print(
                    f"    WARNING: orphan sweep removing {len(orphans)}/{len(non_dot_dst)} "
                    f"plugin dirs ({names}) — COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 set, proceeding.",
                    file=sys.stderr,
                )

        for dst_plugin in orphans:
            orphan_name = dst_plugin.name
            file_count = sum(1 for _ in _walk_files(dst_plugin))
            if dry_run:
                print(f"    REMOVE DIR: {orphan_name}/ ({file_count} file(s), not in source)")
            else:
                shutil.rmtree(dst_plugin)
                print(f"    REMOVE DIR: {orphan_name}/ ({file_count} file(s), not in source)")
            removed += file_count

    return synced, removed


# ---------------------------------------------------------------------------
# Flat-mirror mode — top-level files only, no subdirs
# ---------------------------------------------------------------------------
def sync_flat_mirror(src_dir: Path, dst_dir: Path, ignore: IgnoreMatcher, dry_run: bool) -> tuple[int, int]:
    synced = 0
    removed = 0

    # Phase 1: top-level files from src → dst
    for src_file in sorted(src_dir.iterdir()):
        if not src_file.is_file():
            continue
        rel_path = src_file.name
        if _archived_or_orphan(rel_path):
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

    # Phase 2: delete top-level files from dst that src no longer has
    if dst_dir.is_dir():
        for dst_file in sorted(dst_dir.iterdir()):
            if not dst_file.is_file():
                continue
            rel_path = dst_file.name
            if _archived_or_orphan(rel_path):
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
