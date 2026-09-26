# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
cruft-sweep — Layer 1 autonomous cruft pruner for coordinator state (naked-Python
port, chunk A: header/resolver-preamble/arg-parse/lock/helpers, L1-523 of the
bash oracle).

Purpose: prune stale harness session state (projects/<repo>/<uuid>/, *.jsonl,
         file-history/<uuid>/) on a configurable retention threshold, with an
         active-handoff predecessor pre-flight to avoid deleting referenced
         work. Phase B prunes stale in-repo scratch directories by
         name-anchored list. Phase C scans parent-altitude roots for orphaned
         coordinator installs.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1, § C2
Port backlink: docs/plans/2026-07-21-cruft-sweep-naked-python-port.md (chunk A)
Debt backlink: state/debt-backlog/2026-07-21-cruft-sweep-unported-wave-e2-claim-overstated.yaml

Usage:
  cruft-sweep [OPTIONS]

Options:
  --days N               Retention threshold in days (default: 14; reads
                         cruft_sweep.harness_retention_days from machine-local
                         registry if present; flag overrides)
  --apply                Delete matching items (default: dry-run)
  --dry-run              Report only, no deletions (default)
  --class harness|scratch|orphans|empty-dirs|all
                         Which class to sweep (default: all). empty-dirs is
                         net-new (no bash-oracle counterpart) — see chunk
                         boundary note below and coordinator_core.ops.
                         cruft_sweep's module docstring.
  --json                 With --dry-run, emit JSONL records on stdout
                         (schema: {class, path, name, size_bytes, mtime,
                         disposition, evidence})
  --projects-root <path>  Default: ~/.claude/projects
  --file-history-root <path>  Default: ~/.claude/file-history
  --handoffs-glob <glob>  Glob for active handoff files
                          Default: $(coordinator_state_root)/handoffs/*.md —
                          resolves to the CURRENT git root's state/handoffs/
                          under default (no-flag) invocation.
  --log-path <path>       Sweep log path (default:
                          $(coordinator_state_root --central)/cruft-sweep-log.md)
  --parent-root <path>    (repeatable; when given, replaces default parent
                          roots for the Phase C orphan scan; tests pass
                          tmp_path overrides)
  --scratch-age-days N    Scratch retention threshold in days (default: 7)
  --repo-root <path>      Scratch scan root (default: enclosing git repo
                          root, or cwd if not in a git repo); useful for tests
  --quiet                 Suppress human-readable banner

  cruft_sweep.projects_size_cap_gib (machine-local registry key, default: 2)
                          Byte-cap in GiB for UUID-gated projects/ bytes,
                          resolved at _apply_machine_local_days_override.
  cruft_sweep.size_cap_mtime_floor_hours (machine-local registry key,
                          default: 24) Age floor below which a file is
                          never evicted by the size cap.

Exit codes:
  0  success or lock contention (contention exits silently)
  1  unexpected error (including COORDINATOR_CONTENT_ROOT / doe-root
     resolution failure)
  2  invalid flags

Portability: pure stdlib Python (no subprocess spawn on the hot path except
  the optional `machine-local` registry read and the native coordinator_core
  bootstrap's own `machine-local` call) — this is the whole point of the
  naked-Python port relative to the bash oracle's coreutils dependence.

Concurrency: exclusive lock via os.mkdir at LOCK_DIR (atomic on POSIX and
  Windows). On contention (or any other mkdir failure — a faithfully
  preserved bash-oracle quirk, see negative-spec), exit 0 silently — the
  other run (or nothing) owns the work.

Negative-spec: does NOT scan beyond --parent-root roots speculatively.
  Does NOT emit JSONL for non-name-matched parent-altitude dirs (silent).
  Does NOT use flock(1)/fcntl (mkdir-based lock only, portable to Windows).
  A mkdir failure for ANY reason (contention OR e.g. a missing parent
  directory) exits 0 silently — this mirrors the bash oracle's
  `if ! mkdir "$LOCK_DIR"; then exit 0; fi` exactly; it is not scoped to
  EEXIST only. Do NOT narrow this to FileExistsError-only when extending —
  that would be a behavior change, not a faithful port.
  Does NOT reap the install-baton rendezvous under default (no --parent-root)
  invocation, nor under an explicit --parent-root pointed at settings-home
  (Phase C hard-excludes it by resolved-path compare — ported in a later
  chunk, this chunk only carries the doc-comment forward).

CHUNK BOUNDARY (2026-07-21 naked-Python port, chunk A of 4): this module
  ports ONLY the bash oracle's L1-523 — header, native-resolver preamble,
  content-root + trusted-root-guard, defaults, arg-parse, machine-local
  read, mkdir-lock + trap, and the six shared helpers
  (_get_mtime, _file_size, _dir_size_bytes, _emit_jsonl,
  _build_uuid_blocklist, _is_blocked). Phase A/B/C dispatch bodies,
  log-append, and the grand-total banner (bash oracle L524-1632) are NOT
  yet ported — later chunks (B/C/D) land those on top of this contract.
  `main()` below acquires the lock, computes all defaults/overrides, and
  currently no-ops the dispatch (exits 0) — this keeps --help/bad-flag/
  lock-contention/lock-release behavior testable now without inventing
  Phase A/B/C logic ahead of its chunk.

CHUNK BOUNDARY (chunk B of 4, this addendum): ports the bash oracle's
  L524-776 `_sweep_harness` — the Phase A harness-retention sweep (stale
  projects/<repo>/<uuid>/ dirs, <uuid>.jsonl transcripts, and
  file-history/<uuid>/ dirs, each on a configurable mtime-age threshold,
  honoring the predecessor-UUID block-list) plus its per-class dry-run
  banner and its apply-mode log-append row. `main()` now dispatches to
  `_sweep_harness` when `cfg.class_` is "harness" or "all"; the
  scratch/orphans branches and the grand-total banner remain chunk C/D
  territory (see the negative-spec note on `_sweep_harness` re: the
  bash-oracle watchdog's stall-detection half being dropped as
  inapplicable to this port's non-subprocess loop body).

CHUNK BOUNDARY (chunk C+D of 4, this addendum, ported together — the paired
  test file test_cruft_sweep_phase_b.py straddles both and neither phase
  greens alone): ports the bash oracle's L777-1632 — `_sweep_scratch` (Phase
  B in-repo scratch sweep, name-anchored auto-prune/confirm-needed/backup
  classes, .git-boundary + negative-spec-component skips, git-tracked skip,
  the 24h mtime-floor consolidated with the configurable age threshold via
  max()), `_sweep_subagent_sandbox_files` (file-level 24h reap of
  scratch/subagent-sandbox/*.md — never prunes the dir itself),
  `_sweep_orphans` (Phase C parent-altitude orphan sweep — conjoint
  name-match + sonnet-fingerprint gate, hard-exclude list including the
  install-baton-rendezvous forward-guard and the machine-local
  parent_whitelist), and the main-dispatch `case $CLASS` block + grand-total
  banner + run-marker log row. `main()` now dispatches all four classes
  (`harness`, `scratch`, `orphans`, `all`) exactly as the bash oracle's
  `case "$CLASS" in ... esac` does. This completes the naked-Python port.

  DELIBERATE DIVERGENCE (parity with chunk B's own precedent, not a new
  design choice): `_sweep_scratch` and `_sweep_orphans` each carry the same
  wall-clock-CEILING-only watchdog bail `_sweep_harness` already documents
  (300s per phase) — the bash oracle's stall-detection half is dropped for
  the identical reason given there (this port's loop bodies spawn no
  probe-subprocess for the stall detector to watch).

  DELIBERATE PARITY (not fixed here): the grand-total banner sums
  harness+scratch+orphans+empty-dirs bytes/items, mirroring the bash
  oracle's `_total_all_bytes=$(( HARNESS_BYTES + SCRATCH_BYTES +
  ORPHANS_BYTES ))` for the three ported classes — subagent-sandbox
  reclaimed bytes/items are tracked on `Totals` but are NOT folded into the
  grand total, faithfully reproducing what reads as a bash-oracle omission
  rather than correcting it (see PRIOR-CHUNK CONTRACT NOTES in the port plan
  for why this port does not unilaterally fix oracle-level behavior).

CHUNK BOUNDARY (Phase E, 2026-07-28 addendum — NET-NEW, no bash oracle):
  adds `--class empty-dirs` (folded into `all`), a structural (not
  name-literal) sweep for top-level repo-root directories containing zero
  files anywhere in their subtree, past the 24h mtime floor, and not
  git-ignored — the class of cruft a fake-$HOME skeleton (ten levels of
  nested empty dirs, zero files) and arbitrary `mkdir`'d prose-word dirs
  both fell through undetected between 2026-07-22 and 2026-07-28, since git
  is structurally blind to directories with nothing in them and
  `_sweep_orphans`'s name-literal + sonnet-fingerprint gate requires BOTH a
  name match and fingerprint contents. Unlike Phases A/B/C, this phase is
  NOT re-implemented as a private duplicate in this file — it delegates to
  `coordinator_core.ops.cruft_sweep.sweep_empty_toplevel_dirs` (imported
  above), this port's one deliberate departure from the duplicate-per-file
  convention, made because there is no bash oracle here to port in the
  first place, so there is nothing this file's own copy would be "porting."
  Folded into the grand-total banner and run-marker log row (this port's
  own design choice, not an oracle mirror — see the empty_dirs_bytes/items
  Totals fields' comment).

CHUNK BOUNDARY (2026-07-28 collapse addendum — duplicate-port unification):
  Phases A/B/C (`_sweep_harness`/`_sweep_scratch`/`_sweep_subagent_sandbox_files`/
  `_sweep_orphans`) were each an independent, hand-ported duplicate of the
  corresponding `coordinator_core.ops.cruft_sweep` engine function — the two
  had drifted (see docs/research/2026-07-28-cruft-sweep-duplicate-port-drift-
  audit.md for the full enumeration): the engine already carried
  delete-confirmation gating and UUID-blocklist fail-closed apply as
  break-class fixes this trampoline never received, while this trampoline
  carried a `_dir_size_bytes` hang-budget and a Windows-safe pruned-parent
  check the engine lacked (both ported into the engine before this collapse,
  per that audit's D3/D4). This file's four `_sweep_*` functions are now thin
  wrappers: resolve CLI-owned inputs (repo root, blocklist, parent roots,
  whitelist, settings-home) and delegate to the engine functions, the same
  shape Phase E already used. No private duplicate of `_get_mtime`,
  `_file_size`, `_dir_size_bytes`, `_emit_jsonl`, `_is_untracked`,
  `_enumerate_all_dirs`/`_is_pruned_child`, `_is_auto_prune_name`/
  `_is_confirm_needed_name`/`_is_backup_name`, `_has_git_boundary`/
  `_has_negative_spec_component`, `_is_orphan_name_match`/
  `_has_sonnet_fingerprint`, or `_UUID_RE`/`_build_uuid_blocklist`/`_is_blocked`
  remains in this file — see the engine module's own negative-spec for what
  it does NOT own (still this file's job): CLI/argparse, machine-local +
  registry resolution, the `coordinator_state_root` seam, `--parent-root`
  default derivation, the `parent_whitelist` TOML/grep read, CLASS dispatch,
  the grand-total banner, and the run-marker log row.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# shells out to via `${_CSR_LIB_DIR}/settings_home.py --print-home`. Imported
_COORDINATOR_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"
)


def _bootstrap_engine() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    if _COORDINATOR_LIB_DIR not in sys.path:
        sys.path.insert(0, _COORDINATOR_LIB_DIR)

    try:
        require_dispatch_engine_on_path()
    except RuntimeError as _exc:
        sys.stderr.write(
            f"cruft-sweep: cannot resolve the engine root for native coordinator_core "
            f"import: {_exc}\n"
        )
        sys.exit(1)


# Phases A-D (2026-07-28 collapse — see CHUNK BOUNDARY addendum below) now

SELF_NAME = "cruft-sweep"


_STATE_ROOT_FAILURES: dict[bool, str] = {}


def _state_root_or_empty(*, central: bool = False) -> str:
    """coordinator_state_root(...), folding StateRootError to "" — mirrors the
    bash oracle's `$(coordinator_state_root ...)` command-substitution
    semantics: a failing subshell contributes an empty string to the
    surrounding string concatenation rather than aborting the script (the
    failure only becomes visible later, as a malformed path). Faithful
    port of an existing bash-oracle quirk, not a design choice made here.

    Records the swallowed reason in `_STATE_ROOT_FAILURES` so
    `_reject_rootless_defaults` can name the ACTUAL cause. The empty-string
    return is the oracle-faithful part; discarding the diagnosis was never
    load-bearing."""
    from coordinator_core.state_root import StateRootError, coordinator_state_root

    try:
        root = coordinator_state_root(central=central)
        _STATE_ROOT_FAILURES.pop(central, None)
        return root
    except StateRootError as exc:
        _STATE_ROOT_FAILURES[central] = str(exc)
        return ""


def _read_doe_root_pointer() -> str:
    """Durable-first, legacy-fallback `.doe-root` pointer read — mirrors the
    bash oracle's inline fallback (L158-162), used ONLY when
    resolve_content_root() itself fails (see _resolve_and_guard_content_root
    below). Deliberately a local, tiny reimplementation rather than importing
    coordinator_core.resolve_coordinator_clone._read_doe_root_pointer (a
    private symbol of a sibling module) — same convention that module's own
    docstring already documents as accepted (each caller keeps its own copy
    rather than sharing a private helper across module boundaries).

    Deliberately terminates the `home` ladder at `CLAUDE_HOME or HOME or
    USERPROFILE or ""` — no `expanduser("~")`/`Path.home()` PATH_HOME rung.
    A missing home here correctly degrades to "no settings-home, no pointer
    file" (empty return below); the caller's own fallback path takes over
    from there. Intentional narrowing, not an unjustified ladder-shortening
    (review: code-reviewer, info-only finding) — do not re-add the rung
    without re-checking that reasoning."""
    settings_home_override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    home = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or ""
    )
    if settings_home_override:
        settings_home_dir = settings_home_override
    elif home:
        settings_home_dir = os.path.join(home, ".coordinator-claude-settings")
    else:
        settings_home_dir = ""

    doe_root = ""
    if settings_home_dir:
        try:
            with open(
                os.path.join(settings_home_dir, "machine-local", ".doe-root"),
                "r",
                encoding="utf-8",
            ) as f:
                doe_root = f.read().strip()
        except OSError:
            doe_root = ""
    if not doe_root and home:
        try:
            with open(
                os.path.join(home, ".claude", ".doe-root"), "r", encoding="utf-8"
            ) as f:
                doe_root = f.read().strip()
        except OSError:
            doe_root = ""
    return doe_root


def _resolve_and_guard_content_root() -> None:
    """Resolve COORDINATOR_CONTENT_ROOT and, ONLY on the .doe-root fallback
    path, run the trusted-root-guard fail-loud check — mirrors the bash
    oracle's control flow EXACTLY (L144-180): the primary
    resolve-coordinator-clone resolver is trusted implicitly (its own ladder
    already only returns well-known trusted locations); the guard only fires
    when that primary resolver fails and this falls back to reading the raw
    `.doe-root` pointer file directly. Exits 1 (mirroring the bash oracle's
    literal `exit 1`) if neither path resolves a usable content root."""
    from coordinator_core.resolve_coordinator_clone import (
        ResolveCoordinatorCloneError,
        resolve_content_root,
    )
    from coordinator_core.trusted_root_guard import coordinator_trusted_root_guard_or_exit

    content_root = ""
    try:
        content_root = resolve_content_root()
    except ResolveCoordinatorCloneError:
        content_root = ""

    if content_root:
        return

    from coordinator_data_root import content_root_for

    doe_root = _read_doe_root_pointer()
    pointed = content_root_for(doe_root)
    if pointed is None:
        sys.stderr.write(
            "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install\n"
        )
        sys.exit(1)

    content_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(pointed)
    coordinator_trusted_root_guard_or_exit(
        mode="fail-loud", root=content_root, site=sys.argv[0]
    )


HELP_TEXT = """\
cruft-sweep — Layer 1 autonomous cruft pruner for coordinator state.

Usage:
  cruft-sweep [OPTIONS]

Options:
  --days N               Retention threshold in days (default: 14)
  --apply                Delete matching items (default: dry-run)
  --dry-run              Report only, no deletions (default)
  --class harness|scratch|orphans|empty-dirs|all
                          Which class to sweep (default: all).
                          empty-dirs is net-new (no bash-oracle
                          counterpart): top-level repo-root dirs with zero
                          files anywhere in their subtree, see
                          coordinator_core.ops.cruft_sweep module docstring.
  --json                 With --dry-run, emit JSONL records on stdout
                          (schema: {class, path, name, size_bytes, mtime,
                          disposition, evidence})
  --projects-root <path>  Default: ~/.claude/projects
  --file-history-root <path>  Default: ~/.claude/file-history
  --handoffs-glob <glob>  Glob for active handoff files
  --log-path <path>       Sweep log path
  --parent-root <path>    (repeatable) Phase C orphan-scan roots
  --scratch-age-days N    Scratch retention threshold in days (default: 7)
  --repo-root <path>      Scratch scan root
  --quiet                 Suppress human-readable banner
  -h, --help              Show this help and exit

  cruft_sweep.projects_size_cap_gib (machine-local registry key, default: 2)
                          Byte-cap in GiB for UUID-gated projects/ bytes.
  cruft_sweep.size_cap_mtime_floor_hours (machine-local registry key,
                          default: 24) Age floor below which a file is never
                          evicted by the size cap.

Exit codes:
  0  success or lock contention (contention exits silently)
  1  unexpected error
  2  invalid flags
"""


@dataclass
class SweepConfig:

    days: str = "14"
    apply: bool = False
    class_: str = "all"
    json_mode: bool = False
    quiet: bool = False
    # Deliberately shorter ladder (HOME -> USERPROFILE, no CLAUDE_HOME rung), per the
    # ~/.claude/projects and ~/.claude/file-history there regardless of CLAUDE_HOME,
    # CLAUDE_HOME rung here would point the sweep at a directory the harness never
    projects_root: str = field(default_factory=lambda: os.path.join(
        os.environ.get("HOME") or os.environ.get("USERPROFILE") or "",
        ".claude", "projects",
    ))
    file_history_root: str = field(default_factory=lambda: os.path.join(
        os.environ.get("HOME") or os.environ.get("USERPROFILE") or "",
        ".claude", "file-history",
    ))
    handoffs_glob: str = ""
    log_path: str = ""
    lock_dir: str = ""
    parent_roots: List[str] = field(default_factory=list)
    scratch_age_days: str = "7"
    repo_root: str = ""
    size_cap_gib: str = "2"
    size_cap_floor_hours: str = "24"


@dataclass
class Totals:
    """Shared cross-class byte/item totals — module-level equivalent of the
    bash oracle's HARNESS_BYTES/SCRATCH_BYTES/ORPHANS_BYTES + *_ITEMS
    variables. Passed explicitly to (and mutated by) each phase's dispatch
    function in later chunks; main() reads all six fields to render the
    grand-total banner (also a later chunk)."""

    harness_bytes: int = 0
    harness_items: int = 0
    scratch_bytes: int = 0
    scratch_items: int = 0
    orphans_bytes: int = 0
    orphans_items: int = 0
    # "DELIBERATE PARITY" note (chunk C+D): the bash oracle's own grand-total
    subagent_sandbox_bytes: int = 0
    subagent_sandbox_items: int = 0
    empty_dirs_bytes: int = 0
    empty_dirs_items: int = 0


def _usage_error(message: str) -> "int":
    sys.stderr.write(f"{SELF_NAME}: {message}\n")
    return 2


def parse_args(argv: List[str]) -> SweepConfig:
    cfg = SweepConfig()
    central_state_root = _state_root_or_empty(central=True)
    non_central_state_root = _state_root_or_empty(central=False)
    cfg.handoffs_glob = f"{non_central_state_root}/handoffs/*.md"
    cfg.log_path = f"{central_state_root}/cruft-sweep-log.md"
    cfg.lock_dir = f"{central_state_root}/cruft-sweep.lock.d"

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--days":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--days requires a value"))
            cfg.days = argv[i + 1]
            i += 2
        elif arg == "--apply":
            cfg.apply = True
            i += 1
        elif arg == "--dry-run":
            cfg.apply = False
            i += 1
        elif arg == "--class":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--class requires a value"))
            value = argv[i + 1]
            if value not in ("harness", "scratch", "orphans", "empty-dirs", "all"):
                sys.exit(
                    _usage_error(
                        f"unknown class '{value}' (expected: harness, scratch, "
                        "orphans, empty-dirs, all)"
                    )
                )
            cfg.class_ = value
            i += 2
        elif arg == "--json":
            cfg.json_mode = True
            i += 1
        elif arg == "--projects-root":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--projects-root requires a value"))
            cfg.projects_root = argv[i + 1]
            i += 2
        elif arg == "--file-history-root":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--file-history-root requires a value"))
            cfg.file_history_root = argv[i + 1]
            i += 2
        elif arg == "--handoffs-glob":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--handoffs-glob requires a value"))
            cfg.handoffs_glob = argv[i + 1]
            i += 2
        elif arg == "--log-path":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--log-path requires a value"))
            cfg.log_path = argv[i + 1]
            i += 2
        elif arg == "--parent-root":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--parent-root requires a value"))
            cfg.parent_roots.append(argv[i + 1])
            i += 2
        elif arg == "--scratch-age-days":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--scratch-age-days requires a value"))
            cfg.scratch_age_days = argv[i + 1]
            i += 2
        elif arg == "--repo-root":
            if i + 1 >= n or not argv[i + 1]:
                sys.exit(_usage_error("--repo-root requires a value"))
            cfg.repo_root = argv[i + 1]
            i += 2
        elif arg == "--quiet":
            cfg.quiet = True
            i += 1
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP_TEXT)
            sys.exit(0)
        else:
            sys.exit(_usage_error(f"unknown flag '{arg}'\n  Use --help for usage."))

    _reject_rootless_defaults(cfg, central_state_root, non_central_state_root)
    return cfg


def _reject_rootless_defaults(
    cfg: SweepConfig, central_state_root: str, non_central_state_root: str
) -> None:
    if central_state_root and non_central_state_root:
        return
    unresolved = [
        flag
        for flag, root, value, default in (
            ("--log-path", central_state_root, cfg.log_path, "/cruft-sweep-log.md"),
            (
                "--handoffs-glob",
                non_central_state_root,
                cfg.handoffs_glob,
                "/handoffs/*.md",
            ),
        )
        if not root and value == default
    ]
    if not unresolved:
        return
    causes = [
        _STATE_ROOT_FAILURES[central]
        for central in (True, False)
        if central in _STATE_ROOT_FAILURES
    ]
    reason = (
        " Cause: " + " / ".join(causes)
        if causes
        else " Cause: no state root is registered for this machine — "
        "machine-local set repos.claude_klabauter <path-to-live-claude-klabauter>."
    )
    sys.exit(
        _usage_error(
            "state root did not resolve; refusing to write to the drive root "
            "(%s). Pass %s.%s"
            % (cfg.log_path, " and ".join(unresolved), reason)
        )
    )


def _apply_machine_local_days_override(cfg: SweepConfig) -> None:
    from coordinator_core.machine_resolver import registry_get as _machine_registry_get

    value = _machine_registry_get("cruft_sweep.harness_retention_days")
    if value:
        value = value.strip()
    if value and value.isdigit():
        cfg.days = value

    cap_value = _machine_registry_get("cruft_sweep.projects_size_cap_gib")
    if cap_value:
        cap_value = cap_value.strip()
    if cap_value:
        try:
            if float(cap_value) > 0:
                cfg.size_cap_gib = cap_value
        except ValueError:
            pass

    floor_value = _machine_registry_get("cruft_sweep.size_cap_mtime_floor_hours")
    if floor_value:
        floor_value = floor_value.strip()
    if floor_value and floor_value.isdigit() and int(floor_value) > 0:
        cfg.size_cap_floor_hours = floor_value


def _acquire_lock(lock_dir: str) -> None:
    """Exclusive lock via os.mkdir (atomic on POSIX and Windows). On ANY
    mkdir failure (contention OR e.g. a missing parent directory), exit 0
    silently — mirrors the bash oracle's `if ! mkdir "$LOCK_DIR"; then exit
    0; fi` exactly (not narrowed to EEXIST-only; see module negative-spec)."""
    try:
        os.mkdir(lock_dir)
    except OSError:
        sys.exit(0)


def _release_lock(lock_dir: str) -> None:
    """Release the lock dir — mirrors the bash oracle's
    `trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT`. Best-effort: any
    shell-doc-ok: that trap is the shell line this describes.
    failure (already removed, permissions) is swallowed, never raised."""
    try:
        os.rmdir(lock_dir)
    except OSError:
        pass


# Phase A-D thin wrappers (2026-07-28 collapse — see CHUNK BOUNDARY addendum


def _resolve_repo_root(cfg: "SweepConfig") -> str:
    if cfg.repo_root:
        return cfg.repo_root
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel() or os.getcwd()


def _handoffs_dir_from_glob(handoffs_glob: str) -> Path:
    glob_dir = handoffs_glob.rsplit("/", 1)[0] if "/" in handoffs_glob else handoffs_glob
    if glob_dir == handoffs_glob and "\\" in handoffs_glob:
        glob_dir = handoffs_glob.rsplit("\\", 1)[0]
    return Path(glob_dir)


def _sweep_harness(cfg: "SweepConfig", totals: "Totals") -> None:
    from coordinator_core.ops.cruft_sweep import build_uuid_blocklist, sweep_harness

    handoffs_dir = _handoffs_dir_from_glob(cfg.handoffs_glob)
    blocklist, complete = build_uuid_blocklist(handoffs_dir)
    if not complete and cfg.apply:
        sys.stderr.write(
            f"{SELF_NAME}: ERROR: UUID blocklist scan of {handoffs_dir} was "
            "incomplete (unreadable handoff file(s) — see stderr warnings "
            "above); aborting --apply rather than deleting harness state on "
            "an incomplete protected-UUID set\n"
        )
        sys.exit(1)

    log_path = Path(cfg.log_path) if cfg.log_path else None
    size_cap_bytes = int(float(cfg.size_cap_gib) * 1024**3)
    size_cap_mtime_floor_secs = int(cfg.size_cap_floor_hours) * 3600
    harness_bytes, harness_items = sweep_harness(
        Path(cfg.projects_root), Path(cfg.file_history_root), int(cfg.days),
        blocklist, apply=cfg.apply, json_mode=cfg.json_mode, quiet=cfg.quiet,
        log_path=log_path,
        size_cap_bytes=size_cap_bytes,
        size_cap_mtime_floor_secs=size_cap_mtime_floor_secs,
    )
    totals.harness_bytes = harness_bytes
    totals.harness_items = harness_items


def _sweep_scratch(cfg: "SweepConfig", totals: "Totals") -> None:
    from coordinator_core.ops.cruft_sweep import sweep_scratch

    repo_root = Path(_resolve_repo_root(cfg))
    log_path = Path(cfg.log_path) if cfg.log_path else None
    scratch_bytes, scratch_items = sweep_scratch(
        repo_root, int(cfg.scratch_age_days),
        apply=cfg.apply, json_mode=cfg.json_mode, quiet=cfg.quiet,
        log_path=log_path,
    )
    totals.scratch_bytes = scratch_bytes
    totals.scratch_items = scratch_items


def _sweep_subagent_sandbox_files(cfg: "SweepConfig", totals: "Totals") -> None:
    from coordinator_core.ops.cruft_sweep import sweep_subagent_sandbox_files

    repo_root = Path(_resolve_repo_root(cfg))
    log_path = Path(cfg.log_path) if cfg.log_path else None
    sandbox_bytes, sandbox_items = sweep_subagent_sandbox_files(
        repo_root, apply=cfg.apply, json_mode=cfg.json_mode, quiet=cfg.quiet,
        log_path=log_path,
    )
    totals.subagent_sandbox_bytes = sandbox_bytes
    totals.subagent_sandbox_items = sandbox_items


def _get_parent_whitelist() -> set:
    from settings_home import settings_home as _coordinator_settings_home

    registry_path = os.path.join(
        _coordinator_settings_home(), "machine-local", "registry.local.toml"
    )
    if not os.path.isfile(registry_path):
        return set()
    try:
        with open(registry_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return set()

    whitelist: set = set()
    found_key = False
    for line in content.splitlines():
        if "parent_whitelist" in line:
            found_key = True
            whitelist.update(re.findall(r'"([^"]*)"', line))
    if found_key and not whitelist:
        sys.stderr.write(
            "cruft-sweep: WARNING: parent_whitelist found in registry but "
            "yielded no entries — if using multi-line TOML syntax, entries "
            'are silently ignored. Use single-line: parent_whitelist = '
            '["name"]\n'
        )
    return whitelist


def _default_parent_roots() -> List[str]:
    from coordinator_core.machine_resolver import merged_flat_registry as _merged_flat_registry

    flat = _merged_flat_registry()

    seen: set = set()
    roots: List[str] = []
    for key, val in flat.items():
        if not key.startswith("repos."):
            continue
        path_value = ("" if val is None else str(val)).strip()
        if not path_value:
            continue
        parent = os.path.dirname(path_value)
        if parent and parent not in seen:
            seen.add(parent)
            roots.append(parent)
    return roots


def _sweep_orphans(cfg: "SweepConfig", totals: "Totals") -> None:
    from coordinator_core.ops.cruft_sweep import sweep_orphans
    from settings_home import settings_home as _coordinator_settings_home

    roots = [Path(p) for p in cfg.parent_roots] if cfg.parent_roots else [
        Path(p) for p in _default_parent_roots()
    ]
    whitelist = _get_parent_whitelist()
    try:
        sh = _coordinator_settings_home()
    except Exception:
        sh = ""
    settings_home = Path(sh) if sh else None
    log_path = Path(cfg.log_path) if cfg.log_path else None

    orphans_bytes, orphans_items = sweep_orphans(
        roots, whitelist, apply=cfg.apply, json_mode=cfg.json_mode,
        quiet=cfg.quiet, log_path=log_path, settings_home=settings_home,
    )
    totals.orphans_bytes = orphans_bytes
    totals.orphans_items = orphans_items


def _sweep_empty_dirs(cfg: "SweepConfig", totals: "Totals") -> None:
    from coordinator_core.ops.cruft_sweep import sweep_empty_toplevel_dirs

    repo_root = Path(_resolve_repo_root(cfg))
    log_path = Path(cfg.log_path) if cfg.log_path else None

    total_bytes, pruned_items = sweep_empty_toplevel_dirs(
        repo_root,
        apply=cfg.apply,
        json_mode=cfg.json_mode,
        quiet=cfg.quiet,
        log_path=log_path,
    )
    totals.empty_dirs_bytes = total_bytes
    totals.empty_dirs_items = pruned_items


def _emit_grand_total_banner(totals: "Totals", json_mode: bool) -> int:
    total_bytes = (
        totals.harness_bytes + totals.scratch_bytes + totals.orphans_bytes
        + totals.empty_dirs_bytes
    )
    if not json_mode:
        total_mb = total_bytes // 1048576
        sys.stderr.write(
            f"[cruft-sweep] grand total: ~{total_mb} MB reclaimable across "
            "all classes\n"
        )
    return total_bytes


def _write_run_marker(cfg: "SweepConfig", totals: "Totals", total_bytes: int) -> None:
    total_items = (
        totals.harness_items + totals.scratch_items + totals.orphans_items
        + totals.empty_dirs_items
    )
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_dir = os.path.dirname(cfg.log_path)
    if log_dir and not os.path.isdir(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            pass
    try:
        with open(cfg.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(
                f"| {ts} | run-marker | {total_bytes} bytes | "
                f"{total_items} items |\n"
            )
        from coordinator_core.session.declared_writes import declare_write

        declare_write(cfg.log_path)
    except OSError:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    _bootstrap_engine()
    from coordinator_core.cli_entry import recording_declared_writes

    args = list(sys.argv[1:] if argv is None else argv)

    _resolve_and_guard_content_root()

    cfg = parse_args(args)
    _apply_machine_local_days_override(cfg)

    _acquire_lock(cfg.lock_dir)
    try:
        with recording_declared_writes():
            totals = Totals()

            # (L1580-1600) exactly — including "scratch" dispatching BOTH
            if cfg.class_ == "harness":
                _sweep_harness(cfg, totals)
            elif cfg.class_ == "scratch":
                _sweep_scratch(cfg, totals)
                _sweep_subagent_sandbox_files(cfg, totals)
            elif cfg.class_ == "orphans":
                _sweep_orphans(cfg, totals)
            elif cfg.class_ == "empty-dirs":
                _sweep_empty_dirs(cfg, totals)
            elif cfg.class_ == "all":
                _sweep_harness(cfg, totals)
                _sweep_scratch(cfg, totals)
                _sweep_subagent_sandbox_files(cfg, totals)
                _sweep_orphans(cfg, totals)
                _sweep_empty_dirs(cfg, totals)

            total_bytes = _emit_grand_total_banner(totals, cfg.json_mode)

            # runs. Mirrors the bash oracle's `if [[ "$APPLY" -eq 1 && "$JSON_MODE"
            if cfg.apply and not cfg.json_mode:
                _write_run_marker(cfg, totals, total_bytes)

        return 0
    finally:
        _release_lock(cfg.lock_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
