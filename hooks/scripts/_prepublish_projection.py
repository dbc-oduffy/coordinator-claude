"""Pre-publish projection: what the OSS mirror WILL contain, computed before publish runs.

WHY THIS EXISTS
    Two live incidents shipped documents citing files the publish never carried — caught
    only after the fact (once by a reviewer, once by a wipe-and-rebuild). Both incidents'
    prescribed fix was the same: project the published file set BEFORE publishing and
    validate citations against that projection, rather than trusting the mirror after the
    fact. This module is that projector. See `coordinator/tests/test_prepublish_projection_
    citations.py` for the pytest harness and the standalone CLI entrypoint (`__main__`
    below) for the manual pre-publish run.

THE HARD CONSTRAINT THIS MODULE HONORS
    Do NOT re-derive the engine's file-surface include/exclude semantics by hand —
    an engine-plane incident this same session fixed was exactly that shape (two
    hand-synced tables desyncing). Materialization (does a file END UP in the mirror at
    all) is NOT governed by `file_surface` (that governs the CONTENT-TRANSFORM sweep's
    scope — which already-copied files get codename-scrubbed, a different question). It is
    governed by two real, already-implemented, already-tested mechanisms this module calls
    directly rather than re-deriving:
      - the allowlist CSV grammar (`percolate.allowlist.parse_allowlist_csv` /
        `split_inclusion_exclusion`, the engine-plane sibling repo's `coordinator/lib/percolate/
        allowlist.py`) — PURE, no I/O, no tree mutation;
      - `.percolate-ignore` matching (`percolate.ignore.PercolateIgnoreMatcher`,
        the engine-plane sibling repo's `coordinator/lib/percolate/ignore.py`) — PURE, reads one file;
      - the REAL sync engine's own file-walk primitives (`setup/publish_sync.py`'s
        `_walk_files` / `_archived_or_orphan` / `load_ignore`) — this repo's own already-
        ratified sync driver, imported by path rather than re-implemented, so this
        projector's notion of "what sync would walk" can never independently drift from
        what `setup/publish.sh` actually runs.
    None of those three call sites write anything or mutate a tree — this module never
    calls `build_allowlisted_source` (which physically copies into a temp dir) or
    `rename_basenames`/`rename_directories` (which physically rename on disk); both are
    real, mutating engine functions this module deliberately does NOT call (see
    `_apply_basename_rename`'s docstring for the one place this module diverges from
    calling a real function, and why).

ROW MODEL
    `setup/publish-targets.portable` — the one ratified, portable, doctrine-plane-owned config of
    what publishes where (see that file's own header for the field grammar). Every row
    in the file today lands in `publish-mirror:coordinator_claude` (five active rows); this
    module does not special-case that, it just derives scope from the file, same as
    `coordinator/tests/test_percolating_surfaces_carry_no_gendered_pronouns.py` already
    does for a sibling gate — reusing that established scope-derivation convention rather
    than inventing a second one.

MODE SEMANTICS (mirrored, not re-derived, from `setup/publish_sync.py`'s real functions)
    - `mirror`: every allowlist entry that resolves to a DIRECTORY is walked recursively
      (`_walk_files`); every entry that resolves to a FILE materializes as itself. For both
      shapes, the destination-relative path IS the entry (plus, for a directory entry, the
      path beneath it) — this is what `sync_mirror`'s per-plugin-directory loop and its
      `_sync_mirror_top_level_files` leg jointly produce once you observe that
      `plugin_name + "/" + rel_path` reconstructs to `entry + "/" + <path within entry>`
      for every entry shape (shallow file, shallow dir, deep file, deep dir) -- worked out
      by hand against `sync_mirror`'s source, not asserted; see that function's own
      docstring for the two phases this collapses.
    - `flat-mirror`: TOP-LEVEL FILES ONLY (`sync_flat_mirror`'s `src_dir.iterdir()`, never
      recursive) — a directory entry never appears in this mode's real config, and this
      module raises loudly if one is ever declared, rather than silently mis-modeling it.

KNOWN SIMPLIFICATIONS (report, don't hide — § brief's "closest available seam" instruction)
    - Multi-source `.percolate-ignore` composition (the engine-plane sibling repo's `allowlist.py`'s
      `_compose_percolate_ignore`, the ownership-gated ignore-rule union across
      `source_map` roots) is NOT replicated — this module loads exactly the ROW's own
      source root's `.percolate-ignore` for every entry in that row, including
      `source_map`-routed entries (today: `bin`/`lib` routed to that engine-plane sibling repo). A
      composed ignore file could in principle diverge from the row-root file for those two
      entries specifically; this is the one seam where "the engine's own walk" was not
      reachable without also calling the mutating `build_allowlisted_source`.
    - `basename_rename` is applied as a PURE exact-basename dict lookup off the store's own
      declared `{src, dst}` pairs (composed via the real `store.resolve_target`), not via
      the real `rename_basenames` function — that function physically renames files on
      disk, which this read-only projector must never do. See `_apply_basename_rename`.
    - Anchor/heading citation targets are OUT OF SCOPE for v1, per the dispatch brief —
      a citation's file target is checked; a `#section` fragment on it is not.

Spec backlink: dispatch brief "Build the pre-publish projection check" (2026-08-05,
no plan id — ad hoc dispatch); seam identification per
the engine-plane sibling repo's `coordinator_core/percolate/{guards,store,surface}.py` and
`coordinator/bin/publish.py::_compute_effective_source_count` (read, not called — see
module docstring above for why file_surface is the wrong seam for materialization).
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_SCRIPTS_DIR = REPO_ROOT / "coordinator" / "hooks" / "scripts"
if str(_HOOKS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))

from _engine_root import (  # noqa: E402
    RESOLUTION_LIVE_WORKING_TREE,
    resolve_claude_klabauter_root,
    resolve_claude_klabauter_root_with_class,
)

PUBLISH_TARGETS_PATH = REPO_ROOT / "setup" / "publish-targets.portable"
STORE_PATH = REPO_ROOT / "setup" / "percolate-hooks" / "percolate-store.yaml"

_PUBLISH_MIRROR_DEST = "publish-mirror:coordinator_claude"
_SOURCE_SIGIL_COORDINATOR_CLAUDE = "plugin-source:coordinator-claude"
_SOURCE_SIGIL_CLAUDE_KLABAUTER = "plugin-source:claude-klabauter"


class ProjectionUnavailableError(RuntimeError):
    """Raised when a required sibling module (the engine-plane sibling repo's engine, this repo's own
    `setup/publish_sync.py`) cannot be resolved/imported. The caller (the pytest harness,
    the CLI) must skip/abort rather than silently project an empty or partial set — an
    empty projection that reports "clean" is worse than no gate at all (§ dispatch brief).
    """


@dataclass(frozen=True)
class PublishRow:
    name: str
    mode: str
    dest_sigil: str
    source_subpath: str  # coordinator/-relative; "" means coordinator/ itself
    dest_subdir: str  # dest-repo-relative; "" means repo root
    allowlist_csv: str  # "" means no allowlist declared (whole subtree publishes)
    source_map_csv: str  # "" means single-source


@dataclass(frozen=True)
class ProjectedFile:
    row: str
    dest_relpath: str  # forward-slash, dest-repo-relative, post-basename-rename
    source_path: Path


@dataclass(frozen=True)
class ProjectionIssue:
    """A structural problem in the projection itself (e.g. a declared allowlist entry
    absent from source) — distinct from a citation finding. Surfaced so a caller can tell
    "the projection is incomplete" apart from "the projection is complete and a citation in
    it is broken"."""

    row: str
    entry: str
    reason: str


