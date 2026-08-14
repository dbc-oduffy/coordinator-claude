#!/usr/bin/env python3
"""Mirror sync engine, imported in-process by coordinator/bin/publish.py.

Replaces the per-file bash loops that used to live in setup/publish.sh's
sync_mirror() and sync_flat_mirror(). Motivation: Cygwin/MSYS fork() costs
~50-100ms on Windows, so the bash version was spending 60s+ on ~150-file
syncs and intermittently exhausting the cygwin1.dll heap (manifests as
`fork: retry: Resource temporarily unavailable`).

(Review: code-reviewer — docstring said "Bash still owns target dispatch,
hook discovery, audit-pattern enforcement, and CI smoke"; publish.sh (bash)
was retired in the percolate-python-port cutover and coordinator/bin/publish.py
now owns all of that, importing this module in-process, never subprocessed.)
coordinator/bin/publish.py owns target dispatch, hook discovery,
audit-pattern enforcement, and CI smoke. This script just does the
copy/delete work for one target directory and emits the same
`NEW:/UPDATE:/REMOVE:` lines the driver already parses.

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
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable


# ---------------------------------------------------------------------------
# .percolate-ignore — delegates to coordinator/lib/percolate/ignore.py so
# there is exactly one implementation of the (SECURITY-LOAD-BEARING) matcher
# semantics; two independent copies of a leak-gate WILL drift — this file
# used to carry its own parallel `IgnoreMatcher` class with NO root-anchored
# `/dir/` branch, a silent false-negative that would have let a root-anchored
# ignore pattern through unmatched (see
# state/bug-backlog/2026-07-21-templates-setup-publish-sync-py-still-ca-c753beadf718.yaml
# and docs/plans/2026-07-21-percolate-python-port.md § C-W4b).
#
# THIS FILE IS A DEPLOYED COPY, not a checkout-sibling of coordinator/. It is
# delivered by install-substrate.sh / dist/publish-repo-setup/install.sh into
# <install-root>/setup/publish_sync.py — unlike the repo-root
# setup/publish_sync.py (which sits directly next to coordinator/ in a
# doctrine-repo checkout and can reach ignore.py via a simple parent.parent
# relative path), this copy's install destination is NOT a sibling of
# coordinator/lib: the live plugin's coordinator/ tree lives one level
# further down, at <install-root>/plugins/coordinator/
# (see the doctrine repo's root `CLAUDE.md` § Architecture: "the live plugin root
# under ~/.claude/plugins/coordinator-claude/ is one level above a
# coordinator/ subdirectory"; not coordinator/CLAUDE.md, which was retired
# 2026-07-27). _locate_percolate_lib() below resolves that, mirroring the
# 2-rung CLAUDE_PLUGIN_ROOT / known-layout precedent already established by
# coordinator/bin/publish.py's _locate_cc_invoke().
# ---------------------------------------------------------------------------
def _locate_machine_local_cli() -> Path | None:
    """Return the `machine-local` registry-reader CLI, or None if unresolvable.

    Resolution ladder (first hit wins):
      1. `$COORDINATOR_SETTINGS_HOME/bin/machine-local` if the env var is set,
         else `~/.coordinator-claude-settings/bin/machine-local`.
      2. `shutil.which("machine-local")` (on PATH).
      3. `~/.claude/bin/machine-local` (transitional compat forwarder during
         the settings-home migration window).

    The CLI is a `python3`-shebanged executable — callers invoke it directly,
    never through bash/sh (see the caller below).
    """
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if not settings_home:
        settings_home = str(Path.home() / ".coordinator-claude-settings")
    candidate = Path(settings_home) / "bin" / "machine-local"
    if candidate.is_file():
        return candidate

    which_hit = shutil.which("machine-local")
    if which_hit:
        return Path(which_hit)

    transitional = Path.home() / ".claude" / "bin" / "machine-local"
    if transitional.is_file():
        return transitional

    return None


def _locate_percolate_lib() -> Path:
    """Return the `coordinator/lib` directory containing `percolate/ignore.py`.

    Rung 0: `$REPO_CLAUDE_KLABAUTER` env, then `$CLAUDE_KLABAUTER_ROOT` env (dir must
    exist) — the same canonical-override precedence every other resolver in
    this arc honors (`_engine_root.py`, `_claude_klabauter-root.js`,
    `setup/publish_sync.py` via its `_engine_root` import; DR-087). Without
    this rung an operator setting `REPO_CLAUDE_KLABAUTER` to override a
    stale/misconfigured machine-local registry entry gets no effect here,
    unlike everywhere else in the codebase that resolves an
    engine-repo-derived path.
    Rung 1: `$CLAUDE_PLUGIN_ROOT/lib/percolate/ignore.py` — harness-provided,
    most robust when this script runs under a Claude Code plugin context.
    Rung 2: `<install-root>/plugins/coordinator/lib/percolate/ignore.py`
    — the doctrine-fixed live-install layout (this file's own install
    destination's grandparent is `<install-root>`).
    Rung 3 (machine-local registry): resolve the engine repo checkout
    root via `machine-local get repos.claude_klabauter` (CLI located by
    `_locate_machine_local_cli()` above) and look for
    `<claude-klabauter-root>/coordinator/lib/percolate/ignore.py` there.
    `coordinator/lib/percolate/` was relocated to the engine repo by the
    2026-07-22 "migrate the executable surface" commit (b644d5a9), so
    rungs 1-2 can never resolve on a machine where this script runs from a
    deployed copy (e.g. `~/.claude/setup/publish_sync.py`) with no sibling
    doctrine-repo dev checkout in reach. This rung is the ratified
    registry→pointer-ladder replacement for a `Path(__file__)`-depth-walk —
    it works regardless of where this file's own copy happens to sit on
    disk. Any of {CLI not found, non-zero exit, empty stdout, resolved path
    missing the ignore.py file} is treated as a miss and falls through to
    rung 4.
    Rung 4 (dev-checkout convenience ONLY, file-relative, no env/registry):
    an engine repo sibling of the doctrine-repo checkout this copy of
    the file currently lives in. Deliberately narrow (pure `Path(__file__)`
    ancestor math) so it degrades safely on a real deployed copy:
    `<install-root>/setup/publish_sync.py` has no such sibling two
    directories up and correctly falls through to the ImportError below.

    Fails loud (ImportError) if no rung resolves: a silently-imported
    second matcher implementation is exactly the drift this delegation
    exists to prevent (detect-then-fail-loud on ambiguity, never
    detect-then-silently-pick — see
    coordinator/docs/wiki/implementation-standards-by-domain.md §
    Cross-cutting standards; formerly coordinator/CLAUDE.md § Implementation
    Standards, retired 2026-07-27).
    """
    for env in ("REPO_CLAUDE_KLABAUTER", "CLAUDE_KLABAUTER_ROOT"):
        env_claude_klabauter_root = os.environ.get(env)
        if env_claude_klabauter_root and Path(env_claude_klabauter_root).is_dir():
            candidate = Path(env_claude_klabauter_root) / "coordinator" / "lib" / "percolate" / "ignore.py"
            if candidate.is_file():
                return candidate.parent.parent

    env_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_plugin_root:
        candidate = Path(env_plugin_root) / "lib" / "percolate" / "ignore.py"
        if candidate.is_file():
            return candidate.parent.parent

    install_root = Path(__file__).resolve().parent.parent
    candidate = (
        install_root
        / "plugins"
        / "coordinator-claude"
        / "coordinator"
        / "lib"
        / "percolate"
        / "ignore.py"
    )
    if candidate.is_file():
        return candidate.parent.parent

    machine_local_cli = _locate_machine_local_cli()
    if machine_local_cli is not None:
        try:
            result = subprocess.run(
                [str(machine_local_cli), "get", "repos.claude_klabauter"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            claude_klabauter_root = result.stdout.strip()
            if claude_klabauter_root:
                registry_candidate = (
                    Path(claude_klabauter_root)
                    / "coordinator"
                    / "lib"
                    / "percolate"
                    / "ignore.py"
                )
                if registry_candidate.is_file():
                    return registry_candidate.parent.parent

    try:
        # This file's own checkout root, assuming the fixed dev-tree depth
        # <checkout-root>/coordinator/templates/setup/publish_sync.py. A
        # deployed copy lives shallower (<install-root>/setup/publish_sync.py)
        # so this index either lands outside the real checkout or raises
        # IndexError on a filesystem root — both are caught below.
        checkout_root = Path(__file__).resolve().parents[3]
        sibling_candidate = (
            checkout_root.parent
            / "claude-klabauter"
            / "coordinator"
            / "lib"
            / "percolate"
            / "ignore.py"
        )
        if sibling_candidate.is_file():
            return sibling_candidate.parent.parent
    except IndexError:
        pass

    raise ImportError(
        "publish_sync.py: could not locate coordinator/lib/percolate/ignore.py via "
        "$REPO_CLAUDE_KLABAUTER env, $CLAUDE_KLABAUTER_ROOT env, "
        "$CLAUDE_PLUGIN_ROOT/lib/percolate, "
        "<install-root>/plugins/coordinator/lib/percolate, "
        "the machine-local registry's repos.claude_klabauter, or a claude-klabauter "
        "sibling checkout's coordinator/lib/percolate. "
        "This module delegates to the SSOT ignore matcher on purpose (see the "
        "header comment above) rather than shipping a second implementation — "
        "fix the install layout, set CLAUDE_PLUGIN_ROOT, or set "
        "repos.claude_klabauter in the machine-local registry rather than adding "
        "a fallback matcher here."
    )


_COORDINATOR_LIB = _locate_percolate_lib()
if str(_COORDINATOR_LIB) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_LIB))

from percolate.ignore import (  # noqa: E402  (path setup must precede this import)
    PercolateIgnoreMatcher as IgnoreMatcher,
    load_percolate_ignore as _load_percolate_ignore_patterns,
)


def load_ignore(path: Path | None) -> IgnoreMatcher:
    if path is None:
        return IgnoreMatcher([])
    return IgnoreMatcher(_load_percolate_ignore_patterns(path))


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
# Empty-source mass-delete guard — see EmptySourceMassDeleteError docstring.
#
# BACKGROUND (2026-07-26): when a source directory exists on disk but has
# been emptied of real content (e.g. an allowlist entry hollowed by a
# migration, or a misrouted source_path), Phase 2 below (delete dst files
# not in src) reads "nothing in source" as "everything at the destination
# was intentionally removed" and deletes it. That is the WRONG inference for
# the common case (a misconfigured/stale source root) and correct only for
# the rare deliberate-full-prune case. This guard makes the common case fail
# loud instead of silently deleting; the rare case gets an explicit,
# intent-recording escape hatch (`COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE`)
# rather than a permanent wall — see its docstring below. Kept in parity
# with the repo-root `setup/publish_sync.py` copy this templates copy
# mirrors (see the module docstring's install-layout note above); the two
# `sync_mirror`/`sync_flat_mirror` bodies must not drift.
# ---------------------------------------------------------------------------
class EmptySourceMassDeleteError(RuntimeError):
    """Raised by `sync_mirror`/`sync_flat_mirror` when a directory (mirror:
    one per-plugin subdir; flat-mirror: the whole src_dir) resolves to ZERO
    real files on the SOURCE side while the DESTINATION counterpart has one
    or more — i.e. Phase 2's "delete dst files not in src" loop is about to
    treat "nothing to compare against" as "everything here was intentionally
    removed" and wipe real, previously-published content.

    This is a HARD ABORT, not a warning: the caller (`sync_mirror`/
    `sync_flat_mirror`) raises this BEFORE either phase touches the affected
    directory — no partial copy, no partial delete for that directory. A
    caller that catches this must NOT proceed to publish the affected
    directory; it must treat the whole run as failed.

    Escape hatch (deliberate-full-prune case): set
    `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE=1` to allow EVERY empty-source
    directory this run encounters to proceed as a real prune, or set it to a
    comma-separated list of directory names (e.g.
    `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE=bin,lib`) to confirm just those
    — this records the operator's explicit intent rather than silently
    reinterpreting "empty" as "confirmed empty on purpose". Under `--dry-run`
    this guard never aborts — it prints what a real run WOULD refuse, so a
    preview stays non-destructive by construction."""


def _empty_source_prune_override() -> "bool | frozenset[str]":
    """Parses `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE`. Returns `False` when
    unset/empty (no override), `True` for the literal `1` (blanket allow —
    every empty-source directory this run encounters may proceed), or a
    `frozenset` of directory names for a scoped allow (only those names may
    proceed; any other empty-source directory still aborts)."""
    raw = os.environ.get("COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE", "")
    if not raw:
        return False
    if raw == "1":
        return True
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _effective_file_count(
    root: Path,
    ignore: IgnoreMatcher,
    *,
    qualify: "Callable[[str], str] | None" = None,
    recursive: bool = True,
) -> int:
    """Counts real files under `root` the way Phase 1/Phase 2 below actually
    see them — after the `_archived_or_orphan` structural skip and the
    `.percolate-ignore` match (qualified via `qualify`, e.g. plugin-prefixed
    for mirror mode; identity for flat-mirror). `root` need not exist (0).
    `recursive=False` (flat-mirror) counts only direct-child files, matching
    that mode's top-level-only `src_dir.iterdir()` walk."""
    if not root.is_dir():
        return 0
    entries: Iterable[Path] = _walk_files(root) if recursive else (
        p for p in sorted(root.iterdir()) if p.is_file()
    )
    count = 0
    for entry in entries:
        rel_path = entry.name if not recursive else entry.relative_to(root).as_posix()
        if _archived_or_orphan(rel_path):
            continue
        qualified = qualify(rel_path) if qualify is not None else rel_path
        if ignore.matches(qualified):
            continue
        count += 1
    return count


def _guard_against_empty_source_mass_delete(
    name: str,
    src_root: Path,
    dst_root: Path,
    ignore: IgnoreMatcher,
    *,
    dry_run: bool,
    qualify: "Callable[[str], str] | None" = None,
    context_label: str = "directory",
    recursive: bool = True,
) -> None:
    """Preflight check, called BEFORE either phase touches `name` — see
    `EmptySourceMassDeleteError` for the full contract. No-op (returns
    normally) unless src has 0 effective files AND dst has >=1."""
    src_count = _effective_file_count(src_root, ignore, qualify=qualify, recursive=recursive)
    if src_count != 0:
        return
    dst_count = _effective_file_count(dst_root, ignore, qualify=qualify, recursive=recursive)
    if dst_count == 0:
        return

    override = _empty_source_prune_override()
    allowed = override is True or (isinstance(override, frozenset) and name in override)

    diagnostic = (
        f"{context_label} '{name}' resolves to an EMPTY source ({src_root}, 0 real "
        f"file(s)) while the destination ({dst_root}) has {dst_count} file(s) under "
        f"it. Publishing would delete all {dst_count} destination file(s) as "
        "unmatched-against-source.\n"
        "    Likely cause: the source path for this target/directory points at a "
        "tree the content has migrated OUT of, or an allowlist entry has narrowed "
        "to nothing — check the target's source_path / plugin-source config and "
        "any allowlist declared for it. This is very unlikely to be a deliberate "
        "deletion.\n"
        f"    If '{name}' IS a confirmed, deliberate full prune, re-run with "
        "COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE=1 (allow every empty-source "
        f"directory this run) or COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE={name} "
        "(allow just this one) to proceed."
    )

    if allowed:
        print(
            f"    WARNING: {diagnostic}\n    COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE "
            "confirms this is intentional — proceeding to delete.",
            file=sys.stderr,
        )
        return

    if dry_run:
        print(
            f"    WARNING (dry-run): ABORT — {diagnostic}\n    A real run WOULD ABORT "
            "here without the override; this preview does not delete anything.",
            file=sys.stderr,
        )
        return

    print(f"    ABORT: {diagnostic}", file=sys.stderr)
    raise EmptySourceMassDeleteError(diagnostic)


# ---------------------------------------------------------------------------
# Copy-time transform seam — `copy_file`, optional on both sync_mirror and
# sync_flat_mirror. Default (None) is a plain byte-for-byte shutil.copy2,
# i.e. today's behavior, unchanged — this is a MANDATORY backward-compat
# contract, not a convenience default: this module's own `main()` below and
# any other caller that does not pass copy_file must see identical behavior
# to before this parameter existed. Threading a caller-supplied transform
# through here (rather than duplicating a strip implementation in this file)
# is deliberate — see `<claude-klabauter-root>/coordinator/bin/publish.py`'s
# `strip_fleet_only_fences` / `_publish_copy_file` docstrings for why a
# security-sensitive copy-time transform is single-sourced there and injected
# down, not re-derived per copy engine.
# ---------------------------------------------------------------------------
CopyFileFn = Callable[[Path, Path, bool], None]


def _default_copy_file(src_file: Path, dst_file: Path, dry_run: bool) -> None:
    """The behavior every call site here had before `copy_file` existed:
    no-op under dry-run, plain `shutil.copy2` otherwise."""
    if not dry_run:
        shutil.copy2(src_file, dst_file)


# ---------------------------------------------------------------------------
# Mirror mode — per-plugin subdir sync
# ---------------------------------------------------------------------------
def sync_mirror(
    src_dir: Path,
    dst_dir: Path,
    ignore: IgnoreMatcher,
    dry_run: bool,
    *,
    copy_file: CopyFileFn | None = None,
    renamed_dir_names: frozenset[str] | None = None,
) -> tuple[int, int]:
    """`renamed_dir_names` (default `None`, treated as empty -- 100% behavior-preserving
    for every existing caller) is a forward-compatible hook for the engine-side
    directory-rename primitive (coordinator_core/percolate/rewrite_basename.py
    `rename_directories`, state/audits/2026-08-05-first-full-payload-identity-
    findings.md Group E), NOT YET WIRED to any real row as of this addition -- see that
    module's own docstring for why.

    The hazard this closes: a mirror-mode row whose content-transform sweep renames a
    top-level directory (e.g. `resolve-<source-name>/` -> `resolve-<published-name>/`) leaves
    THIS module's own orphan sweep below unable to tell "a directory the engine itself
    renamed last pass" apart from "a genuinely stray directory no longer wanted" --
    both look identical to it (present at `dst_dir`, absent from `src_dir`, since
    `src_dir` never changes name; only the DESTINATION copy is ever renamed). Left
    unexempted, the very next sync pass would delete the renamed directory outright as
    an orphan (or, worse, the 2026-07-26 top-level-presence preflight would FATAL-abort
    the entire publish over it) -- then recreate the untransformed, un-renamed source
    directory fresh, which the content-transform sweep would rename again next pass,
    oscillating forever and re-triggering the same abort on every subsequent publish.

    `renamed_dir_names` is every DESTINATION top-level basename the caller knows is an
    engine-produced rename target for THIS row (sourced from the engine's own rename
    ledger, coordinator_core/percolate/rewrite_basename.py `read_directory_rename_ledger`
    -- reading that ledger is the CALLER's job, not this module's: this module is a
    portable, repo-agnostic sync engine (see module docstring) and must not import a
    percolate-engine-specific module to stay that way). A name in this set is treated as
    present-by-construction for the orphan sweep, exactly as if `src_dir` had a
    same-named entry, so it is neither deleted as an orphan nor re-synced as new.
    """
    synced = 0
    removed = 0
    copier = copy_file or _default_copy_file
    renamed_dir_names = renamed_dir_names or frozenset()

    for src_plugin in sorted(p for p in src_dir.iterdir() if p.is_dir()):
        plugin_name = src_plugin.name
        dst_plugin = dst_dir / plugin_name
        print(f"  --- {plugin_name} ---")

        _guard_against_empty_source_mass_delete(
            plugin_name,
            src_plugin,
            dst_plugin,
            ignore,
            dry_run=dry_run,
            qualify=lambda rel, _plugin=plugin_name: f"{_plugin}/{rel}",
            context_label="mirror plugin",
        )

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
                copier(src_file, dst_file, True)
                print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                copier(src_file, dst_file, False)
                # Defense-in-depth: ensure shebanged files land executable at the percolation
                # target, regardless of source-repo index mode. See DR-151 and the
                # Windows-chmod lesson in state/lessons.md.
                # Review: the Staff Engineer — use `with` to avoid file-handle leak; Path accepted natively (no str() needed)
                try:
                    with open(dst_file, "rb") as fh:
                        is_shebang = fh.read(2) == b"#!"
                    if is_shebang:
                        st = os.stat(dst_file)
                        os.chmod(dst_file, st.st_mode | 0o111)
                except OSError:
                    pass
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
        orphans = [
            p for p in non_dot_dst
            if not (src_dir / p.name).is_dir() and p.name not in renamed_dir_names
        ]

        # Top-level presence preflight (2026-07-26): the mass-deletion guard below
        # only fires above a >50%-of-dst-top-level-dirs threshold, so a SINGLE
        # dropped top-level entry (e.g. `bin`, `lib` out of 8 top-level dirs = 25%)
        # sails under it and is deleted outright by the orphan sweep with no abort
        # at all — this is the exact mechanism that made a previously-investigated
        # multi-source (source_map) publish shape destructive (2/8 orphaned = 25%,
        # under the 50% guard). Statement of the invariant this closes: for a
        # mirror-mode target, the restricted source tree must contain a top-level
        # directory entry for every top-level directory the destination contains
        # that this target owns — a top-level dir present at dst and absent from
        # src is deleted by the sweep below regardless of .percolate-ignore, which
        # the sweep does not consult. This preflight fires on ANY orphan (not just
        # a large fraction), aborting before either guard below or the sweep touches
        # disk. Reuses COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 deliberately — a second,
        # differently-named escape hatch for the same underlying action (permit the
        # orphan sweep to proceed) would just be a second knob an operator has to
        # remember exists. Preserves the dry-run-never-aborts contract used
        # throughout this module (WARNING instead of FATAL, never a real delete).
        # Does NOT replace the 50%-threshold guard immediately below — belt and
        # braces on a destructive path is cheap, and that guard still independently
        # covers the wholly-misconfigured-src_dir case (which this preflight also
        # catches, redundantly, on the non-override path).
        # Spec: state/subagent-share/5bae563a-448a-4c5e-96ef-2de84498bd09/
        #       coordinatorstaff-eng-dfffb96b.md § 6 (The orphan-sweep invariant).
        if orphans:
            override = os.environ.get("COORDINATOR_OVERRIDE_ORPHAN_SWEEP") == "1"
            names = ", ".join(p.name for p in orphans)
            plural = len(orphans) != 1
            diagnostic = (
                f"top-level presence check: {len(orphans)} destination top-level "
                f"director{'ies are' if plural else 'y is'} absent from the "
                f"restricted source ({names}) and would be deleted outright by the "
                "orphan sweep below, regardless of .percolate-ignore (the sweep "
                "does not consult it).\n"
                "    Likely cause: a source_map root that failed to contribute this "
                "target, or an allowlist entry that dropped a top-level directory "
                "entirely — check the target's source_path / plugin-source config "
                "in setup/publish-targets.portable and any source_map wiring for "
                "this publish target.\n"
                f"    If this IS a confirmed, deliberate removal of "
                f"{'these top-level directories' if plural else 'this top-level directory'}, "
                "re-run with COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1."
            )
            if override:
                print(
                    f"    WARNING: {diagnostic}\n    COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 "
                    "confirms this is intentional — proceeding.",
                    file=sys.stderr,
                )
            elif dry_run:
                print(
                    f"    WARNING (dry-run): WOULD ABORT — {diagnostic}\n    A real "
                    "run WOULD ABORT here without the override; this preview does "
                    "not delete anything.",
                    file=sys.stderr,
                )
            else:
                print(f"FATAL: {diagnostic}", file=sys.stderr)
                raise SystemExit(3)

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
# Coordinator install-manifest layout transform
# ---------------------------------------------------------------------------
# WHY THIS EXISTS — the coordinator install-manifest layout transform
# ===================================================================
# The working-tree manifest at:
#   plugins/coordinator/docs/install/agent-install-manifest.json
# declares:
#   standalone_setup_script.posix    = "scripts/setup.py"
#   standalone_setup_script.windows  = "scripts/setup.ps1"
# These are correct relative paths in the NESTED coordinator/ layout, where the
# manifest lives at coordinator/docs/install/ and the script at coordinator/scripts/.
#
# When this manifest is flat-mirrored to the PUBLISH-REPO root layout (e.g.
# Code_Projects/coordinator-claude/docs/install/), the publish repo root IS the
# coordinator/ root — so the script lives at coordinator/scripts/setup.py from
# the manifest's vantage point (i.e. <publish-root>/coordinator/scripts/setup.py).
#
# The flat-mirror is verbatim by default; without this transform the published
# manifest still says "scripts/setup.py", which resolves to a non-existent path
# in the publish-repo layout and causes leaf-bootstrap step D to fail with a
# path-resolution error.
#
# FIX: apply a single, documented, explicit path substitution during the
# coordinator-claude-toplevel-install flat-mirror copy — rewriting the
# standalone_setup_script values from the nested-layout paths to the
# publish-root paths. The working-tree manifest (single source of truth) is
# NEVER modified; only the copy at the publish destination receives the rewrite.
#
# KEYING: the transform is applied iff BOTH conditions hold:
#   1. The file being copied is "agent-install-manifest.json" (the install manifest).
#   2. The src_dir ends with "coordinator/docs/install" (confirming this is the
#      coordinator nested-layout source, not an already-transformed publish root).
# This combination is unique to the coordinator-claude-toplevel-install flat-mirror
# target — no other flat-mirror target copies from that source path.
#
# Spec backlink: docs/plans/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md § C4
# See also: agent-install-contract.md § install-manifest layout transform
#
# DO NOT extend this transform to other files or targets without a named plan section.
# DO NOT apply this transform when operating in dry-run (dst file is not written).
# DO NOT modify the source manifest — read src, write only dst.

_INSTALL_MANIFEST_FILENAME = "agent-install-manifest.json"
# The src_dir suffix that identifies the coordinator nested-layout install dir.
# Normalised to POSIX for cross-platform matching.
# Review: code-reviewer (F4) — leading slash anchors `coordinator` to a path-segment
# boundary, preventing a hypothetical `.../notcoordinator/docs/install` false-match.
# Real source path `plugins/coordinator/docs/install` has a `/`
# before `coordinator`, so the match is unaffected.
_COORDINATOR_INSTALL_SRC_SUFFIX = "/coordinator/docs/install"

# Path rewrite pairs: (nested-layout value, publish-root value)
_COORDINATOR_MANIFEST_PATH_REWRITES: list[tuple[str, str]] = [
    ("scripts/setup.py", "coordinator/scripts/setup.py"),
    ("scripts/setup.ps1", "coordinator/scripts/setup.ps1"),
]


def _is_coordinator_install_src(src_dir: Path) -> bool:
    """Return True iff src_dir is the coordinator nested-layout docs/install/ directory.

    Checked by testing whether the POSIX representation of the path ends with
    'coordinator/docs/install'. Case-sensitive — install paths are always
    lowercase in the coordinator tree.
    """
    return src_dir.as_posix().endswith(_COORDINATOR_INSTALL_SRC_SUFFIX)


def _apply_coordinator_install_manifest_transform(dst_file: Path) -> None:
    """Rewrite standalone_setup_script paths in a just-copied install manifest.

    Reads the JSON at dst_file, rewrites only the standalone_setup_script values
    that need the nested→publish-root layout correction, then writes the result
    back in-place (UTF-8, trailing newline, same indentation as json.dumps
    indent=2 — consistent with the existing manifest style).

    Raises json.JSONDecodeError or OSError on failure (caller must not silently
    swallow — these indicate the manifest on disk is malformed or unwritable,
    which is a publish-correctness failure).

    Called ONLY when:
      - The filename is agent-install-manifest.json
      - The src_dir ended with coordinator/docs/install  (checked by caller)
      - dry_run is False (no dst_file exists in dry-run paths)
    """
    raw = dst_file.read_text(encoding="utf-8")
    data = json.loads(raw)

    sss = data.get("standalone_setup_script")
    if not isinstance(sss, dict):
        # Key absent — no transform needed (nothing to break, nothing to fix).
        return

    changed = False
    for nested_val, publish_val in _COORDINATOR_MANIFEST_PATH_REWRITES:
        for key in list(sss):
            if sss[key] == nested_val:
                sss[key] = publish_val
                changed = True

    if not changed:
        # All values already in publish-root form (e.g. re-publish after first run).
        return

    # Write back: 2-space indent, ensure trailing newline.
    out = json.dumps(data, indent=2, ensure_ascii=False)
    if not out.endswith("\n"):
        out += "\n"
    dst_file.write_text(out, encoding="utf-8")
    # Review: code-reviewer (F3) — this goes to stderr but the caller captures stderr
    # into the sync_log, so the TRANSFORM line is intentionally visible in publish
    # output alongside the NEW:/UPDATE: lines.
    print(
        f"    TRANSFORM: {_INSTALL_MANIFEST_FILENAME} "
        f"standalone_setup_script paths rewritten for publish-root layout "
        f"(scripts/ → coordinator/scripts/)",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Flat-mirror mode — top-level files only, no subdirs
# ---------------------------------------------------------------------------
def sync_flat_mirror(
    src_dir: Path,
    dst_dir: Path,
    ignore: IgnoreMatcher,
    dry_run: bool,
    *,
    copy_file: CopyFileFn | None = None,
) -> tuple[int, int]:
    synced = 0
    removed = 0
    copier = copy_file or _default_copy_file

    _guard_against_empty_source_mass_delete(
        dst_dir.name or str(dst_dir),
        src_dir,
        dst_dir,
        ignore,
        dry_run=dry_run,
        context_label="flat-mirror target",
        recursive=False,
    )

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
            copier(src_file, dst_file, True)
            print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            copier(src_file, dst_file, False)
            # Coordinator install-manifest layout transform — see the long comment
            # block above _apply_coordinator_install_manifest_transform for rationale.
            # Applied ONLY when copying agent-install-manifest.json from the
            # coordinator nested-layout docs/install/ source directory.
            if (
                rel_path == _INSTALL_MANIFEST_FILENAME
                and _is_coordinator_install_src(src_dir)
            ):
                _apply_coordinator_install_manifest_transform(dst_file)
            # Defense-in-depth: ensure shebanged files land executable at the percolation
            # target, regardless of source-repo index mode. See DR-151 and the
            # Windows-chmod lesson in state/lessons.md.
            # Review: the Staff Engineer — use `with` to avoid file-handle leak; Path accepted natively (no str() needed)
            try:
                with open(dst_file, "rb") as fh:
                    is_shebang = fh.read(2) == b"#!"
                if is_shebang:
                    st = os.stat(dst_file)
                    os.chmod(dst_file, st.st_mode | 0o111)
            except OSError:
                pass
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
