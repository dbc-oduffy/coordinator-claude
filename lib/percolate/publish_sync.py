"""coordinator/lib/percolate/publish_sync.py — generic mirror sync engine.

Port (not a rewrite) of the percolate-engine-owning source repo's
`setup/publish_sync.py`, landed here as the engine-side half of the DR-079
seam described in docs/plans/2026-08-03-klabauter-rows-relocate-into-claude-klabauter.md
§ "AMENDED 2026-08-03 — the seam, not the copy (DR-079 `26450311a`)".
That amendment found ~78% of the 894-line source file is codename-free
generic sync engine, ~13% is a source-repo-specific coordinator-install-
manifest layout transform, and ~8% is an import bootstrap whose sole purpose
is to climb from that source checkout into
`coordinator/lib/percolate/ignore.py` — a module this repo already owns. This
file IS that climb's destination: `coordinator/bin/publish.py::
_import_publish_sync` now loads `setup/publish_sync.py` if a percolate root
provides one, else this module, and `check_publish_sync_contract` validates
whichever wins identically (interface, never provenance — no AC15
weakening).

Three cuts from the source original, nothing else:
  1. The `sys.path` bootstrap (source `:80-118`) collapses to the plain
     relative import below — this module already lives beside
     `ignore.py`, so there is no sibling checkout to resolve.
  2. The coordinator install-manifest layout transform
     (`_is_coordinator_install_src` /
     `_apply_coordinator_install_manifest_transform`, source `:666-786`,
     `:835-839`) is DROPPED along with its call site inside
     `sync_flat_mirror` — it is keyed to the source repo's own
     `coordinator-claude-toplevel-install` row and has no generic meaning.
     `sync_flat_mirror` itself stays, unabridged otherwise: three of the
     four klabauter rows are flat-mirror rows and need it.
  3. Nothing else — every other symbol below (`sync_mirror`,
     `sync_flat_mirror`, `load_ignore`, `_needs_copy`, `_walk_files`,
     `_archived_or_orphan`, the `EmptySourceMassDeleteError` guard family,
     `_default_copy_file`, `_restore_shebang_executable_bit`,
     `_sync_mirror_top_level_files`, `main`) is a byte-for-byte port of the
     source original's logic; sync semantics are unchanged.

Negative spec: this module holds ZERO source-repo-specific transform
content — no coordinator-install-manifest rewrite, no source-repo codename,
target name, or review pattern. The percolate-engine-owning repo keeps its
own `setup/publish_sync.py`, which continues to win over this module via
the per-root override in `_import_publish_sync` for as long as that repo's
checkout provides one.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

from .ignore import (
    PercolateIgnoreMatcher as IgnoreMatcher,
    load_percolate_ignore as _load_percolate_ignore_patterns,
)
from .publish_modes import argparse_mode_choices


def load_ignore(path: Path | None) -> IgnoreMatcher:
    if path is None:
        return IgnoreMatcher([])
    return IgnoreMatcher(_load_percolate_ignore_patterns(path))


# ---------------------------------------------------------------------------
# Skip rules common to both modes
# ---------------------------------------------------------------------------
# Structural build-artifact exclusion — the twin of `coordinator/bin/publish.py::
# _is_structurally_never_published`'s `__pycache__`/`.pyc`/`.pyo` handling
# (that function's own `_STRUCTURAL_NEVER_PUBLISHED_DIR_NAMES`/`_SUFFIXES`
# comment carries the full rationale: these are locally-generated Python
# bytecode artifacts, recreated by anything that RUNS Python in a
# destination clone, never present in a restricted source tree, and never
# something any row's sync copies — treating their mere presence at the
# destination as an orphan-sweep signal is a false positive by construction.
# Deliberately NOT sharing one Python object with publish.py's copy: that
# function is keyed to a `(path, repo_root)` pair walking a FULL repo tree
# (including `.git/`, which this module never syncs to/from and which
# `_archived_or_orphan`'s dotfile-adjacent callers already keep out of scope
# — see `_sync_mirror_top_level_files`'s `not p.name.startswith(".")` and the
# orphan-sweep's own `non_dot_dst` filter), while this module's callers pass
# POSIX-relative rel_path strings (sub-plugin-relative or bare top-level
# names) with no `repo_root` in scope. Same `__pycache__`/`.pyc`/`.pyo`
# vocabulary, kept identical char-for-char below; `.git` is intentionally
# absent here because it can never appear as sync input in this module.
_STRUCTURAL_BUILD_ARTIFACT_DIR_NAMES = ("__pycache__",)
_STRUCTURAL_BUILD_ARTIFACT_SUFFIXES = (".pyc", ".pyo")

# A console-subsystem child with no console of its own allocates a fresh
# conhost on Windows -- with a visible window. Every git spawn in this module
# is short-lived and output-captured, so without this each one flashes a
# window at whoever is running the publish. 0 on POSIX, where the flag does
# not exist, which is why this is unconditional rather than platform-branched.
#
# Belongs HERE, not in a consumer's per-root override: this is generic engine
# behaviour, and a downstream override carrying it (DoE-claude
# `setup/publish_sync.py`, whose own negative spec forbids engine behaviour in
# an override) had to keep it only because this module lacked it. That
# override drops it on its next re-derivation from this file.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _is_structural_build_artifact(rel_path: str) -> bool:
    """True iff `rel_path` (a POSIX-relative path, or a bare top-level
    directory/file name) is a locally-generated Python build artifact that
    must never count as orphaned, published, or deletable content — see the
    module-level comment above this function for the full rationale and its
    relationship to `coordinator/bin/publish.py::
    _is_structurally_never_published`. Matches ANY path segment equal to
    `__pycache__` (so a nested `sub/pkg/__pycache__/foo.pyc` is caught, not
    just a top-level one) or a bare `.pyc`/`.pyo` suffix on the final
    segment (the rare pre-`__pycache__`-layout stray bytecode file)."""
    parts = rel_path.split("/")
    if any(part in _STRUCTURAL_BUILD_ARTIFACT_DIR_NAMES for part in parts):
        return True
    return parts[-1].endswith(_STRUCTURAL_BUILD_ARTIFACT_SUFFIXES)


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
    if _is_structural_build_artifact(rel_path):
        return True
    return False


# ---------------------------------------------------------------------------
# Copy / compare primitives
# ---------------------------------------------------------------------------
def _needs_copy(src: Path, dst: Path) -> bool:
    """Decide whether dst needs (re)copying from src.

    Copy iff: dst missing, OR size differs, OR (size-equal AND) bytes
    differ. Content-only — deliberately NOT mtime-gated (§ removed
    "src mtime > dst mtime" branch, task brief "Deliverable 3 — honest
    change reporting"): source rows are materialized from a committed ref
    via `git archive` + extraction (`publish.py::_extract_git_archive`),
    so every source file's mtime is the extraction timestamp — always
    "now", always newer than any prior destination file regardless of
    whether the underlying bytes changed. An mtime-newer trigger therefore
    logged `UPDATE:`/performed a copy on EVERY materialized row, every
    run, even when the destination's tracked git diff was empty. Dropping
    it makes this the same byte-identical-is-unchanged contract
    `publish.py::files_differ` now holds, and is what makes `--delta`'s
    destination-drift detection sound: an untouched destination stays
    byte-identical across runs.

    Perf bound: filecmp.cmp is an in-process read+memcmp with NO per-file
    subprocess fork, so the 2026-05-20 Cygwin/MSYS heap-fragmentation
    incident (a fork-storm class) cannot return here regardless of how
    many files fall through. Cost in the all-same-size case is RAM/IO
    bound — for the coordinator main mirror (~800 same-size files) that
    is ~800 in-process memcmps, tolerable."""
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
    # Size-equal: bounded byte compare.
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
# BACKGROUND (2026-07-26): when an allowlist-declared (or otherwise resolved)
# source directory exists on disk but has been emptied of real content — e.g.
# `coordinator-claude|mirror`'s `bin`/`lib` allowlist entries, hollowed by the
# 2026-07-22 executable-surface migration (commit b644d5a9) — Phase 2 below
# (delete dst files not in src) reads "nothing in source" as "everything at
# the destination was intentionally removed" and deletes it. That is the
# WRONG inference for the common case (a misrouted/stale source_path config)
# and correct only for the rare deliberate-full-prune case. This guard makes
# the common case fail loud instead of silently deleting; the rare case gets
# an explicit, intent-recording escape hatch (`COORDINATOR_OVERRIDE_EMPTY_
# SOURCE_PRUNE`) rather than a permanent wall — see its docstring below.
#
# Companion regression doc: coordinator/tests/test_publish_allowlist_source_
# populated.py documents the SAME hazard from the authoring-time angle (an
# allowlist entry resolving to an empty dir on THIS repo's own root); this
# guard is the runtime backstop that fires regardless of how the empty
# source came about (allowlist narrowing, a misrouted source_path, a
# multi-source design gap, etc.) — it does not depend on that test running.
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
    directory; it must treat the whole run as failed (mirrors every other
    `EngineUnavailableError`-class fail-closed contract in this pipeline).

    Escape hatch (deliberate-full-prune case): set
    `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE=1` to allow EVERY empty-source
    directory this run encounters to proceed as a real prune, or set it to a
    comma-separated list of directory names (e.g.
    `COORDINATOR_OVERRIDE_EMPTY_SOURCE_PRUNE=bin,lib`) to confirm just those
    — this records the operator's explicit intent rather than silently
    reinterpreting "empty" as "confirmed empty on purpose". Under `--dry-run`
    this guard never aborts — it prints what a real run WOULD refuse, so a
    preview stays non-destructive by construction (matching every other gate
    in this pipeline's dry-run degrade, e.g. the orphan-plugin-dir sweep
    above)."""


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


def _orphan_sweep_override() -> "bool | frozenset[str]":
    """Parses `COORDINATOR_OVERRIDE_ORPHAN_SWEEP`. Returns `False` when
    unset/empty (no override — the top-level presence preflight and
    mass-deletion guard below run at full strength), `True` for the literal
    `1` (blanket override — every top-level orphan this run encounters is
    exempted from both guards, the original all-or-nothing form), or a
    `frozenset` of top-level directory names for a scoped override (only
    orphans with one of those names are exempted; any other orphan in the
    same round still goes through the preflight/guard exactly as before).

    An operator who reasoned about removing ONE directory used to have to
    arm `=1` against every other removal in the same round, including ones
    they never looked at — the scoped form lets them name exactly the
    directories they reasoned about. Same parse shape as
    `_empty_source_prune_override`, kept as its own function/env var rather
    than merged with it: the two knobs gate independently destructive
    actions (empty-source pruning vs. top-level orphan deletion) and must
    stay separately settable."""
    raw = os.environ.get("COORDINATOR_OVERRIDE_ORPHAN_SWEEP", "")
    if not raw:
        return False
    if raw == "1":
        return True
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _orphan_sweep_overridden(name: str, override: "bool | frozenset[str]") -> bool:
    """Whether top-level directory `name` is exempted from the orphan-sweep
    guards under the parsed `override` value (§ `_orphan_sweep_override`)."""
    if override is True:
        return True
    if override is False:
        return False
    return name in override


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
    that mode's top-level-only `src_dir.iterdir()` walk — never descending
    into subdirs the flat-mirror phases themselves never touch. This is the
    SAME filtering both copy phases apply, so a directory this function
    reports as "0 effective files" is genuinely nothing Phase 1 would ever
    copy from it and genuinely everything Phase 2 would delete from its
    destination counterpart — not an artifact of a looser count."""
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
        "to nothing — check the target's source_path / plugin-source config in "
        "setup/publish-targets.portable and any registry publish.mirrors.<key> "
        "override, and the target's allowlist (7th) field. This is very unlikely to "
        "be a deliberate deletion.\n"
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
# is deliberate — see `<this-repo-root>/coordinator/bin/publish.py`'s
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


def _restore_shebang_executable_bit(dst_file: Path) -> None:
    """Restore the executable bit on a copied file if it opens with `#!` —
    defense-in-depth against a source-repo index mode that dropped it.
    Shared by every copy leg in this module so a future leg (e.g. a new
    top-level-file allowlist entry) inherits this rather than needing its
    own hand-rolled copy."""
    try:
        with open(dst_file, "rb") as fh:
            is_shebang = fh.read(2) == b"#!"
        if is_shebang:
            st = os.stat(dst_file)
            os.chmod(dst_file, st.st_mode | 0o111)
    except OSError:
        pass


def _sync_mirror_top_level_files(
    src_dir: Path,
    dst_dir: Path,
    ignore: IgnoreMatcher,
    dry_run: bool,
    copier: CopyFileFn,
    *,
    changed_paths: "set[str] | None" = None,
) -> int:
    """Copy the regular files sitting directly under `src_dir`, returning how
    many were synced.

    `changed_paths` (optional): when supplied, every `rel_path` this pass
    actually copies (a real `_needs_copy` decision, not a re-parse of this
    function's own printed `NEW:`/`UPDATE:` lines) is added to it, `dst_dir`-
    relative — see `sync_mirror`'s own `changed_paths` docstring for the full
    contract this sink is one leg of.

    `sync_mirror`'s main loop iterates `src_dir`'s subdirectories, because in
    mirror mode each top-level entry is normally a tree (`bin`, `hooks`,
    `skills`). A restricted source tree built from an allowlist can also carry a
    BARE TOP-LEVEL FILE entry, which that loop never sees — the entry is
    enforced by the allowlist, reported in the publish banner, and then silently
    never copied, so admitting it reads as shipping while nothing ships.

    Ignore matching is unqualified here: `.percolate-ignore` patterns are
    SOURCE_DIR-relative, and a top-level file's source-relative path IS its
    basename — there is no plugin segment to prepend, unlike the sub-plugin
    `rel_path` the main loop qualifies.

    Top-level DOTFILES are skipped, matching the orphan sweep's existing
    `not p.name.startswith(".")` carve-out: a dotfile sitting at the root of a
    source tree is publish machinery (`.percolate-ignore` itself) rather than
    payload. An allowlisted dotted entry that IS payload — `.claude-plugin` —
    is a directory and travels through the main loop, untouched by this rule.

    Negative spec — this COPY leg never deletes anything. The destination-side
    sweep is `_sweep_mirror_top_level_orphans` below, deliberately a separate
    function and deliberately opt-in per row; see its own docstring for the
    condition under which sweeping a top-level file is safe at all.
    """
    synced = 0
    for src_file in sorted(p for p in src_dir.iterdir() if p.is_file()):
        rel_path = src_file.name
        if rel_path.startswith("."):
            continue
        if _archived_or_orphan(rel_path):
            continue
        if ignore.matches(rel_path):
            continue
        dst_file = dst_dir / rel_path
        if not _needs_copy(src_file, dst_file):
            continue
        is_new = not dst_file.exists()
        label = "NEW:   " if is_new else "UPDATE:"
        if dry_run:
            copier(src_file, dst_file, True)
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            copier(src_file, dst_file, False)
            _restore_shebang_executable_bit(dst_file)
        print(f"  {label} {rel_path}")
        if changed_paths is not None:
            changed_paths.add(rel_path)
        synced += 1
    return synced


def _sweep_mirror_top_level_orphans(
    src_dir: Path,
    dst_dir: Path,
    ignore: IgnoreMatcher,
    dry_run: bool,
    renamed_file_names: "frozenset[str]",
) -> int:
    """Delete the destination's top-level FILES that the source no longer has,
    returning how many were removed. Opt-in per row — see `sync_mirror`'s
    `sweep_top_level_orphans` parameter for who may turn it on and why.

    Why this is a separate, gated function rather than a second phase of
    `_sync_mirror_top_level_files`: whether a top-level file is target-owned
    depends on WHERE the row lands, and this module cannot see that. A row
    projecting into a destination SUBDIRECTORY it owns outright (`coordinator/
    bin`, `coordinator_core`) owns every file directly under it, so a file the
    source dropped is an orphan by construction. A row landing at a mirror
    repo's ROOT does not: `README.md`, `LICENSE`, and the repo's own dotfiles
    live exactly there, were never published by any row, and sweeping them
    would delete repo-owned content the publisher never created. That was the
    whole content of this leg's former blanket negative-spec, and it is right
    for the root case -- it was only ever wrong as a rule for every case.

    The incident that narrowed it (2026-08-26): `coordinator/bin/detect-staged-
    rollback.py`/`.cmd` were retired at source and correctly removed from the
    `claude-klabauter-coordinator-bin` row's allowlist, and went on shipping in
    the mirror anyway. Every published CLI in that row IS a top-level file, so
    the no-sweep rule made retirement unrepresentable for the entire row: a
    name could be added to the mirror but never taken off it. Audited before
    changing anything -- of 942 entries under that row's destination, exactly
    that one pair was a true orphan (the other nine apparent orphans are
    legitimate published basename substitutions), so this closes a real gap
    rather than licensing a mass delete.

    `renamed_file_names` is the exemption without which this sweep is actively
    destructive, not merely aggressive: the destination also holds every file the
    engine's own content-transform pass RENAMED, and those are absent from the
    source under their published names by construction (the source name never
    changes; only the destination copy is renamed). To this sweep they look
    identical to a dropped file. Measured the first time this sweep was previewed
    against a real row: 10 of 12 proposed deletions were engine-renamed published
    files, which the next transform pass would have re-created under the same
    names -- the file-granular form of exactly the oscillation `sync_mirror`'s
    `renamed_dir_names` exists to prevent for directories. A name in this set is
    treated as present-by-construction, the same contract `renamed_dir_names`
    carries. The caller sources it from the rename-generation ledger unioned with
    the store's static `basename_rename` section -- ledger alone is a cache that is
    empty on a fresh clone, which is precisely when a wrong delete is least
    recoverable.

    `_guard_against_empty_source_mass_delete` runs first, `recursive=False` to
    match this sweep's own non-recursive scope, so an allowlist that narrows to
    nothing aborts instead of emptying the destination -- the same preflight
    `sync_flat_mirror` (which has always swept its top-level files) already
    runs for the same reason. Dotfiles are skipped on the destination side
    exactly as the copy leg skips them on the source side: a dotfile at a
    destination root is publish machinery or repo-owned, never this row's
    payload, so it is neither copied nor deleted.
    """
    if not dst_dir.is_dir():
        return 0

    _guard_against_empty_source_mass_delete(
        dst_dir.name or str(dst_dir),
        src_dir,
        dst_dir,
        ignore,
        dry_run=dry_run,
        context_label="mirror top-level",
        recursive=False,
    )

    removed = 0
    for dst_file in sorted(p for p in dst_dir.iterdir() if p.is_file()):
        rel_path = dst_file.name
        if rel_path.startswith("."):
            continue
        if _archived_or_orphan(rel_path):
            continue
        if ignore.matches(rel_path):
            continue
        if rel_path in renamed_file_names:
            continue
        if (src_dir / rel_path).is_file():
            continue
        if not dry_run:
            dst_file.unlink()
        print(f"  REMOVE: {rel_path} (not in source)")
        removed += 1
    return removed


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
    changed_paths: "set[str] | None" = None,
    sweep_top_level_orphans: bool = False,
    renamed_file_names: "frozenset[str] | None" = None,
) -> tuple[int, int]:
    """`sweep_top_level_orphans` (default `False` -- 100% behavior-preserving
    for every existing caller): when True, destination top-level FILES absent
    from the source are deleted as orphans, via
    `_sweep_mirror_top_level_orphans` (see that function for the incident, the
    audit, and the empty-source preflight it runs first). Only a caller that
    knows this row projects into a destination SUBDIRECTORY the row owns
    outright may pass True -- a row landing at a mirror repo's ROOT must leave
    it False, because `README.md`/`LICENSE`/dotfiles live there and belong to
    the repo, not to any row. This module cannot determine that itself: it is a
    portable, repo-agnostic sync engine (see module docstring) and has no view
    of the target table, so the decision arrives as this parameter rather than
    being inferred from `dst_dir`'s shape.

    `changed_paths` (optional, default `None` -- 100% behavior-preserving for
    every existing caller): when supplied, every `dst_dir`-relative posix rel_path
    this pass actually copies (top-level files, via `_sync_mirror_top_level_files`,
    and per-plugin files below, prefixed `f"{plugin_name}/{rel_path}"`) is added to
    it as the copy happens -- a real `_needs_copy` decision recorded at its source,
    not a downstream re-parse of this function's own printed `NEW:`/`UPDATE:` lines
    (§ `coordinator/bin/publish.py::_parse_sync_changed_paths`, the scrape this
    param exists to make obsolete: a stdout-format change there silently degrades
    that parse to an EMPTY set rather than failing loud, which a caller reads as
    "nothing changed" and skips a downstream sweep it should have run — this sink
    cannot degrade that way because it is never derived from the printed text).

    Deliberately mutate-a-caller-supplied-set, not a return value: `sync_mirror`'s
    `(synced, removed)` return shape is a load-bearing existing contract (`main`'s
    CLI, every prior caller) this addition must not disturb. `None` (the default)
    is a true no-op -- nothing is tracked, matching every pre-existing call site
    exactly. An empty set the caller passed in and gets back unmodified after a
    genuine no-changes sync IS the correct tri-state answer ("determined, and
    nothing changed") -- this function does not itself decide UNDETERMINABLE for
    any call that reaches this parameter; that verdict belongs to whichever layer
    decides whether to call `sync_mirror` at all (see `PhaseResult.changed_files`'s
    own docstring, `coordinator_core/percolate/engine.py`, for the `None`-vs-empty
    contract one layer up).

    `renamed_dir_names` (default `None`, treated as empty -- 100% behavior-preserving
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

    synced += _sync_mirror_top_level_files(
        src_dir, dst_dir, ignore, dry_run, copier, changed_paths=changed_paths
    )
    if sweep_top_level_orphans:
        removed += _sweep_mirror_top_level_orphans(
            src_dir, dst_dir, ignore, dry_run, renamed_file_names or frozenset()
        )

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
                _restore_shebang_executable_bit(dst_file)
                print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
            if changed_paths is not None:
                changed_paths.add(f"{plugin_name}/{rel_path}")
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
        non_dot_dst = [
            p for p in sorted(dst_dir.iterdir())
            if p.is_dir() and not p.name.startswith(".") and not _is_structural_build_artifact(p.name)
        ]
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
            override = _orphan_sweep_override()
            exempt = [p for p in orphans if _orphan_sweep_overridden(p.name, override)]
            at_risk = [p for p in orphans if not _orphan_sweep_overridden(p.name, override)]
            if exempt:
                exempt_names = ", ".join(p.name for p in exempt)
                print(
                    f"    WARNING: top-level presence check: {exempt_names!r} "
                    "absent from the restricted source and would be deleted "
                    "outright by the orphan sweep below — "
                    "COORDINATOR_OVERRIDE_ORPHAN_SWEEP confirms this is "
                    "intentional — proceeding.",
                    file=sys.stderr,
                )
            if at_risk:
                names = ", ".join(p.name for p in at_risk)
                plural = len(at_risk) != 1
                diagnostic = (
                    f"top-level presence check: {len(at_risk)} destination top-level "
                    f"director{'ies are' if plural else 'y is'} absent from the "
                    f"restricted source: {names!r} and would be deleted outright by the "
                    "orphan sweep below, regardless of .percolate-ignore (the sweep "
                    "does not consult it).\n"
                    "    Likely cause: a source_map root that failed to contribute this "
                    "target, or an allowlist entry that dropped a top-level directory "
                    "entirely — check the target's source_path / plugin-source config "
                    "in setup/publish-targets.portable and any source_map wiring for "
                    "this publish target.\n"
                    f"    If this IS a confirmed, deliberate removal of "
                    f"{'these top-level directories' if plural else 'this top-level directory'}, "
                    "re-run with COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 (whole run) or "
                    f"COORDINATOR_OVERRIDE_ORPHAN_SWEEP={names.replace(', ', ',')} "
                    "(only these name(s))."
                )
                if dry_run:
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
            # `at_risk`/`exempt` (§ the top-level presence preflight above) —
            # an exempted top-level name is pre-approved and must not be
            # blocked by this threshold; only the non-exempt orphans can
            # trigger a FATAL here.
            if at_risk:
                names = ", ".join(p.name for p in at_risk)
                if not dry_run:
                    print(
                        f"FATAL: orphan sweep would remove {len(orphans)} of {len(non_dot_dst)} "
                        f"destination plugin dirs ({names}) — refusing as a likely src_dir "
                        "misconfiguration. Set COORDINATOR_OVERRIDE_ORPHAN_SWEEP=1 (whole run) "
                        f"or COORDINATOR_OVERRIDE_ORPHAN_SWEEP={names.replace(', ', ',')} "
                        "(only these name(s)) to force.",
                        file=sys.stderr,
                    )
                    raise SystemExit(3)
                # Preview only — report the would-be-fatal condition, never abort
                # (the dry-run contract is non-aborting; a real run would SystemExit(3)).
                print(
                    f"    WARNING: orphan sweep WOULD remove {len(orphans)}/{len(non_dot_dst)} "
                    f"plugin dirs ({names}) — a real run would FATAL here without an "
                    "override.",
                    file=sys.stderr,
                )
            if exempt:
                names = ", ".join(p.name for p in exempt)
                print(
                    f"    WARNING: orphan sweep removing {len(orphans)}/{len(non_dot_dst)} "
                    f"plugin dirs ({names}) — COORDINATOR_OVERRIDE_ORPHAN_SWEEP set, "
                    "proceeding.",
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
def sync_flat_mirror(
    src_dir: Path,
    dst_dir: Path,
    ignore: IgnoreMatcher,
    dry_run: bool,
    *,
    copy_file: CopyFileFn | None = None,
    changed_paths: "set[str] | None" = None,
) -> tuple[int, int]:
    """`changed_paths` — see `sync_mirror`'s own parameter docstring for the
    full contract (structured copy-decision sink, `None`-default no-op,
    mutate-in-place, tri-state ownership boundary); identical here, without
    a plugin prefix since flat-mirror has no per-plugin subdir."""
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
            _restore_shebang_executable_bit(dst_file)
            print(f"    {'NEW:   ' if is_new else 'UPDATE:'} {rel_path}")
        if changed_paths is not None:
            changed_paths.add(rel_path)
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
# `repo-cut` one-shot bootstrap (docs/plans/2026-08-10-repo-cut-the-fourth-
# mode-and-the-table.md, chunk C7b). NOT part of the source-repo port this
# module otherwise is (see module docstring's "Three cuts... nothing else") —
# a genuinely new addition, authored here because `check_publish_sync_
# contract` (`publish.py`) validates every mode's `entry_point` as an
# attribute of WHICHEVER module wins the `_import_publish_sync` seam, exactly
# like `sync_mirror`/`sync_flat_mirror` (AC7); a bootstrap function living
# only in `publish.py` would never be reachable through that seam.
# ---------------------------------------------------------------------------
class RepoCutBootstrapError(RuntimeError):
    """Raised by `sync_repo_cut` when a `git` step of the one-shot bootstrap
    (init / config / add / commit) exits non-zero. Fatal by design — a
    failed bootstrap leaves no safe partial state to recover from other than
    aborting the whole publish run, matching every other unrecoverable `git`
    failure this driver already fails loud on."""


def _run_git(dest_dir: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(dest_dir), *args],
        capture_output=True,
        text=True,
        check=False,
        **_NO_CONSOLE,
    )
    if result.returncode != 0:
        # Bounded — an unbounded git stderr blob (a looping hook, a credential
        # helper prompt) would otherwise fold in full, uncapped, to this
        # exception's message, which propagates through publish.py into
        # whatever surface reports it. No existing truncation convention in
        # this module to match; this is a fresh, conservative cap, not a
        # widening of one already in place elsewhere.
        stderr = result.stderr.strip()
        if len(stderr) > 2000:
            stderr = stderr[:2000] + f"... [{len(result.stderr.strip()) - 2000} more chars truncated]"
        raise RepoCutBootstrapError(
            f"repo-cut bootstrap: 'git {' '.join(args)}' failed in {dest_dir} "
            f"(exit {result.returncode}): {stderr}"
        )


def _repo_cut_is_bootstrapped(dest_dir: Path) -> bool:
    """AC6's explicit positive check: `dest_dir` already carries a `.git`
    entry AND a resolvable HEAD commit. Deliberately not an exception-swallow
    around a repeated `git init` (`git init` on an existing repo is itself
    harmless, but silently re-running it would make "already cut" and
    "genuinely virgin" indistinguishable to a caller deciding whether to
    warn)."""
    if not (dest_dir / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "-C", str(dest_dir), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        **_NO_CONSOLE,
    )
    return result.returncode == 0


def sync_repo_cut(dest_dir: Path, dry_run: bool) -> bool:
    """One-shot `repo-cut` bootstrap: `git init` a virgin `dest_dir`, set
    `core.autocrlf true` (AC4 — this is what protects the payload's line
    endings, per `git-config`'s "same as setting `text=auto` on all files"),
    set `core.safecrlf false` EXPLICITLY (an inherited global
    `core.safecrlf=true` would otherwise make `git add` ERROR rather than
    warn on an irreversible conversion, turning the bootstrap commit into a
    hard failure on an otherwise-correct machine), then write and commit
    `.gitattributes` as the FIRST commit, before any payload is staged
    (AC4 — retained for `-text`/`binary` overrides, `working-tree-encoding`,
    and `filter=`/LFS, none of which `core.autocrlf` or a later
    `git add --renormalize` protects; NOT for line-ending protection, which
    is `core.autocrlf`'s job alone).

    Runs strictly AHEAD of `publish.py::_ensure_dest_ready` in the caller —
    that check refuses a destination with no `.git` ancestor at all, so a
    virgin `dest_dir` must already be a git repo by the time it runs.

    A `repo-cut` row's publish SOURCE must itself be inside a git work tree
    with a committed HEAD (AC11) — enforced upstream, before this function is
    ever reached, by the pre-existing `run_pre_sync_gates`/
    `_git_materialize_ref` gate in `publish.py`; not re-checked here.

    Operator precondition (undocumented until Review: code-reviewer P2,
    2026-08-10): the final `git commit` relies on an inherited global
    `user.name`/`user.email` — this function sets neither. On a machine
    with no global git identity configured, `_run_git` raises
    `RepoCutBootstrapError` loudly (fatal by design, not silent) rather
    than committing under a fabricated identity. This is exactly the
    cut-a-brand-new-repo path, where a minimal/fresh machine is likeliest
    to lack one. Documenting rather than setting a repo-local identity here
    is the deliberate choice: inventing an author identity on the
    operator's behalf is its own defect, distinct from failing loud on a
    genuinely missing precondition.

    Concurrency (Review: code-reviewer P2, 2026-08-10): `_repo_cut_is_
    bootstrapped`'s check and this function's `git init`/`add`/`commit`
    body are not atomic in isolation — a TOCTOU window exists between them.
    In practice this is a documented no-op, not a live hazard: every
    `process_target` call that can reach this function runs inside
    `publish.py::main()`'s per-destination advisory lock
    (`lock_repo_roots`/`_publish_held_lock`), acquired up front for every
    resolved destination root across the WHOLE row loop, strictly before
    any row's `process_target` (and therefore this function) runs. Two
    concurrent `publish.py` invocations targeting the same virgin
    `dest_dir` already fail loud at lock-acquisition time — "another
    publish is running against it" — before either reaches this check. A
    caller that invokes this function directly, bypassing `publish.py::
    main()`'s lock, reopens the window; no lock is taken inside this
    function itself.

    AC6 (one-shot, not a durable row): a second call against an already-cut
    `dest_dir` (`_repo_cut_is_bootstrapped` is True) takes the ordinary
    projection path — no re-init, no re-commit of `.gitattributes`, no
    identity disturbance — and returns `False`.

    `dry_run` reports without mutating: an already-cut destination still
    returns `False`; a virgin one returns `True` without creating `dest_dir`
    or invoking `git` at all, matching every other sync dispatcher's
    non-mutating preview contract.

    Returns `True` iff this call actually performed the bootstrap.
    """
    if _repo_cut_is_bootstrapped(dest_dir):
        return False
    if dry_run:
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)
    _run_git(dest_dir, "init", "-q")
    _run_git(dest_dir, "config", "core.autocrlf", "true")
    _run_git(dest_dir, "config", "core.safecrlf", "false")
    (dest_dir / ".gitattributes").write_text("* text=auto\n", encoding="utf-8", newline="\n")
    _run_git(dest_dir, "add", ".gitattributes")
    _run_git(dest_dir, "commit", "-m", "repo-cut: bootstrap .gitattributes")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=argparse_mode_choices())
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