@dataclass
class Projection:
    rows: "dict[str, frozenset[str]]" = field(default_factory=dict)
    files: "list[ProjectedFile]" = field(default_factory=list)
    issues: "list[ProjectionIssue]" = field(default_factory=list)

    def published_paths(self) -> "frozenset[str]":
        """Union of every row's projected dest-relpath set — the full mirror contents."""
        out: set[str] = set()
        for paths in self.rows.values():
            out |= paths
        return frozenset(out)


# ---------------------------------------------------------------------------
# Sibling-module resolution — real functions only, never re-derived
# ---------------------------------------------------------------------------


def _load_module_by_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProjectionUnavailableError(f"could not build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _resolve_claude_klabauter_root() -> Path:
    root = resolve_claude_klabauter_root()
    if not root:
        raise ProjectionUnavailableError(
            "engine-plane sibling checkout not resolvable (env / machine-local registry / "
            "sibling-directory marker all failed via _engine_root.resolve_claude_klabauter_root()) "
            "-- the file-surface engine and coordinator/lib/percolate live there; without "
            "it this projector has no real walk to call and must not fall back to a "
            "hand-rolled one."
        )
    return Path(root)


def _import_publish_sync():
    """Import THIS REPO's own real sync driver (`setup/publish_sync.py`) by path.

    Reused rather than re-implemented for `_walk_files` / `_archived_or_orphan` /
    `load_ignore` -- see module docstring. Importing it also resolves and sys.path-inserts
    the engine-plane sibling repo's `coordinator/lib` as a side effect (its own module-level import
    ladder), which `percolate.allowlist` below depends on.
    """
    path = REPO_ROOT / "setup" / "publish_sync.py"
    if not path.is_file():
        raise ProjectionUnavailableError(f"expected the real sync driver at {path}")
    return _load_module_by_path(path, "_prepublish_projection_publish_sync")


def _import_percolate_allowlist():
    """Import the engine-plane sibling repo's `coordinator/lib/percolate/allowlist.py` for its PURE
    CSV-parsing helpers (`parse_allowlist_csv`, `split_inclusion_exclusion`) -- never for
    `build_allowlisted_source` (mutates a temp tree; not called anywhere in this module)."""
    claude_klabauter_root = _resolve_claude_klabauter_root()
    lib_dir = claude_klabauter_root / "coordinator" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import percolate.allowlist as allowlist_module  # noqa: PLC0415

    return allowlist_module


def _import_percolate_store():
    """Import the engine-plane sibling repo's `coordinator_core.percolate.store` for `resolve_target` --
    the REAL base+target composition function, used here only to read the composed
    `basename_rename` table (§ `_apply_basename_rename`).

    Capability-checked, not root-trusting: `_resolve_claude_klabauter_root()` (via
    `_engine_root.resolve_claude_klabauter_root()`) may hand back the PUBLISHED-ENGINE
    MIRROR rung (`repos.claude_klabauter`) ahead of the live-tree rung once
    that key is registered on this machine -- and a published mirror is not
    guaranteed to carry `coordinator_core/percolate/` (it is publish-content,
    not engine-source; observed absent on the 2026-08-12-registered
    claude-klabauter mirror while `coordinator/lib/percolate/allowlist.py`,
    consumed separately by `_import_percolate_allowlist`, IS present there).
    So: resolve the root as usual, but if it lacks
    `coordinator_core/percolate/store.py`, fall through to the live-working-tree
    rung (`resolve_claude_klabauter_root_with_class`'s class-reporting resolver, or a
    direct `repos.claude_klabauter` registry read) before importing. Only raise
    `ProjectionUnavailableError` when NEITHER root carries the module -- this
    projector's percolate dependency is real and must not be silenced.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    candidates = [claude_klabauter_root]

    if not (claude_klabauter_root / "coordinator_core" / "percolate" / "store.py").is_file():
        live_root: "Path | None" = None
        try:
            live_root_str, resolution_class = resolve_claude_klabauter_root_with_class()
            if resolution_class == RESOLUTION_LIVE_WORKING_TREE and live_root_str:
                live_root = Path(live_root_str)
        except Exception:
            live_root = None

        if live_root is None:
            try:
                from _engine_root import (  # noqa: PLC0415
                    _registry_value,
                    _settings_home_registry_dir,
                )

                reg_dir = _settings_home_registry_dir()
                v = _registry_value(reg_dir, "repos.claude_klabauter")
                if v and Path(v).is_dir():
                    live_root = Path(v)
            except Exception:
                live_root = None

        if live_root is not None and live_root != claude_klabauter_root:
            candidates.append(live_root)

    for root in candidates:
        if (root / "coordinator_core" / "percolate" / "store.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            import coordinator_core.percolate.store as store_module  # noqa: PLC0415

            return store_module

    raise ProjectionUnavailableError(
        "coordinator_core.percolate.store not found under any resolved engine "
        f"root ({', '.join(str(c) for c in candidates)}) -- the published-engine "
        "mirror rung omits coordinator_core/percolate and no live working tree "
        "carries it either."
    )


# ---------------------------------------------------------------------------
# Row parsing — setup/publish-targets.portable, same convention as
# coordinator/tests/test_percolating_surfaces_carry_no_gendered_pronouns.py's
# _iter_publish_target_rows (config-row parsing, not engine include/exclude semantics).
# ---------------------------------------------------------------------------


def iter_publish_rows(dest_sigil: str = _PUBLISH_MIRROR_DEST) -> "Iterable[PublishRow]":
    if not PUBLISH_TARGETS_PATH.is_file():
        return
    for line in PUBLISH_TARGETS_PATH.read_text(encoding="utf-8").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("|")
        if len(fields) < 5:
            continue
        name, mode, dest, source = fields[0], fields[1], fields[2], fields[3]
        if dest != dest_sigil:
            continue
        if source == _SOURCE_SIGIL_COORDINATOR_CLAUDE:
            source_subpath = ""
        elif source.startswith(_SOURCE_SIGIL_COORDINATOR_CLAUDE + "/"):
            source_subpath = source[len(_SOURCE_SIGIL_COORDINATOR_CLAUDE) + 1 :]
        else:
            continue
        dest_subdir = fields[4].strip()
        allowlist_csv = fields[6].strip() if len(fields) >= 7 else ""
        source_map_csv = fields[7].strip() if len(fields) >= 8 else ""
        yield PublishRow(
            name=name,
            mode=mode,
            dest_sigil=dest,
            source_subpath=source_subpath,
            dest_subdir=dest_subdir,
            allowlist_csv=allowlist_csv,
            source_map_csv=source_map_csv,
        )


def _resolve_sigil_root(sigil: str, *, claude_klabauter_root: Path) -> "Path | None":
    """Resolve a `plugin-source:<key>[/subpath]` sigil to a real root on disk.

    Supports exactly the two sigil families this repo's own config uses today
    (`coordinator-claude`, resolved against THIS repo's `coordinator/`; the engine-plane sibling repo,
    resolved against the sibling checkout's `coordinator/`) -- an unrecognized sigil
    returns `None` rather than guessing, so a caller can surface it as a `ProjectionIssue`
    instead of silently resolving to the wrong tree."""
    if sigil == _SOURCE_SIGIL_COORDINATOR_CLAUDE:
        return REPO_ROOT / "coordinator"
    if sigil.startswith(_SOURCE_SIGIL_COORDINATOR_CLAUDE + "/"):
        return REPO_ROOT / "coordinator" / sigil[len(_SOURCE_SIGIL_COORDINATOR_CLAUDE) + 1 :]
    if sigil == _SOURCE_SIGIL_CLAUDE_KLABAUTER:
        return claude_klabauter_root
    if sigil.startswith(_SOURCE_SIGIL_CLAUDE_KLABAUTER + "/"):
        return claude_klabauter_root / sigil[len(_SOURCE_SIGIL_CLAUDE_KLABAUTER) + 1 :]
    return None


def _parse_source_map(csv: str, *, claude_klabauter_root: Path) -> "tuple[dict[str, Path], list[str]]":
    """Parse a row's 8th-field `source_map` (`<sigil>=<csv-of-entries>;<sigil>=<csv>`)
    into `{allowlist_entry: contributing_root}`. Returns `(map, unresolved_sigils)` --
    an unresolved sigil is reported by the caller as a `ProjectionIssue`, never silently
    dropped."""
    entry_roots: dict[str, Path] = {}
    unresolved: list[str] = []
    if not csv:
        return entry_roots, unresolved
    for clause in csv.split(";"):
        clause = clause.strip()
        if not clause or "=" not in clause:
            continue
        sigil, entries_csv = clause.split("=", 1)
        sigil = sigil.strip()
        root = _resolve_sigil_root(sigil, claude_klabauter_root=claude_klabauter_root)
        if root is None:
            unresolved.append(sigil)
            continue
        for entry in entries_csv.split(","):
            entry = entry.strip()
            if entry:
                entry_roots[entry] = root
    return entry_roots, unresolved


# ---------------------------------------------------------------------------
# basename_rename — pure data application (§ module docstring, Known Simplifications)
# ---------------------------------------------------------------------------


def _apply_basename_rename(dest_relpath: str, rename_map: "dict[str, str]") -> str:
    """Rewrite `dest_relpath`'s trailing basename per the store's exact `{src: dst}`
    basename_rename table, leaving the directory portion untouched.

    Deliberately NOT a call to the engine-plane sibling repo's real `rename_basenames` -- that function
    performs the rename by physically renaming files on a real target tree
    (`old_path.rename(new_path)`), which a read-only projector must never do. The
    substitution itself is a trivial, judgment-free exact-string dict lookup (no glob, no
    prefix/segment matching, no admission/exclusion decision) -- unlike `file_surface`'s
    include/exclude tables, there is no drift risk in reading this table as plain data,
    because there is no derived judgment to get out of sync: the store's `{src, dst}` pairs
    ARE the whole rule, verbatim, on both sides."""
    if "/" in dest_relpath:
        parent, basename = dest_relpath.rsplit("/", 1)
        new_basename = rename_map.get(basename, basename)
        return f"{parent}/{new_basename}"
    return rename_map.get(dest_relpath, dest_relpath)


def _load_basename_rename_map(store_module) -> "dict[str, str]":
    """Every `{src, dst}` pair declared under `base.basename_rename` (composed once,
    per-target composition is a no-op for this store's current content since no target
    overrides `basename_rename` -- but resolved via the REAL `resolve_target` against an
    arbitrary declared target anyway, rather than reading `base` directly, so a future
    target-level override is picked up automatically instead of silently ignored)."""
    store = store_module.load_store(STORE_PATH)
    targets = store.get("targets") or {}
    rename_map: dict[str, str] = {}
    if targets:
        any_target = sorted(targets)[0]
        composed = store_module.resolve_target(store, any_target)
        for pair in composed.get("basename_rename") or []:
            src, dst = pair.get("src"), pair.get("dst")
            if src and dst:
                rename_map[src] = dst
    else:
        for pair in (store.get("base") or {}).get("basename_rename") or []:
            src, dst = pair.get("src"), pair.get("dst")
            if src and dst:
                rename_map[src] = dst
    return rename_map


# ---------------------------------------------------------------------------
# Projection — the core "what will materialize" computation
# ---------------------------------------------------------------------------


def _project_mirror_row(
    row: PublishRow,
    *,
    real_src: Path,
    entry_roots: "dict[str, Path]",
    publish_sync_module,
    allowlist_module,
    issues: "list[ProjectionIssue]",
) -> "list[tuple[str, Path]]":
    """`mode == 'mirror'` projection -- see module docstring § MODE SEMANTICS."""
    entries, exclusion_targets = allowlist_module.split_inclusion_exclusion(
        allowlist_module.parse_allowlist_csv(row.allowlist_csv)
    )
    ignore = publish_sync_module.load_ignore(
        (real_src / ".percolate-ignore") if (real_src / ".percolate-ignore").is_file() else None
    )
    out: "list[tuple[str, Path]]" = []
    for entry in entries:
        root = entry_roots.get(entry, real_src)
        candidate = root / entry
        if candidate.is_dir():
            for f in publish_sync_module._walk_files(candidate):  # noqa: SLF001
                rel_within = f.relative_to(candidate).as_posix()
                if publish_sync_module._archived_or_orphan(rel_within):  # noqa: SLF001
                    continue
                qualify = f"{entry}/{rel_within}"
                if ignore.matches(qualify):
                    continue
                out.append((qualify, f))
        elif candidate.is_file():
            if not ignore.matches(entry):
                out.append((entry, candidate))
        else:
            issues.append(
                ProjectionIssue(
                    row=row.name,
                    entry=entry,
                    reason=f"allowlist entry absent from source (looked under {candidate})",
                )
            )

    if exclusion_targets:
        excluded_prefixes = tuple(t.rstrip("/") for t in exclusion_targets)
        out = [
            (rel, path)
            for rel, path in out
            if not any(rel == pfx or rel.startswith(pfx + "/") for pfx in excluded_prefixes)
        ]
    return out


def _project_flat_mirror_row(
    row: PublishRow,
    *,
    real_src: Path,
    publish_sync_module,
    allowlist_module,
    issues: "list[ProjectionIssue]",
) -> "list[tuple[str, Path]]":
    """`mode == 'flat-mirror'` projection -- top-level files only (§ MODE SEMANTICS)."""
    ignore = publish_sync_module.load_ignore(
        (real_src / ".percolate-ignore") if (real_src / ".percolate-ignore").is_file() else None
    )
    out: "list[tuple[str, Path]]" = []
    if row.allowlist_csv:
        entries, exclusion_targets = allowlist_module.split_inclusion_exclusion(
            allowlist_module.parse_allowlist_csv(row.allowlist_csv)
        )
        if exclusion_targets:
            issues.append(
                ProjectionIssue(
                    row=row.name,
                    entry="(exclusions)",
                    reason="flat-mirror row declares '!'-exclusions -- not modeled, no "
                    "current row uses this shape; treat this projection as unverified "
                    "for this row until this is implemented",
                )
            )
        for entry in entries:
            if "/" in entry:
                issues.append(
                    ProjectionIssue(
                        row=row.name,
                        entry=entry,
                        reason="flat-mirror row declares a deep/nested allowlist entry -- "
                        "flat-mirror only ever publishes top-level files in the real "
                        "sync engine; not modeled",
                    )
                )
                continue
            candidate = real_src / entry
            if not candidate.is_file():
                issues.append(
                    ProjectionIssue(
                        row=row.name, entry=entry, reason=f"allowlist entry absent from source ({candidate})"
                    )
                )
                continue
            if not ignore.matches(entry):
                out.append((entry, candidate))
    else:
        if not real_src.is_dir():
            issues.append(
                ProjectionIssue(row=row.name, entry="(source root)", reason=f"source root does not exist: {real_src}")
            )
            return out
        for candidate in sorted(real_src.iterdir()):
            if not candidate.is_file():
                continue
            rel = candidate.name
            if publish_sync_module._archived_or_orphan(rel):  # noqa: SLF001
                continue
            if ignore.matches(rel):
                continue
            out.append((rel, candidate))
    return out


def project_publish_paths() -> Projection:
    """Compute the full pre-publish projection: every row's projected dest-relpath set,
    the source path each maps from, and any structural issues (missing allowlist entry,
    unresolved sigil, unmodeled shape) encountered while computing it.

    Read-only, no publish, no percolate, no writes anywhere -- every path touched is
    opened for reading only (`.percolate-ignore` files, source trees) or not touched at
    all (the destination mirror is never read here; see `sanity_check_against_mirror`
    for the one place this module deliberately reads the mirror, read-only, for
    validation purposes only).
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    publish_sync_module = _import_publish_sync()
    allowlist_module = _import_percolate_allowlist()
    store_module = _import_percolate_store()
    rename_map = _load_basename_rename_map(store_module)

    projection = Projection()
    for row in iter_publish_rows():
        real_src = REPO_ROOT / "coordinator" / row.source_subpath if row.source_subpath else REPO_ROOT / "coordinator"
        entry_roots, unresolved_sigils = _parse_source_map(row.source_map_csv, claude_klabauter_root=claude_klabauter_root)
        for sigil in unresolved_sigils:
            projection.issues.append(
                ProjectionIssue(row=row.name, entry="(source_map)", reason=f"unresolved source_map sigil: {sigil}")
            )

        if row.mode == "mirror":
            pairs = _project_mirror_row(
                row,
                real_src=real_src,
                entry_roots=entry_roots,
                publish_sync_module=publish_sync_module,
                allowlist_module=allowlist_module,
                issues=projection.issues,
            )
        elif row.mode == "flat-mirror":
            pairs = _project_flat_mirror_row(
                row,
                real_src=real_src,
                publish_sync_module=publish_sync_module,
                allowlist_module=allowlist_module,
                issues=projection.issues,
            )
        else:
            projection.issues.append(
                ProjectionIssue(row=row.name, entry="(mode)", reason=f"unmodeled publish mode: {row.mode!r}")
            )
            continue

        row_paths: set[str] = set()
        for rel, source_path in pairs:
            dest_relpath = f"{row.dest_subdir}/{rel}" if row.dest_subdir else rel
            dest_relpath = _apply_basename_rename(dest_relpath, rename_map)
            row_paths.add(dest_relpath)
            projection.files.append(ProjectedFile(row=row.name, dest_relpath=dest_relpath, source_path=source_path))
        projection.rows[row.name] = frozenset(row_paths)

    return projection


def sanity_check_against_mirror(projection: Projection, mirror_root: "str | Path") -> "list[str]":
    """Read-only sanity check: for every row, how many projected paths ALSO exist as a
    real file at `mirror_root / dest_relpath`. Returns human-readable summary lines (one
    per row plus a total) -- never asserts, never writes; the caller decides what to do
    with a low/zero overlap number. NEVER touches `mirror_root` for anything but
    `Path.is_file()` reads."""
    mirror_root = Path(mirror_root)
    lines: list[str] = []
    total_projected = 0
    total_present = 0
    for row_name in sorted(projection.rows):
        paths = projection.rows[row_name]
        present = sum(1 for p in paths if (mirror_root / p).is_file())
        lines.append(f"  {row_name}: projected={len(paths)} present_in_mirror={present}")
        total_projected += len(paths)
        total_present += present
    lines.append(f"  TOTAL: projected={total_projected} present_in_mirror={total_present}")
    return lines


# ---------------------------------------------------------------------------
# Citation extraction and checking
# ---------------------------------------------------------------------------

#: Text extensions this checker scans for citations -- read off the store's own base
#: `file_surface.include_extensions` as DATA (not a hand-copied second list; see module
#: docstring's hard-constraint framing -- this reads the config, it does not re-derive
#: engine walk semantics).
_TEXT_EXTENSIONS_FALLBACK = (".md", ".py", ".json", ".sh", ".ts", ".toml", ".js", ".mjs", ".ps1", ".cmd")

_FENCE = re.compile(r"^\s*```")
_MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: A `coordinator/...`-rooted bare path or file:line reference -- the one directory prefix
#: every publish row actually sources from (§ module docstring's scope decision: a bare
#: path is checked only when it is unambiguously rooted at the tree this projector knows
#: how to map onto the mirror; see `_prepublish_projection_citations` test module for why
#: this is a deliberate, documented v1 scope rather than a general path-shaped-token sweep).
_COORDINATOR_PATH = re.compile(
    r"\bcoordinator/[\w./\-]+\.(?:md|py|sh|json|ya?ml|ts|toml|js|mjs|ps1|cmd)\b(?::(\d+))?"
)


@dataclass(frozen=True)
class Citation:
    source_file: str  # repo-root-relative, the file the citation was found IN
    line_no: int
    kind: str  # "markdown-link" | "markdown-image" | "bare-path"
    raw_target: str
    excerpt: str


def _load_text_extensions() -> "tuple[str, ...]":
    try:
        import yaml  # noqa: PLC0415

        store = yaml.safe_load(STORE_PATH.read_text(encoding="utf-8"))
        exts = (store.get("base") or {}).get("file_surface", {}).get("include_extensions") or []
        normalized = tuple(sorted({e.lstrip("*") for e in exts if e.startswith("*.")}))
        if normalized:
            return normalized
    except Exception:
        pass
    return _TEXT_EXTENSIONS_FALLBACK


def _looks_like_a_path(href: str) -> bool:
    """A markdown-link href is only worth checking as a repo citation if it could
    possibly BE a repo path -- a bare word with no directory separator and no file
    extension (`url`, `target`, `here`) is syntax-documentation prose (`` [text](url) ``
    describing link syntax), never a real citation. Directory targets (`docs/wiki/`)
    keep their trailing slash and pass here on the strength of the `/` alone (§
    `_resolve_markdown_link_target`'s directory handling, AC4)."""
    return "/" in href or "." in href


def iter_citations(text: str, *, source_file: str) -> "list[Citation]":
    """Every markdown-link/image and `coordinator/`-rooted bare-path/file:line citation in
    `text`, in line order. Deliberately does NOT blank fenced code blocks -- the dispatch
    brief scopes bare-path detection to "prose and code fences that look like repo paths",
    so a fenced example citing a real path is in scope here (unlike the sibling
    `_prompt_surface_citations.py` detector, which exempts fences entirely for a different
    class of citation).

    Markdown-link/image extraction is restricted to actual markdown content
    (`source_file` ending `.md`) -- a `"pattern": "...[01]\\d...(...)"`-shaped regex
    literal inside a `.json` schema is not a markdown link, and extracting it as one is
    a pure false positive (§ dispatch brief class 1, 243 findings). Bare-path extraction
    (`_COORDINATOR_PATH`) is unaffected -- it stays live in code/data files, which is
    exactly where a bare `coordinator/...` path citation legitimately appears (docstrings,
    comments, `Spec backlink:` lines)."""
    citations: list[Citation] = []
    is_markdown = source_file.lower().endswith(".md")
    for line_no, line in enumerate(text.split("\n"), start=1):
        excerpt = " ".join(line.split())[:120]
        if is_markdown:
            for m in _MD_LINK.finditer(line):
                href = m.group(1)
                if "://" in href or href.startswith("mailto:") or href.startswith("#"):
                    continue
                if not _looks_like_a_path(href):
                    continue
                kind = "markdown-image" if line[max(0, m.start() - 1) : m.start()] == "!" or m.group(0).startswith("!") else "markdown-link"
                citations.append(Citation(source_file, line_no, kind, href, excerpt))
        for m in _COORDINATOR_PATH.finditer(line):
            citations.append(Citation(source_file, line_no, "bare-path", m.group(0), excerpt))
    return citations


@dataclass(frozen=True)
class Finding:
    citation: Citation
    reason: str  # "excluded-from-publish" | "absent-from-source"


def _resolve_markdown_link_target(citing_dest_relpath: str, href: str) -> str:
    """Resolve a relative markdown link/image target against the CITING file's own
    destination-relative directory -- markdown links are resolved relative to the
    document they appear in, in the mirror, not in this source tree.

    A trailing slash (`docs/wiki/`) denotes a DIRECTORY target and is preserved on the
    resolved result (§ AC4) -- `check_citations` resolves a directory target against
    whether ANY projected path lies under it, since a directory itself never appears in
    `published_paths()` (only the files inside it do)."""
    href = href.split("#", 1)[0]
    if not href:
        return ""
    is_dir_target = href.endswith("/")
    citing_dir = citing_dest_relpath.rsplit("/", 1)[0] if "/" in citing_dest_relpath else ""
    combined = f"{citing_dir}/{href}" if citing_dir else href
    parts: list[str] = []
    for part in combined.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    resolved = "/".join(parts)
    if is_dir_target and resolved:
        resolved += "/"
    return resolved


#: `bin`/`lib` are the two allowlist entries this store's `coordinator-claude|mirror` row
#: routes to the engine-plane sibling repo via `source_map` rather than this repo's own
#: `coordinator/` (§ module docstring's KNOWN SIMPLIFICATIONS -- this repo tracks zero
#: files under `coordinator/bin`/`coordinator/lib`, per this repo's own CLAUDE.md). A
#: `coordinator/bin/...`/`coordinator/lib/...` bare-path citation's SOURCE existence check
#: must therefore also try the sibling root, or every such citation misclassifies as
#: "absent from source" when it is really just published from elsewhere.
_SOURCE_MAP_ROUTED_TOP_LEVEL = ("bin", "lib")


#: Dest-relative citation targets (`coordinator/` prefix already stripped, same form
#: `check_citations` compares against `published`) naming a doctrine home this repo
#: RETIRED by ratified decision. A citation of one is a deliberate provenance annotation
#: sitting beside an already-correct pointer -- the migration's own audit trail -- not a
#: broken reference, so it must neither be flagged here nor pruned from the corpus
#: (pruning destroys the record of a ratified retirement).
#:
#: Every entry states its ratification, matching the engine-plane sibling's
#: `percolate-published-unscanned-exceptions.yaml` rule that an exclusion with no stated
#: reason is indistinguishable from an accident. Add an entry only for a path a human has
#: actually ratified as retired -- never to quiet a citation that is merely inconvenient.
_RETIRED_DOCTRINE_PATHS = {
    "CLAUDE.md": (
        "Retired and deleted 2026-07-27 (docs/plans/2026-07-27-claude-md-altitude-triage.md "
        "C11), content split to global-doctrine/CLAUDE.md + "
        "coordinator/snippets/em-operating-doctrine.md. Recorded as retired in "
        "coordinator/docs/wiki/claude-md-surfaces.md, which carries the surface table and "
        "the delivery-mechanism trap the annotations exist to explain."
    ),
}


#: Fallback changelog basenames, used only if the real definition (below) cannot be
#: read off the engine-plane sibling repo. Mirrors that repo's `coordinator/bin/publish.py`
#: `_CHANGELOG_DOC_BASENAMES` verbatim -- see `_load_changelog_basenames`.
_CHANGELOG_BASENAMES_FALLBACK = frozenset(
    {"changelog.md", "changes.md", "history.md", "release-notes.md", "releases.md"}
)


def _load_changelog_basenames(claude_klabauter_root: "Path | None") -> "frozenset[str]":
    """Read the CHANGELOG document-class basename set off the engine-plane sibling
    repo's own `coordinator/bin/publish.py::_CHANGELOG_DOC_BASENAMES` -- the publish
    pipeline's own, already-ratified "a changelog correctly cites files a later version
    removed" rule (§ that module's own docstring) -- rather than hand-writing a second
    table here that can drift from it (§ dispatch brief class 2).

    Read via `ast.parse` + `ast.literal_eval` on just that one assignment, NOT by
    importing `publish.py` in-process: that module is a full publish driver with a heavy,
    package-relative import ladder that is not resolvable as a bare
    `spec_from_file_location` load (confirmed: raises `AttributeError` on a bare load
    attempt) -- and this projector must stay read-only and side-effect-free regardless.
    Parsing is inert: it never executes the sibling module's code, only its syntax tree."""
    if claude_klabauter_root is None:
        return _CHANGELOG_BASENAMES_FALLBACK
    publish_py = claude_klabauter_root / "coordinator" / "bin" / "publish.py"
    if not publish_py.is_file():
        return _CHANGELOG_BASENAMES_FALLBACK
    try:
        tree = ast.parse(publish_py.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return _CHANGELOG_BASENAMES_FALLBACK
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == "_CHANGELOG_DOC_BASENAMES"):
            continue
        value_node = node.value
        # The real definition is `frozenset({...literal strings...})`.
        if isinstance(value_node, ast.Call) and getattr(value_node.func, "id", None) == "frozenset" and value_node.args:
            value_node = value_node.args[0]
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            return _CHANGELOG_BASENAMES_FALLBACK
        if isinstance(value, (set, frozenset)) and value:
            return frozenset(str(v).lower() for v in value)
    return _CHANGELOG_BASENAMES_FALLBACK


def _source_existence_roots(
    target: str,
    *,
    claude_klabauter_root: "Path | None",
    citing_source_path: "Path | None" = None,
) -> "list[Path]":
    """Every real filesystem path worth checking for `target` (a `coordinator/`-rooted
    dest-relpath candidate, prefix already stripped by the caller) actually existing
    SOMEWHERE in source -- even when it is not in the projected publish set. Order
    matters only for readability; the caller only cares whether ANY candidate exists.

    Two roots can supply a `coordinator/`-rooted citation, and BOTH are tried:

    - `_SOURCE_MAP_ROUTED_TOP_LEVEL` (`bin`/`lib`): a citation whose own first path
      segment is one this store routes to the engine-plane sibling, wherever the citing
      file itself came from.
    - `citing_source_path`'s OWN repo root: a bare-path citation is authored
      source-relative *by its author*, so a file published FROM the engine-plane sibling
      resolves its `coordinator/...` citations against that sibling's tree first --
      including top-level roots (`tests/`, `docs/`) that are not themselves routed. This
      leg is what stops a sibling-resident test/doc citation inside a sibling-sourced
      file from misclassifying as `absent-from-source`; deriving it from the file's
      resolved `source_path` reuses the row's own `source_map` routing rather than
      re-deriving (or hand-extending) a second table of roots that can drift from it.
    """
    candidates = [REPO_ROOT / "coordinator" / target]
    if claude_klabauter_root is not None:
        claude_klabauter_candidate = claude_klabauter_root / "coordinator" / target
        routed = target.split("/", 1)[0] in _SOURCE_MAP_ROUTED_TOP_LEVEL
        cited_from_claude_klabauter = citing_source_path is not None and _is_relative_to(
            citing_source_path, claude_klabauter_root
        )
        if routed or cited_from_claude_klabauter:
            candidates.append(claude_klabauter_candidate)
    return candidates


def _is_relative_to(path: Path, root: Path) -> bool:
    """`Path.is_relative_to` without its 3.9+ floor -- this module's interpreter floor is
    the harness's, not this repo's, and a bare `is_relative_to` call would be the only
    version-gated construct in the file."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def check_citations(projection: Projection, *, claude_klabauter_root: "Path | None" = None) -> "list[Finding]":
    """Every citation, in every published text file, whose target will NOT be present in
    the projected mirror. Deterministic, sorted output (§ dispatch brief)."""
    published = projection.published_paths()
    text_extensions = _load_text_extensions()
    changelog_basenames = _load_changelog_basenames(claude_klabauter_root)
    findings: list[Finding] = []

    for pf in sorted(projection.files, key=lambda f: f.dest_relpath):
        if not pf.dest_relpath.endswith(text_extensions):
            continue
        dest_basename = pf.dest_relpath.rsplit("/", 1)[-1].lower()
        if dest_basename in changelog_basenames:
            # A changelog correctly names files a later version removed -- that is
            # the historical record working as intended, not a broken citation
            # (§ dispatch brief class 2; matches the engine-plane sibling repo's own
            # `_install_doc_paths_for_repo_root` ruling for the same document class).
            continue
        if not pf.source_path.is_file():
            continue
        try:
            text = pf.source_path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue

        for citation in iter_citations(text, source_file=pf.dest_relpath):
            if citation.kind == "bare-path":
                raw = citation.raw_target.split(":")[0] if re.search(r":\d+$", citation.raw_target) else citation.raw_target
                # Every row sources from somewhere under `coordinator/` (§ ROW MODEL) --
                # a bare-path citation is authored SOURCE-relative (the doctrine-plane convention),
                # so the prefix must be stripped before comparing against `published`,
                # which is already dest-relative (coordinator/ implicitly stripped by
                # every row's own source_subpath resolution).
                target = raw[len("coordinator/") :] if raw.startswith("coordinator/") else raw
            else:
                target = _resolve_markdown_link_target(pf.dest_relpath, citation.raw_target)
                if not target:
                    continue

            if target in published:
                continue
            if target in _RETIRED_DOCTRINE_PATHS:
                continue
            if target.endswith("/") and any(p.startswith(target) for p in published):
                # Directory target (§ AC4): the directory itself is never a member of
                # `published_paths()` (only the files beneath it are) -- it resolves
                # if ANY projected path is materialized under it.
                continue

            exists_in_source = any(
                p.is_file()
                for p in _source_existence_roots(
                    target, claude_klabauter_root=claude_klabauter_root, citing_source_path=pf.source_path
                )
            )
            reason = "absent-from-source" if not exists_in_source else "excluded-from-publish"
            findings.append(Finding(citation=citation, reason=reason))

    return sorted(
        findings,
        key=lambda f: (f.citation.source_file, f.citation.line_no, f.citation.raw_target),
    )


def format_findings(findings: "list[Finding]") -> str:
    lines = []
    for f in findings:
        lines.append(
            f"{f.citation.source_file}:{f.citation.line_no}: cites {f.citation.raw_target!r} "
            f"({f.citation.kind}) -- {f.reason}: {f.citation.excerpt}"
        )
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    try:
        projection = project_publish_paths()
    except ProjectionUnavailableError as exc:
        print(f"prepublish-projection: UNAVAILABLE -- {exc}", file=sys.stderr)
        return 2

    for row_name in sorted(projection.rows):
        print(f"row {row_name}: {len(projection.rows[row_name])} projected file(s)")
    for issue in projection.issues:
        print(f"ISSUE [{issue.row}] {issue.entry}: {issue.reason}", file=sys.stderr)

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except ProjectionUnavailableError:
        claude_klabauter_root = None

    findings = check_citations(projection, claude_klabauter_root=claude_klabauter_root)
    if findings:
        print(format_findings(findings))
        print(f"\n{len(findings)} broken citation(s) found.", file=sys.stderr)
        return 1

    print("prepublish-projection: clean -- no broken citations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
