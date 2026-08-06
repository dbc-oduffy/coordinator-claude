#!/usr/bin/env python3
"""coordinator/bin/publish.py — percolate publish driver: sync dispatch spine.

Native-Python port of `setup/publish.sh`'s main loop (DoE 16302166, 2026-07-21) — SYNC
DISPATCH LAYER ONLY. Resolves the 4-tier publish-target set (via
`coordinator/lib/percolate/targets.py`), then for each resolved target row
dispatches to the mode-appropriate copy engine:

  mirror / flat-mirror  -> imports `setup/publish_sync.py` in-process if the
                            resolved percolate root carries one, else this
                            repo's own `coordinator/lib/percolate/publish_sync.py`
                            (§ `_resolve_publish_sync_module_path`, AMENDED
                            2026-08-03 — DR-079 `26450311a`), and calls
                            `sync_mirror` / `sync_flat_mirror` directly (never
                            subprocesses it — this driver already runs in the
                            same Python process).
  manifest              -> `sync_manifest` below, a faithful port of the bash
                            copy loop (`setup/publish.sh`), using
                            `files_differ`/`bytes_differ` ported from
                            `setup/lib/percolate-gate.sh`.

Then writes the last-sync marker (`setup/percolate-state/<name>.lastsync`),
matching `setup/publish.sh` (Phase 5) — records the DESTINATION repo HEAD at
publish time (pre-commit anchor `/percolate` uses for inverse-drift detection).

GATES — the per-target gates bash runs before dispatch (`setup/
publish.sh`) are ported in `run_pre_sync_gates` and its
helpers: identity-file owner+mode pre-source check (once, at driver
startup — see `main`), live-install-clobber guard, dirty-tree guard,
version-regression gate, version-consistency gate, and the non-fatal
machine-slug warn. Chunk C-W1d2 per
docs/plans/2026-07-21-percolate-python-port.md.

PERCOLATE-ENGINE CUTOVER (chunk C-W2) — the legacy pre-rsync/post-rsync hook
system (`setup/publish.sh`, which shelled the 14 `setup/
percolate-hooks/<target>/<hook_point>/*.sh` scripts) has been REPLACED, not
left as a no-op seam: `dispatch_percolate_pre_rsync` / `_post_rsync` /
`_inject` / `_pre_ci` call directly into the engine repo's
`coordinator_core.percolate` engine (`percolate_run.run_percolate` for the
3 phases + the separate `engine.run_inject_for_section` call) against
`setup/percolate-hooks/percolate-store.yaml`, resolved once per run via
`PercolateEngineContext` (see `main`). AC15 fail-closed (hard requirement):
an unreachable/unimportable engine, a bad/skewed store, an undeclared
target, or any phase-call raise/guard-failure aborts — this driver never
publishes a target's content unscrubbed. `--dry-run` skips engine-phase
dispatch entirely (the engine has no non-mutating preview mode; dispatching
it under `--dry-run` would mutate the destination, defeating the preview).
The 14 legacy hook `.sh` scripts + their `_lib/` are deleted (this chunk);
`setup/percolate-hooks/README.md` and the store's own header remain the
authoritative behavioral spec. Allowlist enforcement (`coordinator/lib/
percolate/allowlist.py`) IS wired — `run_pre_sync_gates` calls
`build_allowlisted_source` / `check_working_data_paths` /
`assert_allowlist_applied`, mode-agnostically, in the same position the bash
original runs them (`setup/publish.sh`, before the `case "$mode"`
dispatch at :1683). Fix: AC18(b), docs/plans/2026-07-21-percolate-python-port.md.

PERCOLATE_ROOT resolution (`resolve_percolate_root`) is a native-Python
in-process port of the bash bootstrap at `setup/publish.sh`: locate
`coordinator/bin/lib/cc_invoke.py`, call its `_resolve_claude_klabauter_root()`, then
import `coordinator_core.percolate.runtime_root.coordinator_percolate_runtime_root`
from the resolved engine repo checkout — the SAME underlying resolver the bash
original called via a `python3 -c` subprocess, just invoked directly since
this driver is already Python. Falls back to this repo's own root on any
failure, exactly mirroring the bash fallback's non-fatal degrade. This
resolution is the load-bearing fix for the one-level SOURCE_DIR offset
between the DoE-claude source layout (`coordinator/` IS the plugin root) and
the `~/.claude` live-install layout (`coordinator/` is one level below the
plugin root) — see `coordinator/docs/wiki/percolate-setup.md`.

Spec backlink: docs/plans/2026-06-22-portable-registry-resolved-publish-targets.md
Port: docs/plans/2026-07-21-percolate-python-port.md (chunk C-W1d1).

Negative-spec: this module performs no top-level side effects on import
(everything happens inside `main()`), and shells out to bash nowhere — the
percolate-engine dispatch calls `coordinator_core.percolate` in-process,
never via a subprocess or a bash trampoline (recipe §3 option b2, not b1).
It never syncs a target's UNRESTRICTED source tree once that target has
declared an allowlist — the FATAL post-condition (`assert_allowlist_applied`)
has no override and a failure there skips the target (mirrors the bash
`continue`), never downgrades to a warning. It never publishes a target
whose percolate-engine phase dispatch failed, raised, or returned a failing
guard result — AC15/AC8 fail-closed, never best-effort.
"""

from __future__ import annotations

import argparse
import filecmp
import importlib.util
import inspect
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import IO, Callable, List, NamedTuple, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COORDINATOR_LIB = _REPO_ROOT / "coordinator" / "lib"
if str(_COORDINATOR_LIB) not in sys.path:
    sys.path.insert(0, str(_COORDINATOR_LIB))
# percolate.targets resolves sibling modules via absolute `coordinator.lib.percolate.*`
# imports, so the repo root must be importable too — else a bareword
# `python coordinator/bin/publish.py` (the invocation docs + the /percolate skill now
# point at) dies with ModuleNotFoundError before argparse runs.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from percolate.allowlist import (  # noqa: E402
    AllowlistError,
    assert_allowlist_applied,
    build_allowlisted_source,
    check_working_data_paths,
    get_pre_filter_paths,
    parse_allowlist_csv,
    split_inclusion_exclusion,
)
from percolate.phase4_audit import PercolateIdentity, parse_percolate_identity  # noqa: E402
from percolate.targets import TargetsError, load_targets  # noqa: E402  (path setup must precede this import)


# ---------------------------------------------------------------------------
# Percolate-engine cutover (C-W2) — replaces the 14 legacy setup/percolate-hooks/
# *.sh hook scripts with direct in-process calls into the engine repo's
# coordinator_core.percolate engine (percolate_run.run_percolate + the separate
# engine.run_inject_for_section call). See docs/plans/2026-07-21-percolate-
# python-port.md chunk C-W2, finish-op-percolate-recipe.md §3 (option b2 — no
# bash trampolines).
#
# AC15 fail-closed contract (hard requirement, NOT optional): when the engine
# repo's engine is unreachable, unimportable, contract-unsatisfiable (undeclared
# target, schema/version skew), or raises for any other reason, this driver
# ABORTS — it never falls back to publishing a target's raw/unscrubbed content.
# `EngineUnavailableError` is the single exception type every fail-closed path
# below raises/catches; a caller seeing it must skip the affected work, never
# proceed best-effort.
# ---------------------------------------------------------------------------
class EngineUnavailableError(Exception):
    """Raised (and caught) on every AC15 fail-closed path: the engine repo's percolate
    engine could not be resolved/imported, the percolate store could not be
    loaded/validated, the store's declared `schema_version` does not match
    what this driver was authored against, or a target is not declared in the
    store's `targets` map. The caller's contract: on this exception, abort —
    never sync/publish the affected target."""


# The percolate-store schema_version this driver was authored against (matches
# `setup/percolate-hooks/percolate-store.yaml`'s own `schema_version: "1.0.0"`
# and the vendored schema's `x-schema-version` in the engine repo). Store.load_store's
# own built-in gate (schema_validate.validate_frontmatter Phase 0) only fails
# loud on a MAJOR-version skew (refuse-on-newer-read); this driver additionally
# asserts an EXACT match before dispatching any phase call, so a minor/patch
# drift this driver has not been verified against is caught too, not silently
# tolerated. Bump this constant (and re-verify the phase-call wiring below)
# when the store is deliberately upgraded.
_EXPECTED_STORE_SCHEMA_VERSION = "1.0.0"


@dataclass
class ClaudeKlabauterPercolate:
    """The subset of the engine repo's `coordinator_core.percolate` surface this driver
    calls, resolved once per run by `_import_claude_klabauter_percolate`. Threading a
    small resolved-callables bundle (rather than re-importing per target) keeps
    every phase-dispatch call site free of import/path-resolution concerns."""

    run_percolate: "Callable[..., dict]"
    load_store: "Callable[[Path], dict]"
    resolve_target: "Callable[[dict, str], dict]"
    run_inject_for_section: "Callable[..., None]"
    iter_surface_files: "Callable[..., object]"
    run_guards: "Callable[..., list]"
    run_identity_check: "Callable[[str], dict]"
    store_validation_error: type
    schema_version_error: type


def _import_claude_klabauter_percolate() -> ClaudeKlabauterPercolate:
    """Resolve CLAUDE_KLABAUTER_ROOT via the same `cc_invoke._resolve_claude_klabauter_root()` shim
    `percolate-preflight-scratch-publish.py` uses (§ module docstring), then
    import the engine repo's percolate-engine surface this driver dispatches against.

    Raises `EngineUnavailableError` — never returns partially — on: no
    `cc_invoke.py` resolvable on any of the 3 search rungs, an empty
    `_resolve_claude_klabauter_root()` result, or ANY exception importing the engine repo's
    modules (missing checkout, syntax error, ImportError, etc.). This is the
    AC15 engine-absent / import-failure fail-closed path.
    """
    cc_invoke_path = _locate_cc_invoke()
    if cc_invoke_path is None:
        raise EngineUnavailableError(
            "cc_invoke.py not found on any of the 3 search rungs — cannot resolve CLAUDE_KLABAUTER_ROOT"
        )

    try:
        spec = importlib.util.spec_from_file_location("_publish_cc_invoke_pct", cc_invoke_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not build a module spec for {cc_invoke_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise

        claude_klabauter_root = module._resolve_claude_klabauter_root()
        if not claude_klabauter_root:
            raise EngineUnavailableError("CLAUDE_KLABAUTER_ROOT resolution returned empty")
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)

        from coordinator_core.frontmatter.schema_validate import (  # type: ignore[import-not-found]
            SchemaVersionError as _SchemaVersionError,
        )
        from coordinator_core.ops.percolate_run import (  # type: ignore[import-not-found]
            run_percolate as _run_percolate,
        )
        from coordinator_core.ops.percolate_identity_check import (  # type: ignore[import-not-found]
            run_identity_check as _run_identity_check,
        )
        from coordinator_core.percolate import engine as _pct_engine  # type: ignore[import-not-found]
        from coordinator_core.percolate import guards as _pct_guards  # type: ignore[import-not-found]
        from coordinator_core.percolate import surface as _pct_surface  # type: ignore[import-not-found]
        from coordinator_core.percolate.store import (  # type: ignore[import-not-found]
            StoreValidationError as _StoreValidationError,
        )
        from coordinator_core.percolate.store import load_store as _load_store
        from coordinator_core.percolate.store import resolve_target as _resolve_target
    except EngineUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-closed catch-all, AC15
        raise EngineUnavailableError(f"claude-klabauter percolate engine import failed: {exc}") from exc

    return ClaudeKlabauterPercolate(
        run_percolate=_run_percolate,
        load_store=_load_store,
        resolve_target=_resolve_target,
        run_inject_for_section=_pct_engine.run_inject_for_section,
        iter_surface_files=_pct_surface.iter_surface_files,
        run_guards=_pct_guards.run_guards,
        run_identity_check=_run_identity_check,
        store_validation_error=_StoreValidationError,
        schema_version_error=_SchemaVersionError,
    )


def locate_percolate_store(setup_dir: Path) -> Path:
    """The production DoE percolate-store the engine repo's engine consumes for every
    target (§ `setup/percolate-hooks/percolate-store.yaml`'s own header)."""
    return setup_dir / "percolate-hooks" / "percolate-store.yaml"


def assert_percolate_store_ready(claude-klabauter: ClaudeKlabauterPercolate, store_path: Path) -> dict:
    """AC15 version/schema handshake — load+validate the store ONCE, before ANY
    phase call is dispatched for ANY target, and assert its declared
    `schema_version` is EXACTLY `_EXPECTED_STORE_SCHEMA_VERSION`.

    `claude-klabauter.load_store` already runs the engine repo's own built-in gates (JSON-Schema
    shape validation, the single-placeholder-per-codename / full-name-sibling /
    mixed-private-refusal / idempotency-self-check / basename-allowlist
    invariants, AND the `schema_validate.validate_frontmatter` Phase-0
    `schema_version` vs `x-schema-version` refuse-on-newer-read gate) — any
    failure there propagates as `StoreValidationError` or `SchemaVersionError`,
    both caught here. On top of that built-in gate (which only fails loud on a
    MAJOR-version skew), this function additionally asserts an EXACT
    `schema_version` match: a minor/patch drift this driver has not been
    verified against is refused too, not silently tolerated.

    Raises `EngineUnavailableError` (fail-closed, same handling as an
    unreachable engine — AC15) on a missing store file, a load/validation
    failure, or ANY schema_version skew. Returns the loaded+validated store
    dict on success.
    """
    if not store_path.is_file():
        raise EngineUnavailableError(f"percolate store not found at {store_path}")

    try:
        store = claude-klabauter.load_store(store_path)
    except Exception as exc:  # noqa: BLE001 - store/schema validation errors, fail-closed
        raise EngineUnavailableError(f"percolate store failed to load/validate: {exc}") from exc

    declared = store.get("schema_version")
    if declared != _EXPECTED_STORE_SCHEMA_VERSION:
        raise EngineUnavailableError(
            f"percolate store schema_version skew: store declares {declared!r}, this "
            f"driver was authored against {_EXPECTED_STORE_SCHEMA_VERSION!r} — refusing "
            "to dispatch any phase call (AC15 fail-closed, not best-effort)."
        )

    return store


@dataclass
class PercolateEngineContext:
    """Bundles the engine repo's percolate-engine surface + the loaded/validated
    store, resolved ONCE at driver startup (see `main`) and threaded into every
    `process_target` call. A `None` value (either field) means the engine was
    never made ready — callers must not dispatch phase calls in that case."""

    claude-klabauter: Optional[ClaudeKlabauterPercolate]
    store: Optional[dict]


def _assert_no_guard_failures(
    guard_results: List[dict],
    target_name: str,
    phase: str,
) -> None:
    """AC8: fail loud on any `guard_results[].ok == False` returned by a phase
    call. Raises `EngineUnavailableError` — same fail-closed handling as an
    unreachable engine (§ `process_target`'s catch), since a failed guard means
    this target's tree does not satisfy its own declared invariants and must
    not be published."""
    failures = [g for g in guard_results if not g.get("ok", False)]
    if not failures:
        return
    detail = "; ".join(f"{g.get('kind')}: {g.get('message')}" for g in failures)
    raise EngineUnavailableError(
        f"{target_name}: {len(failures)} guard(s) failed in phase {phase!r} — {detail}"
    )


_FILE_COUNT_DELTA_KIND = "file-count-delta"


def _compute_effective_source_count(
    claude-klabauter: ClaudeKlabauterPercolate,
    effective_source_dir: Path,
    section: dict,
) -> Optional[int]:
    """Count the EXPECTED side of the `file-count-delta` guard against the SOURCE
    tree, using the SAME PREDICATE the guard's OBSERVED side uses.

    "Same predicate" is the whole contract, and it is two things, both of which
    were previously false:

      1. The scoping params come off the `file-count-delta` GUARD ENTRY's own
         `params` — never the section's `file_surface`. `guards._walk_for_guard`
         reads the guard entry's params for `observed` (§ its docstring, and the
         store's own note on this entry: "`_walk_for_guard` reads scoping params
         off the guard ENTRY's own `params`, never the section's
         `file_surface`"), so an expected side derived from `file_surface`
         compares two different questions.
      2. The walk NARROWS to `include_extensions` (`_walk_for_guard` passes
         `narrow_to_include_extensions=True` unconditionally, deliberately —
         surface.py's 2026-08-05 admission-inversion is scoped to the engine's
         content-transform sweep, not to guard walks). Without narrowing,
         `surface.is_in_surface` admits everything not explicitly excluded, so
         the expected side counted non-`include_extensions` files the observed
         side never could — e.g. `.percolate-ignore`, which
         `coordinator/lib/percolate/allowlist.py::build_allowlisted_source`
         copies into the restricted staging tree unconditionally. That single
         dotfile was the standing `expected 28 (+/-0), got 27` failure on
         `coordinator-claude-toplevel-wiki`.

    This function therefore guarantees only what it can actually guarantee: the
    two sides of the delta ask the same question of two trees. It deliberately
    does NOT claim to mirror the engine's content-transform sweep — that claim
    is what was false, and the sweep's discovery call is un-narrowed by design.

    Returns `None` when `section` declares no `file-count-delta` guard entry: the
    count exists solely to feed that entry, and a section without one has nothing
    to feed. `None` propagates to `run_percolate(effective_source_count=...)`,
    which is already the "not supplied" value there. Same no-op-if-absent shape
    `dispatch_standalone_guards` uses for its own kind lookup — never a silent
    fallback to a differently-scoped count.
    """
    guard_params = _file_count_delta_guard_params(section)
    if guard_params is None:
        return None
    return sum(
        1
        for _ in claude-klabauter.iter_surface_files(
            effective_source_dir,
            include_extensions=guard_params.get("include_extensions"),
            shebang_prefixes=guard_params.get("shebang_prefixes"),
            exclude_prefixes=guard_params.get("exclude_prefixes"),
            exclude_basenames=guard_params.get("exclude_basenames"),
            exclude_globs=guard_params.get("exclude_globs"),
            narrow_to_include_extensions=True,
        )
    )


def _file_count_delta_guard_params(section: dict) -> Optional[dict]:
    """Return the `params` of `section`'s `file-count-delta` guard entry, or
    `None` if the section declares no such entry.

    A section may not declare the same guard `kind` twice with different scoping
    (there is one delta per row by construction), so the first match is the
    entry. Returns the entry's `params` verbatim — this driver never synthesises
    or defaults scoping params, because a param the driver invents is exactly the
    asymmetry `_compute_effective_source_count` exists to prevent.
    """
    for entry in section.get("guards") or []:
        if entry.get("kind") == _FILE_COUNT_DELTA_KIND:
            return entry.get("params") or {}
    return None


def dispatch_percolate_pre_rsync(
    engine_ctx: PercolateEngineContext,
    store_path: Path,
    target: "ResolvedTarget",
) -> None:
    """pre_rsync phase — MUST run while `target.dest_dir` still holds the PRIOR
    destination tree (preserve-destination-native BACKUP leg, § engine.py
    `run_pre_rsync`), i.e. before the driver's own sync dispatch runs. Raises
    `EngineUnavailableError` (AC15) on any engine failure — the caller must
    treat that as "abort this target, never publish".
    """
    assert engine_ctx.claude-klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    claude-klabauter = engine_ctx.claude-klabauter
    try:
        claude-klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    try:
        wire = claude-klabauter.run_percolate(str(store_path), target.name, str(target.dest_dir), phase="pre_rsync")
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        raise EngineUnavailableError(f"{target.name}: pre_rsync phase raised: {exc}") from exc

    _assert_no_guard_failures(wire.get("guard_results", []), target.name, "pre_rsync")


# ---------------------------------------------------------------------------
# Standalone Shape E guard dispatch (C-W3 item 7, recipe §3.5) — the 2 guard
# entries the retired setup/percolate-hooks/*.sh scripts ran OUTSIDE any
# percolate.run() phase call, because a phase call would silently check either
# the WRONG root or run at the WRONG TIME:
#
#   - coordinator-claude/pre-rsync/10-guard-no-game-dev.sh (recipe §2.3) — the
#     store's `source-dir-absent` entry for this target MUST check the SOURCE
#     tree (the game-dev/ plugin subtree must not exist in the SOURCE checkout
#     before publish), never target_root. Dispatching it via the normal
#     post_rsync/pre_ci phase call (which it still is — this entry stays in
#     the target's declared `guards:` list, § store.yaml comment) checks
#     target_root/game-dev instead — always vacuously absent post-sync, a
#     harmless-but-meaningless no-op, not the intended check.
#   - coordinator-claude-publish-repo-toplevel/pre-rsync/10-prune-stale-
#     handoff-cruft.sh (recipe §2.7) — the store's `prune-stale-paths` entry IS
#     target-root-correct even via the phase dispatch, but must run BEFORE the
#     sync overwrites the destination tree to match the retired hook's
#     pre-rsync timing (§ store.yaml comment: "Driver should still prefer a
#     standalone guards.run_guards() call before rsync runs").
#
# Both entries' CONTENT still lives in store YAML (recipe §3.5's "legitimate
# declarative migration... NOT a straight percolate.run(phase=...) trampoline
# call") — this dispatch only supplies the correct root/timing, filtering each
# target's already-resolved `guards:` list down to the one `kind` it owns
# rather than hand-authoring params here.
# ---------------------------------------------------------------------------
_STANDALONE_GUARD_DISPATCH: dict = {
    "coordinator-claude": {"kind": "source-dir-absent", "against": "source"},
    "coordinator-claude-publish-repo-toplevel": {"kind": "prune-stale-paths", "against": "dest"},
}


def dispatch_standalone_guards(
    engine_ctx: PercolateEngineContext,
    target: "ResolvedTarget",
    effective_source_dir: Path,
) -> None:
    """Run the ONE standalone-guard entry (if any) `target.name` owns, direct
    against `guards.run_guards` — never via a `percolate.run(phase=...)` call
    (§ module comment above `_STANDALONE_GUARD_DISPATCH`).

    A target absent from `_STANDALONE_GUARD_DISPATCH`, or whose resolved
    section has no `guards` entry of the owned `kind`, is a silent no-op —
    most targets have neither standalone hook. Raises `EngineUnavailableError`
    (AC15/AC8, the same fail-closed contract as every other
    `dispatch_percolate_*` function) on an undeclared target, an engine raise,
    or a failing guard result.
    """
    spec = _STANDALONE_GUARD_DISPATCH.get(target.name)
    if spec is None:
        return

    assert engine_ctx.claude-klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    claude-klabauter = engine_ctx.claude-klabauter
    try:
        section = claude-klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    guard_entries = [g for g in (section.get("guards") or []) if g.get("kind") == spec["kind"]]
    if not guard_entries:
        return

    check_root = effective_source_dir if spec["against"] == "source" else target.dest_dir

    try:
        results = claude-klabauter.run_guards(check_root, guard_entries)
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed
        raise EngineUnavailableError(
            f"{target.name}: standalone {spec['kind']!r} guard raised: {exc}"
        ) from exc

    guard_dicts = [
        {
            "kind": getattr(r, "kind", None),
            "ok": getattr(r, "ok", False),
            "message": getattr(r, "message", ""),
        }
        for r in results
    ]
    _assert_no_guard_failures(guard_dicts, target.name, "standalone")


def dispatch_percolate_post_rsync(
    engine_ctx: PercolateEngineContext,
    store_path: Path,
    target: "ResolvedTarget",
    effective_source_dir: Path,
    *,
    visited_sink: "Optional[set[Path]]" = None,
) -> Optional[dict]:
    """post_rsync phase — MUST run AFTER the driver's own sync dispatch (rsync
    equivalent) has completed: restore leg -> full content-transform sweep ->
    post_rsync guards (§ engine.py `run_post_rsync`). Computes
    `effective_source_count` from `effective_source_dir` (§
    `_compute_effective_source_count`) so the `file-count-delta` guard entry
    (coordinator-claude-toplevel-wiki) has what it needs without a store-
    declared `expected_count` fallback. A section declaring no such guard entry
    yields `None` there, forwarded unchanged as "not supplied".

    Returns the phase's `rename_manifest` (old->new dict, or `None`) — the
    caller MUST forward this unchanged into `dispatch_percolate_pre_ci` (§
    module docstring, rename-manifest reconciliation). Raises
    `EngineUnavailableError` (AC15) on any engine failure or guard failure
    (AC8) — the caller must treat that as "abort this target, never publish".

    `visited_sink` (optional, § `dispatch_end_of_run_unscanned_published_check`
    fix): when supplied, every repo-root-relative id in the phase wire's
    `visited_files` (§ `engine.PhaseResult.visited_files` / `percolate_run.
    _phase_result_to_wire`) is resolved to an absolute path under `target.dest_dir`
    and added to it — the real, executed-sweep visited set a caller accumulates
    across every row sharing a repo root, to assert against at end-of-run INSTEAD
    OF re-deriving eligibility via `iter_surface_files` at check time. `None` (the
    default) is a no-op, preserving every pre-existing call site's behavior.
    """
    assert engine_ctx.claude-klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    claude-klabauter = engine_ctx.claude-klabauter
    try:
        section = claude-klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    effective_source_count = _compute_effective_source_count(claude-klabauter, effective_source_dir, section)

    try:
        wire = claude-klabauter.run_percolate(
            str(store_path),
            target.name,
            str(target.dest_dir),
            phase="post_rsync",
            effective_source_count=effective_source_count,
            source_root=str(effective_source_dir),
        )
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        raise EngineUnavailableError(f"{target.name}: post_rsync phase raised: {exc}") from exc

    _assert_no_guard_failures(wire.get("guard_results", []), target.name, "post_rsync")
    if visited_sink is not None:
        for relative_id in wire.get("visited_files", []):
            visited_sink.add(target.dest_dir / relative_id)
    return wire.get("rename_manifest")


_COORDINATOR_CONTENT_ROOT_PLACEHOLDER = "<coordinator-content-root>"
_CLAUDE_KLABAUTER_CONTENT_ROOT_PLACEHOLDER = "<claude-klabauter-content-root>"


def _resolve_inject_src_placeholders(section: dict, percolate_root: Optional[Path]) -> dict:
    """Resolve the placeholder tokens every store-declared `inject[].src` uses
    (§ percolate-store.yaml's `coordinator-update` and `.persona-names-allowlist`
    entries; finish-op-percolate-recipe.md §2.2/§3.5) into absolute paths before
    dispatch. Two tokens, both resolved in this one pass:

      `<coordinator-content-root>` -> `percolate_root / "coordinator"` — DoE's
      resolved plugin-source root, because the actual absolute path varies by
      machine/layout (§ `resolve_percolate_root`) and store data cannot express
      that portably as a literal.

      `<claude-klabauter-content-root>` -> `_REPO_ROOT` — this repo's OWN root (this
      checkout, `Path(__file__).resolve().parents[2]`), for store entries naming
      content this repo itself homes (e.g. `dist/mirror-native/...`) rather than
      DoE's tree. Named to read as the direct sibling of `<coordinator-content-
      root>`: same "-content-root" suffix, the owning repo as the prefix.

    `run_inject`/`inject.py` itself never interprets either token — it only ever
    sees an already-resolved `src` — so resolution is driver plumbing, not an
    engine behavior.

    `percolate_root=None` (a caller that has not resolved one — e.g. a unit test
    exercising `dispatch_percolate_inject` directly) is a no-op: the section is
    returned unchanged, matching this function's prior absence (no placeholder
    resolution) for every existing caller that never threaded a root through.
    `<claude-klabauter-content-root>` resolves to a fixed, machine-independent path
    (`_REPO_ROOT` is derived from `__file__`, not from `percolate_root`), but
    stays behind this same gate so both tokens resolve together in one pass —
    a caller opting out of resolution opts out of all of it, not just DoE's half.

    Returns a NEW section dict with every inject entry's `src` resolved; does not
    mutate the caller's section (a resolved-target dict may be reused across the
    inject/post_rsync/pre_ci calls for the same target).
    """
    if percolate_root is None:
        return section
    inject_entries = section.get("inject") or []
    if not inject_entries:
        return section
    content_root = str(percolate_root / "coordinator")
    claude_klabauter_content_root = str(_REPO_ROOT)
    resolved_entries = []
    for entry in inject_entries:
        resolved_entry = dict(entry)
        src = resolved_entry.get("src", "")
        # The store declares each placeholder's continuation with POSIX
        # separators (`<coordinator-content-root>/dist/...`); a naive
        # string .replace() would splice that literal `/`-joined tail onto
        # an OS-native content root, producing a mixed-separator path on
        # Windows. Route through Path so the whole string comes out with
        # one consistent, OS-native separator.
        if _COORDINATOR_CONTENT_ROOT_PLACEHOLDER in src:
            src = str(Path(src.replace(_COORDINATOR_CONTENT_ROOT_PLACEHOLDER, content_root)))
        if _CLAUDE_KLABAUTER_CONTENT_ROOT_PLACEHOLDER in src:
            src = str(Path(src.replace(_CLAUDE_KLABAUTER_CONTENT_ROOT_PLACEHOLDER, claude_klabauter_content_root)))
        resolved_entry["src"] = src
        resolved_entries.append(resolved_entry)
    return {**section, "inject": resolved_entries}


def _materialize_inject_srcs(section: dict, percolate_root: Optional[Path]) -> dict:
    """Rewrites every inject entry's already-absolute `src` (§
    `_resolve_inject_src_placeholders`, which runs first) to point at its
    committed-ref shadow instead of the live working tree — docs/plans/
    2026-08-04-publish-from-a-committed-ref.md C4, AC6.

    `dispatch_percolate_inject` used to resolve `<claude-klabauter-content-root>` to
    `_REPO_ROOT` and stop there, so injected payload (today: 17 CI-harness
    files from `dist/mirror-native/claude-klabauter/.github`) bypassed
    `run_pre_sync_gates`' materialization entirely — the same class of hole
    C1/C1b closed for the un-allowlisted publish row, left open here.

    The covering unit is the materialized git TOPLEVEL (`_git_materialize_ref`),
    not the row's own contributing root: a naive "must resolve inside the
    row's contributing root, else fail" predicate REFUSES today's only real
    inject entry, since `dist/mirror-native/...` is not under
    `dist/klabauter-toplevel` (`claude-klabauter-publish-repo-toplevel`'s only
    contributing root). Instead, every non-exempt `src` is handed straight to
    `_git_materialize_ref`, which resolves *its own* containing git toplevel
    (materializing it on demand — memoized per `(toplevel, sha)` for the
    process lifetime, so this repo's own toplevel is almost always already
    cached from the row's own materialization) and returns the shadow path
    for that exact directory. `_git_materialize_ref` raises `GitMaterializeError`
    — never falls back to a live-tree copy — when `src` is in no git work
    tree at all; that is the only fail-loud condition here, not "outside the
    row's contributing root".

    `<coordinator-content-root>` is the one deliberate exemption: it resolves
    into `percolate_root / "coordinator"`, DoE's OWN separate checkout — a
    live tree this publish never owns and never materializes elsewhere
    (materializing a sibling repo's checkout from claude-klabauter's publish path would
    mean reading and gating on a tree claude-klabauter does not own, out of scope per
    the plan's "Out of scope" section). Entries whose resolved `src` sits
    inside that checkout are left exactly as `_resolve_inject_src_placeholders`
    produced them — live-tree-sourced, by stated policy, not by omission.

    `percolate_root=None` is the same no-op gate `_resolve_inject_src_placeholders`
    uses: a caller opting out of placeholder resolution (e.g. a unit test
    exercising `dispatch_percolate_inject` directly with no root) opts out of
    materialization too, since an unresolved `<placeholder>/...` string is not
    a real filesystem path to materialize.

    A resolved `src` that is neither absolute nor inside the DoE checkout —
    i.e. a relative, non-placeholder path — raises `GitMaterializeError`
    rather than falling through untouched (Review: code-reviewer Finding 4).
    AC6 requires injected content to be "materialized from the same ref...
    or the publish fails loud"; a bare `if src_path.is_absolute():` guard
    with no `else` left this shape neither materialized nor rejected. Not
    exercised by any store entry today (the one real inject entry resolves
    via `<claude-klabauter-content-root>`, always absolute), but the predicate must
    close this gap explicitly rather than leave it implicit.
    """
    if percolate_root is None:
        return section
    inject_entries = section.get("inject") or []
    if not inject_entries:
        return section
    doe_checkout_root = (percolate_root / "coordinator").resolve()
    resolved_entries = []
    for entry in inject_entries:
        resolved_entry = dict(entry)
        src = resolved_entry.get("src", "")
        src_path = Path(src)
        if src_path.is_absolute():
            resolved_src_path = src_path.resolve()
            is_doe_checkout = (
                resolved_src_path == doe_checkout_root
                or doe_checkout_root in resolved_src_path.parents
            )
            if not is_doe_checkout:
                # `_git_materialize_ref`/`_git_rev_parse` shell `git -C <root>`,
                # which requires a DIRECTORY — a file `src` (today's only real
                # entry, the vendored LICENSE) made `-C` fail and this raise
                # GitMaterializeError unconditionally, blocking every publish
                # of this row. Resolve the git root from the containing
                # directory for a file entry, then re-append the filename.
                git_root = src_path if resolved_src_path.is_dir() else src_path.parent
                shadow_root = _git_materialize_ref(git_root)
                shadow_path = (
                    shadow_root if resolved_src_path.is_dir() else shadow_root / src_path.name
                )
                if not shadow_path.exists():
                    # Review: code-reviewer Finding 3 — the file-case shadow
                    # path is only real when `src` was committed at the
                    # materialized ref; a staged/untracked/dirty-tree file
                    # produces a dangling path here that would otherwise
                    # surface as a bare FileNotFoundError deep inside
                    # run_inject_for_section, with no context tying it back
                    # to materialization. AC6's fail-loud contract applies.
                    raise GitMaterializeError(
                        f"materialized shadow path {shadow_path} for src "
                        f"{src!r} does not exist — src is not committed at "
                        "the materialized ref (staged, untracked, or the "
                        "working tree has diverged from HEAD)"
                    )
                resolved_entry["src"] = str(shadow_path)
        else:
            raise GitMaterializeError(
                f"inject entry src {src!r} is neither absolute nor a recognized "
                "placeholder — cannot materialize (AC6 fail-loud, not a silent "
                "live-tree passthrough)"
            )
        resolved_entries.append(resolved_entry)
    return {**section, "inject": resolved_entries}


def dispatch_percolate_inject(
    engine_ctx: PercolateEngineContext,
    target: "ResolvedTarget",
    percolate_root: Optional[Path] = None,
    *,
    visited_sink: "Optional[set[Path]]" = None,
) -> "tuple[Path, ...]":
    """The SEPARATE `run_inject_for_section` engine call (§ module docstring,
    STEP 2 — inject is NOT phase-wired). Runs AFTER `dispatch_percolate_post_rsync`
    (the content-transform sweep must not scrub freshly-injected files, and
    injected content must land before `dispatch_percolate_pre_ci`'s guards run
    — matches the retired bash hook ordering, `10-transform.sh` then
    `20-inject-oss-only-skills.sh`, both post-rsync). Passes an already-empty
    stdin (`io.StringIO("")`) — this driver is not itself sitting in the
    `--itemize-changes` pipe the retired bash hooks drained, so there is
    nothing to drain; `run_inject_for_section` unconditionally drains whatever
    stream it is given regardless of hook-set membership (§ engine.py
    docstring), so an empty stream is a correct, non-blocking no-op drain.

    `percolate_root`, when supplied (the production call site in `process_target`
    always supplies it), resolves the `<coordinator-content-root>` /
    `<claude-klabauter-content-root>` placeholders in every inject entry's `src`
    (§ `_resolve_inject_src_placeholders`), then rewrites every non-DoE-checkout
    `src` to its committed-ref shadow (§ `_materialize_inject_srcs`, C4/AC6) —
    inject sources from a committed ref exactly like every other publish row,
    or fails loud via `GitMaterializeError` rather than silently reading the
    live tree.

    Returns the shadow-tree TOPLEVELS `_materialize_inject_srcs` newly added
    to `_MATERIALIZED_REF_CACHE` during this call (Review: code-reviewer
    Finding 2) — a before/after diff of the cache taken around that one call,
    since `_materialize_inject_srcs` keeps its existing section-dict-only
    return contract (several unit tests exercise it directly). By the time
    this function runs, `run_pre_sync_gates` has already returned and
    `GateResult.shadow_roots` is fixed, so an inject-triggered shadow tree
    for a toplevel distinct from the target's own contributing roots would
    otherwise never be reachable to any cleanup sweep. The caller
    (`process_target`) folds this return into the SAME run-end sweep that
    reclaims `gate_result.shadow_roots` (Finding 3), rather than cleaning up
    locally here.

    On a `run_inject_for_section` raise, the newly-materialized toplevels
    (already on disk by then) are attached to the re-raised
    `EngineUnavailableError` as `.materialized_shadow_roots`, so the caller's
    `except` clause can still fold them into its cleanup accounting even
    though this function's normal return value is never reached.

    `visited_sink` (optional, § `dispatch_end_of_run_unscanned_published_check`
    fix): forwarded straight through to `engine.run_inject_for_section` as its own
    `visited_sink` — this call is an in-process Python call (not the JSON-RPC
    `percolate.run` op `dispatch_percolate_post_rsync` goes through), so the same
    mutable `set[Path]` object can be shared directly with no wire round-trip. A
    caller threads the SAME set here and into `dispatch_percolate_post_rsync` for
    this row so the two legs' visited files land in one combined set. `None` (the
    default) is a no-op.

    Raises `EngineUnavailableError` (AC15) on any engine failure.
    """
    assert engine_ctx.claude-klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    claude-klabauter = engine_ctx.claude-klabauter
    try:
        section = claude-klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    section = _resolve_inject_src_placeholders(section, percolate_root)
    _cache_before = set(_MATERIALIZED_REF_CACHE.values())
    section = _materialize_inject_srcs(section, percolate_root)
    newly_materialized = tuple(
        shadow for shadow in _MATERIALIZED_REF_CACHE.values() if shadow not in _cache_before
    )

    try:
        claude-klabauter.run_inject_for_section(
            target.dest_dir, section, stdin=io.StringIO(""), visited_sink=visited_sink
        )
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        wrapped = EngineUnavailableError(f"{target.name}: inject raised: {exc}")
        wrapped.materialized_shadow_roots = newly_materialized  # type: ignore[attr-defined]
        raise wrapped from exc

    return newly_materialized


def dispatch_percolate_pre_ci(
    engine_ctx: PercolateEngineContext,
    store_path: Path,
    target: "ResolvedTarget",
    effective_source_dir: Path,
    rename_manifest: Optional[dict],
    *,
    identity_dest_dir: Optional[Path] = None,
) -> None:
    """pre_ci phase — final class-(b) guard/assert checks (§ engine.py
    `run_pre_ci`), run LAST, after `dispatch_percolate_inject` has landed any
    injected content. Forwards `rename_manifest` captured from
    `dispatch_percolate_post_rsync` unchanged (§ module docstring,
    rename-manifest reconciliation — a pre-ci guard enumerating files is just
    as vulnerable to a stale pre-rename path as a post-rsync guard). Raises
    `EngineUnavailableError` (AC15) on any engine failure or guard failure
    (AC8) — the caller must treat that as "abort this target, never publish".

    Also runs `<dest repo root>/.github/scripts/check-persona-names.py` (the
    mirror's own release-CI identity checker,
    `percolate_identity_check.run_identity_check`) here, after the phase's own
    `run_percolate` guards, and folds a failure into the SAME
    `_assert_no_guard_failures` list those guards populate rather than raising
    through a second, out-of-band channel — one design call, made deliberately:
    a target that fails EITHER the phase guards or the identity check aborts
    through the identical `EngineUnavailableError` path, so there is exactly
    ONE way a target aborts pre_ci, not two independently-catchable ones a
    future caller could accidentally handle differently. This is what closes
    the root cause this op exists for: the publish-side guard
    (`percolate_run.py::_registry_alternation_pattern`) derives its vocabulary
    from machine-local registry-repo slugs and is blind to a bare codename by
    construction, so running the mirror's own checker is what actually asks
    the question the mirror's release CI asks.

    The checker is resolved against the DESTINATION REPO ROOT
    (`_dest_repo_root(target.dest_dir)`), not `target.dest_dir` itself: for a
    row whose `dest_subdir` is non-empty (e.g. row 1 of the klabauter mirror,
    `dest_dir = <repo>/coordinator_core`), `.github/scripts/` only ever lands
    at the repo root, published by a SEPARATE toplevel row. Anchoring on
    `dest_dir` made every such row's identity check resolve to a path the
    checker could never occupy, so `run_identity_check` returned
    `skipped=True` every time and the guard-failure append (gated on `ran`)
    never fired — a structural blind spot, not a fluke (root-caused in
    `state/audits/2026-08-05-klabauter-scrub-and-gate-both-silent.md` § Q3).
    When no `.git` ancestor is found at all, this falls back to
    `target.dest_dir` unchanged (matches `_ensure_dest_ready`'s own fallback
    behaviour) and the skip warning below names that explicitly.

    `identity_dest_dir` (default `None`, meaning "use `target.dest_dir`"): the
    REAL destination path to anchor this check against, distinct from
    `target.dest_dir` when the caller is running this phase against a staged
    tree (§ `process_target`'s guard-before-mutate staging fix). The identity
    checker inspects a SIBLING toplevel row's already-published
    `.github/scripts/check-persona-names.py` at the real destination repo
    root — content this row's own staging never touches or owns — so this
    check is correct against the real tree regardless of whether the
    row-owned guard checks above ran staged or not; anchoring it at a
    throwaway staging path instead would make `_dest_repo_root` walk up from
    a directory outside any real repo and spuriously report `skipped=True`.

    A `skipped=True` result is no longer allowed to read as clean: it is
    always printed to stderr, loud, naming the path that was checked and
    why the row was skipped. It stays ADVISORY (does not fail the guard)
    because a legitimate ordering exists where this fires cleanly: a row
    with a non-empty `dest_subdir` can run before its sibling toplevel row
    has ever published `.github/` to a virgin destination, and the checker
    genuinely does not exist yet. Making it a hard failure would block that
    ordering permanently rather than the one publish where it is actually
    missing. What is NOT acceptable, and what this fix removes, is that skip
    being invisible — the whole failure class here was "a gate reporting
    nothing and being read as clean" (module docstring's root-cause note).
    """
    assert engine_ctx.claude-klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    claude-klabauter = engine_ctx.claude-klabauter
    try:
        section = claude-klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    effective_source_count = _compute_effective_source_count(claude-klabauter, effective_source_dir, section)

    try:
        wire = claude-klabauter.run_percolate(
            str(store_path),
            target.name,
            str(target.dest_dir),
            phase="pre_ci",
            effective_source_count=effective_source_count,
            rename_manifest=rename_manifest,
            source_root=str(effective_source_dir),
        )
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        raise EngineUnavailableError(f"{target.name}: pre_ci phase raised: {exc}") from exc

    guard_results = list(wire.get("guard_results", []))

    real_dest_dir = identity_dest_dir if identity_dest_dir is not None else target.dest_dir
    identity_dest = _dest_repo_root(real_dest_dir)
    if identity_dest is None:
        identity_dest = real_dest_dir
        identity_dest_note = f"{identity_dest} (no .git ancestor found; used dest_dir as-is)"
    else:
        identity_dest_note = str(identity_dest)

    try:
        identity_result = claude-klabauter.run_identity_check(str(identity_dest))
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
        raise EngineUnavailableError(f"{target.name}: identity check raised: {exc}") from exc

    if identity_result["skipped"]:
        print(
            f"  WARNING: {target.name}: identity checker not found at "
            f"{identity_dest_note}/.github/scripts/check-persona-names.py — "
            f"pre_ci identity gate SKIPPED for this row (advisory: the "
            f"toplevel row may not have published .github/ to this "
            f"destination yet).",
            file=sys.stderr,
        )

    if identity_result["ran"] and identity_result["exit_code"] != 0:
        guard_results.append(
            {
                "ok": False,
                "kind": "identity_check",
                "message": (
                    f"check-persona-names.py exited {identity_result['exit_code']} — "
                    f"{identity_result['findings'].strip()}"
                ),
            }
        )

    _assert_no_guard_failures(guard_results, target.name, "pre_ci")


def dispatch_end_of_run_identity_check(
    engine_ctx: PercolateEngineContext,
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
    out: IO[str] = sys.stdout,
) -> bool:
    """Run `<repo root>/.github/scripts/check-persona-names.py` ONCE per
    distinct destination repo root touched by this `main()` invocation,
    after every row has synced — the fail-closed backstop the per-row
    `dispatch_percolate_pre_ci` check cannot be, by construction.

    Why the per-row leg alone is insufficient: `setup/publish-targets
    .portable` declares the `claude-klabauter` engine row (`dest_subdir`
    non-empty, the row that ships nearly the entire tree the checker scans)
    BEFORE `claude-klabauter-publish-repo-toplevel` (`dest_subdir` empty,
    the only row that ever publishes `.github/`). `main()` processes rows
    in declaration order, so on a full run into a wiped/virgin destination
    the engine row's own per-row check runs FIRST, finds no checker yet,
    and — correctly, per that function's own advisory-skip reasoning —
    does not fail the row. Nothing in the per-row path ever goes back and
    re-checks the engine row's payload once `.github/` DOES land later in
    the same run. That gap is exactly the failure this leg closes: a real
    release procedure ("prove the whole payload once, into a wiped
    destination, across every row") could complete green with the checker
    having never run against the row that matters most. The checker itself
    walks the WHOLE destination tree in one pass (not per-row content), so
    one run per repo root, AFTER every row has synced, covers every row's
    published bytes at once.

    Severity, deliberately asymmetric with the per-row leg:
      * `skipped=True` (checker not found) is FAIL-CLOSED on an unfiltered
        run (`target_filtered=False`) — by the time every declared row has
        synced, either the toplevel row published `.github/`, or this
        invocation had no business being called complete. Advisory here
        would silently reproduce the exact bug being fixed.
      * `skipped=True` under `target_filtered=True` (a `--target`-scoped
        single-row debug publish) stays ADVISORY (loud WARNING, no
        failure): `main()` skips every non-matching row (`if args.target
        and target.name != args.target: continue`), so a single-target
        invocation may legitimately never reach the toplevel row and never
        place `.github/` at all — that is not evidence of anything broken,
        it is evidence of what was asked for.
      * A nonzero exit code is a HARD failure UNCONDITIONALLY, filtered or
        not: if the checker ran, it already scanned real destination
        content and found a real finding. A `--target` scope narrows
        whether the checker was expected to exist; it never excuses acting
        on a finding it actually produced. This is what keeps a filtered
        debug publish from being "unfailable" per the task brief.

    Returns True iff every repo root passed (or was advisory-skipped);
    False iff any repo root hard-failed. Never raises `EngineUnavailableError`
    itself — the caller (`main()`) turns a False return into a nonzero
    process exit, since by this point in the run there is no single target
    left to attribute a fail-closed abort to; the failure is run-wide.

    Never called under `--dry-run` (see `main()`'s call site) — dry-run
    never mutates a destination, so there is nothing new for this leg to
    have found since the last real publish; firing it would report on
    stale, pre-existing destination state as if this run had produced it.
    """
    assert engine_ctx.claude-klabauter is not None  # narrowed by caller (never called under dry-run)
    claude-klabauter = engine_ctx.claude-klabauter
    ok = True
    for repo_root in repo_roots:
        try:
            identity_result = claude-klabauter.run_identity_check(str(repo_root))
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run identity check raised for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        if identity_result["skipped"]:
            if target_filtered:
                print(
                    f"  WARNING: end-of-run identity checker not found at "
                    f"{repo_root}/.github/scripts/check-persona-names.py — "
                    f"advisory under --target (this invocation may never have "
                    f"published .github/ to this destination).",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  Error: end-of-run identity check FAILED for {repo_root}: "
                    f"checker not found at .github/scripts/check-persona-names.py "
                    f"after a full, unfiltered run — .github/ was never published "
                    f"to this destination this run (or a prior one).",
                    file=sys.stderr,
                )
                ok = False
            continue

        if identity_result["exit_code"] != 0:
            print(
                f"  Error: end-of-run identity check FAILED for {repo_root}: "
                f"check-persona-names.py exited {identity_result['exit_code']} — "
                f"{identity_result['findings'].strip()}",
                file=sys.stderr,
            )
            ok = False

    return ok


_INSTALL_DOC_PAYLOAD_CHECK_PATH = Path(__file__).resolve().parent / "check-install-doc-payload.py"


def _import_check_install_doc_payload():
    """Import `check-install-doc-payload.py` (sibling in this directory) —
    `spec_from_file_location`, matching the ad hoc idiom
    `_import_publish_sync` falls back to for a module with no package
    context to resolve against. Unlike `publish_sync.py`, this module has no
    relative imports of its own (stdlib + dataclasses/argparse/re only), so
    there is no `percolate`-package rung to prefer — this ad hoc path is the
    only one it ever needs."""
    spec = importlib.util.spec_from_file_location(
        "check_install_doc_payload", _INSTALL_DOC_PAYLOAD_CHECK_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build a module spec for {_INSTALL_DOC_PAYLOAD_CHECK_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Basenames of the CHANGELOG document class — the one class where a reference to
# a since-retired path is CORRECT rather than stale (§
# `_install_doc_paths_for_repo_root`). Matched case-insensitively against the
# basename; deliberately an exact-name set, not a substring/prefix test, so a doc
# merely mentioning "changelog" in its name is never silently dropped.
_CHANGELOG_DOC_BASENAMES = frozenset(
    {
        "changelog.md",
        "changes.md",
        "history.md",
        "release-notes.md",
        "releases.md",
    }
)


def _install_doc_paths_for_repo_root(module, repo_root: Path) -> "List[Path]":
    """Return the EXPLICIT install-doc set `check_tree` should scan under
    `repo_root` — every top-level `.md` the published tree actually ships,
    MINUS the changelog class.

    Why an explicit set at all: `check-install-doc-payload.py`'s
    `DEFAULT_DOC_GLOB = "*.md"` sweeps every top-level `.md`, and a full run
    against the real payload returned 71 findings — 69 in `CHANGELOG.md`, 2 in
    `CONTRIBUTING.md`, and ZERO in any install doc. The gate was reporting almost
    entirely on a document class it has no business gating.

    Why the CHANGELOG class specifically, and ONLY it: a changelog is the one
    document class in which a reference to a since-retired filename is CORRECT.
    An entry reading "`bin/cruft-sweep.sh` (mechanical) + ..." was TRUE of the
    release it describes; the file's later retirement does not falsify the
    historical record, and "fixing" such an entry to point at today's path
    rewrites history into something that never shipped. De-linkifying them to
    silence the checker is worse still — it degrades published prose to appease a
    gate (DoE tried exactly that and reverted it). An install doc says "here is
    how to install"; a changelog says "here is how we used to install", and only
    the former is a claim about the tree as published.

    Everything else the tree ships is KEPT, including the policy docs that
    currently return zero findings — the set is "all shipped top-level `.md`
    minus one named class", never a hand-maintained allowlist. Two reasons: the
    two published mirrors do not ship the same doc set (only one has an
    `INSTALL.md`), so an allowlist would need per-repo knowledge and would go
    stale the moment a doc is added; and an allowlist silently drops any doc
    class nobody remembered to list, which is the failure mode of the gate this
    replaces, one file over.

    `CONTRIBUTING.md` is deliberately IN the set despite being the other doc
    named in the 71: it carries real install-relevant payload and this gate has
    already caught a GENUINE stale pointer in it (`lib/install-substrate.sh`,
    retired to `install-substrate.py`). It documents how to run the tree as it
    is NOW, not as it once was — the changelog argument does not reach it.

    Negative-spec: do NOT "helpfully" widen this back to a bare `*.md` glob or to
    `--recursive`. The narrowing is the fix, and its whole content is the one
    named exclusion above.
    """
    return [
        doc
        for doc in module.find_doc_files(repo_root)
        if doc.name.lower() not in _CHANGELOG_DOC_BASENAMES
    ]


def dispatch_end_of_run_install_doc_payload_check(
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
    out: IO[str] = sys.stdout,
) -> bool:
    """Run `check_install_doc_payload.check_tree()` ONCE per distinct
    destination repo root touched by this `main()` invocation, after every
    row has synced — END-OF-RUN ONLY, deliberately never per-row.

    The doc set is passed EXPLICITLY (§ `_install_doc_paths_for_repo_root`),
    never left to the checker's `DEFAULT_DOC_GLOB = "*.md"`: that default swept
    the changelog, the one document class in which a reference to a since-
    retired path is correct rather than stale, and produced 69 of a full run's
    71 findings from it.

    Why not per-row (and why not "both"): `check-install-doc-payload.py`'s
    own author found, running it live against `dist/klabauter-toplevel`,
    that `CONTRIBUTING.md` references `.github/scripts/run-all-checks.py`,
    a file that ships from the SIBLING toplevel row, not the row whose
    tree they were checking (see that module's docstring "WIRING" section
    and its sidecar,
    state/subagent-share/e4ae702d-32fa-4954-96d0-63fcfe810f9b/
    coordinatorexecutor-cad6ccb4.md). A per-row call sees only that row's
    slice of the destination mid-run — before every sibling row has synced
    — so it cannot distinguish a real broken doc reference from a
    reference that is merely satisfied by a row that hasn't run yet. Unlike
    the identity checker (whose "not found yet" case at least has an
    explicit `skipped` signal to make advisory), `check_tree()` has no such
    signal: a finding just IS a finding, so a per-row call would either
    have to swallow every cross-row reference as always-advisory (which
    defeats the gate — it would never fail anything) or produce exactly
    the false positives observed live. End-of-run, after every declared
    row has synced, sees the FULLY ASSEMBLED tree the doc's reader will
    actually get — the question this gate exists to ask only has a
    stable answer at that point.

    Severity mirrors `dispatch_end_of_run_identity_check`'s split for the
    same reason: `main()` skips every row not matching `--target`
    (`if args.target and target.name != args.target: continue`), so a
    single-target debug publish may never place a sibling row's file a doc
    references — that is not evidence of a broken doc, it is evidence of a
    partial publish. Findings are therefore ADVISORY (loud WARNING, no
    failure) under `target_filtered=True`, and a HARD failure on an
    unfiltered run, where every row was supposed to have synced.

    Returns True iff every repo root came back clean (or was
    advisory-warned); False iff any repo root hard-failed. Never raises —
    same reporting contract as `dispatch_end_of_run_identity_check`, and
    never called under `--dry-run` for the same reason (see that
    function's docstring; `main()`'s dry-run early return covers both
    end-of-run legs identically).
    """
    try:
        module = _import_check_install_doc_payload()
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed: unimportable gate
        print(
            f"  Error: end-of-run install-doc payload check unavailable "
            f"(could not import check-install-doc-payload.py): {exc}",
            file=sys.stderr,
        )
        return False

    ok = True
    for repo_root in repo_roots:
        try:
            findings = module.check_tree(
                repo_root,
                doc_paths=_install_doc_paths_for_repo_root(module, repo_root),
            )
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run install-doc payload check raised for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        if not findings:
            continue

        rendered = "\n".join(f"    {finding.render(repo_root)}" for finding in findings)
        if target_filtered:
            print(
                f"  WARNING: end-of-run install-doc payload check found "
                f"{len(findings)} unresolved reference(s) under {repo_root} — "
                f"advisory under --target (this invocation may not have "
                f"published every row a doc references):\n{rendered}",
                file=sys.stderr,
            )
        else:
            print(
                f"  Error: end-of-run install-doc payload check FAILED for "
                f"{repo_root}: {len(findings)} install-doc command(s) reference "
                f"a path absent from the published tree:\n{rendered}",
                file=sys.stderr,
            )
            ok = False

    return ok


_UNSCANNED_EXCEPTIONS_PATH = Path(__file__).resolve().parent / "percolate-published-unscanned-exceptions.yaml"
# `.git` is destination-repo plumbing, never touched by any row's sync —
# a STRUCTURAL exclusion from dispatch_end_of_run_unscanned_published_check's
# "published" set, not a ratified content exception. See that function's own
# docstring for the full rationale.
_STRUCTURAL_NEVER_PUBLISHED_PREFIX = ".git"


def _load_unscanned_exceptions() -> dict:
    """Load the deliberate-exclusion list for
    `dispatch_end_of_run_unscanned_published_check` from
    `percolate-published-unscanned-exceptions.yaml` (this directory) —
    NEVER `setup/percolate-hooks/percolate-store.yaml`, a deliberately
    separate, harness-owned file (see that YAML's own header comment for
    why). Returns `{relative_posix_path: reason}`; an absent file or an
    empty `exceptions:` list is "no exclusion ratified yet," not an error —
    every unscanned-but-published file is a hard failure until a human adds
    an entry.

    Raises ValueError if any entry is missing `path` or `reason` — an
    exclusion with no stated reason is exactly the "looks identical to an
    accident" shape this mechanism exists to close, so it is refused at
    load time rather than silently accepted.
    """
    if not _UNSCANNED_EXCEPTIONS_PATH.is_file():
        return {}
    import yaml

    with _UNSCANNED_EXCEPTIONS_PATH.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    entries = raw.get("exceptions") or []
    result: dict = {}
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        reason = entry.get("reason") if isinstance(entry, dict) else None
        if not path or not reason:
            raise ValueError(
                f"{_UNSCANNED_EXCEPTIONS_PATH}: entry {entry!r} is missing 'path' or "
                f"'reason' — every deliberate exclusion must state why, or it is "
                f"indistinguishable from an accidental one."
            )
        result[path] = reason
    return result


def _import_percolate_surface_module():
    """Import `coordinator_core.percolate.surface` — by the time this is
    called, `_import_claude_klabauter_percolate()` has already resolved CLAUDE_KLABAUTER_ROOT
    onto `sys.path`, so this is a plain import, not a second
    spec_from_file_location dance. Kept as its own function (rather than a
    bare inline import at the call site) so the import failure path has one
    named place to raise from, matching this file's other `_import_*`
    helpers."""
    import coordinator_core.percolate.surface as _surface_module

    return _surface_module


def _import_percolate_rewrite_basename_module():
    """Import `coordinator_core.percolate.rewrite_basename` — same idiom as
    `_import_percolate_surface_module` (CLAUDE_KLABAUTER_ROOT is already on
    `sys.path` by the time this is called). Needed by `process_target` to
    read a mirror-mode row's rename-generation ledger BEFORE dispatching
    sync, so a directory this pass's rename is about to reproduce can be
    exempted from `sync_mirror`'s orphan-deletion (§ that function's own
    `renamed_dir_names` docstring; state/audits/2026-08-05-first-full-
    payload-identity-findings.md Group E)."""
    import coordinator_core.percolate.rewrite_basename as _rewrite_basename_module

    return _rewrite_basename_module


def _classify_unscanned_reason(
    surface_module,
    repo_root: Path,
    path: Path,
    file_surface_params: dict,
    *,
    real_sweep_mode: bool = False,
) -> str:
    """Explain, in one line, why `path` (published, under `repo_root`) was
    not visited by ANY row's `iter_surface_files` call — replicates
    `is_in_surface`'s own precedence order (symlink -> exclude-prefix ->
    exclude-basename/glob -> content-detected-binary -> [narrowing, only
    when a row opts in] include-extension/shebang;
    `coordinator_core/percolate/surface.py`, ADMISSION-INVERTED 2026-08-05)
    against the LAST (widest-reaching, typically the toplevel row's)
    `file_surface_params` checked for this repo root, so the reported
    reason is a real decision the engine actually made for at least one
    row, not a guess. Multiple rows can have DIFFERENT `file_surface`
    params for the same repo root; this reports one concrete, correct
    reason, not an exhaustive per-row breakdown — the finding itself (§
    caller) already names every row's own scanned set was unioned before
    reaching this classifier, so "unscanned" here already means "no row's
    params include it," and this function only needs to produce ONE true
    reason, not all of them.

    Post-inversion, extension/shebang mismatch is reachable ONLY when a row
    opted into `narrow_to_include_extensions: true` — the pre-inversion
    behavior, now opt-in. No store row sets that key as of this writing, so
    that branch is dormant today, not dead: kept correct for the row that
    eventually does opt in, rather than deleted and silently wrong later.

    `real_sweep_mode` (§ caller — set from `visited_files_by_repo_root is not
    None`): when the caller's `scanned` set is the REAL executed-sweep record
    (§ `dispatch_end_of_run_unscanned_published_check` docstring) rather than
    re-derived eligibility, a file reaching one of the two catch-all branches
    below did NOT fail an `iter_surface_files` re-derivation — eligibility was
    never computed for it — it failed the real "did the sweep actually visit
    this" test despite looking admission-open. That is a genuine reproduction
    of the leak `visited_files` exists to catch (or a real sweep bug), not
    evidence this classifier's own eligibility logic is out of step with
    `iter_surface_files`; the message says so.
    """
    include_extensions = file_surface_params.get("include_extensions") or []
    shebang_prefixes = file_surface_params.get("shebang_prefixes") or []
    exclude_prefixes = file_surface_params.get("exclude_prefixes") or []
    exclude_basenames = file_surface_params.get("exclude_basenames") or []
    exclude_globs = file_surface_params.get("exclude_globs") or []
    narrow = bool(file_surface_params.get("narrow_to_include_extensions"))

    if path.is_symlink():
        return "symlink (never in-surface)"

    relative_path = path.relative_to(repo_root).as_posix()
    if surface_module.matches_exclude_prefix(relative_path, exclude_prefixes):
        return f"path segment matches an exclude_prefixes entry {exclude_prefixes!r}"
    if surface_module.matches_exclude_basename(path, exclude_basenames, exclude_globs):
        return "basename matches an exclude_basenames/exclude_globs entry"
    if surface_module.is_probably_binary(path):
        return "content-detected binary (NUL byte in first chunk)"
    if not narrow:
        if real_sweep_mode:
            return (
                "admission is default-open (narrow_to_include_extensions not set) "
                "and no exclusion matched, so this file was eligible to be swept "
                "but the real content-transform sweep never actually visited it "
                "— investigate why (a row that skipped this file, a sweep error "
                "swallowed upstream, or a genuine unscanned-published-guard leak)"
            )
        return (
            "UNEXPECTED: admission is default-open (narrow_to_include_extensions "
            "not set) and no exclusion matched, so this file should have been "
            "in-surface — investigate directly, this classifier's own logic may "
            "be out of step with iter_surface_files"
        )
    if surface_module.has_include_extension(path, include_extensions):
        if real_sweep_mode:
            return (
                "matches include_extensions and was eligible to be swept, but "
                "the real content-transform sweep never actually visited it — "
                "investigate why (a row that skipped this file, a sweep error "
                "swallowed upstream, or a genuine unscanned-published-guard leak)"
            )
        return (
            "UNEXPECTED: matches include_extensions but no row's scanned set "
            "included it (investigate directly — this classifier's own logic "
            "may be out of step with iter_surface_files)"
        )
    if path.suffix == "":
        return (
            f"narrow_to_include_extensions is set for this row, and this file has "
            f"no matching extension and no recognized shebang first line "
            f"(shebang_prefixes: {shebang_prefixes!r})"
        )
    return (
        f"narrow_to_include_extensions is set for this row, and this file has no "
        f"matching extension (include_extensions: {include_extensions!r})"
    )


def dispatch_end_of_run_unscanned_published_check(
    row_sections: "List[tuple]",
    *,
    target_filtered: bool,
    visited_files_by_repo_root: "Optional[dict[Path, set[Path]]]" = None,
    published_dest_dirs_by_repo_root: "Optional[dict[Path, set[Path]]]" = None,
    out: IO[str] = sys.stdout,
) -> bool:
    """Assert **the set of files published equals the set of files the
    content-transform sweep actually visited** — the structural gap
    underneath Group A of
    state/audits/2026-08-05-first-full-payload-identity-findings.md (and,
    per that audit's own framing, the fourth instance this week of "a check
    validating its own table while the real thing goes unexamined": the
    installer row, the identity-gate directory trap, inject's merge-not-
    mirror copy, and now the surface selector silently excluding files the
    publish allowlist happily ships).

    Run ONCE per distinct destination repo root (§ `dispatch_end_of_run_
    identity_check`'s and `dispatch_end_of_run_install_doc_payload_check`'s
    same shape), after every row has synced. For each repo root:
      1. `published` — § `published_dest_dirs_by_repo_root` below
         (unscanned-published-guard FALSE-POSITIVE fix, cross-repo/inbox
         "the check fires on a file this invocation never published"
         follow-on): when the caller supplies it, `published` is every file
         under one of `published_dest_dirs_by_repo_root.get(repo_root,
         set())` right now — the dest_dirs THIS RUN actually swapped (§
         `process_target`'s `published_dest_dirs_sink`, populated only after
         the row's staged content has been verified and swapped into the
         real destination) — never the whole repo root. A file elsewhere
         under the repo root (shipped by a prior publish, excluded by
         `--target`, or belonging to a row this run skipped via a failed
         pre-sync gate) was not published BY THIS RUN and is therefore out of
         scope for its verdict; comparing it against `scanned` (which only
         ever records what THIS run's sweep visited, never a prior run's)
         produced exactly this false positive. When the caller omits
         `published_dest_dirs_by_repo_root` (`None`, e.g. every pre-existing
         test in `test_unscanned_published_gate.py`), `published` falls back
         to every file that actually exists under the repo root right now
         (the pre-fix ground truth) — the production call site (`main`)
         always supplies it; the fallback exists purely for back-compat with
         callers/tests that never run a real staged sync over their
         fixtures.
      2. `scanned` — § `visited_files_by_repo_root` below (unscanned-published-
         guard-hole fix, cross-repo/inbox "the store is ours and inject bypasses
         the sweep" follow-on): when the caller supplies it, `scanned` is
         `visited_files_by_repo_root.get(repo_root, set())` — the REAL set of
         files this run's `post_rsync` content-transform sweep and inject scrub
         actually read successfully (§ `engine.PhaseResult.visited_files`,
         `engine.run_inject_for_section`'s own `visited_sink`), unioned across
         every row sharing this repo root. This is a HARD requirement of the
         fix: re-deriving eligibility via `iter_surface_files(row.dest_dir,
         **row's file_surface)` AT CHECK TIME (the pre-fix behavior, still the
         fallback below) cannot distinguish a file the sweep actually visited
         from one that merely happens to satisfy the same eligibility params
         NOW — e.g. a file `inject` copied AFTER the sweep already finished
         walking the tree, which would re-derive as "eligible" and pass clean
         despite never having been scrubbed by anything. When the caller omits
         `visited_files_by_repo_root` (`None`, e.g. every pre-existing test in
         `test_unscanned_published_gate.py`, which asserts the ELIGIBILITY
         logic itself with no real sweep run over its fixtures), `scanned`
         falls back to the pre-fix UNION, across every row (`ResolvedTarget`,
         resolved `section`) whose destination resolves to this repo root, of
         `iter_surface_files(row.dest_dir, **row's file_surface)` — a row's
         dest_dir can be the repo root itself (a toplevel row) or a
         subdirectory of it (§ `_dest_repo_root`), and DIFFERENT rows can
         declare DIFFERENT `file_surface` params for overlapping trees;
         unioning is deliberate there too — a file is fine if AT LEAST ONE
         applicable row's sweep would visit it, matching "is this file ever
         transformed by anything," not "does every row's own narrower config
         individually cover it." The production call site (`main`) always
         supplies `visited_files_by_repo_root`; the fallback exists purely for
         back-compat with callers/tests exercising eligibility in isolation.
      3. `unscanned = published - scanned`. Each entry is a HARD failure
         UNLESS its repo-root-relative path is a key in
         `_load_unscanned_exceptions()` — in which case it is still
         PRINTED (never silently absorbed into a clean pass — a deliberate
         exclusion is a visible decision, not a silence) but does not fail
         the run.

    Unlike `dispatch_end_of_run_identity_check`/
    `..._install_doc_payload_check`, this check does NOT degrade to
    advisory under `--target`: each finding is evaluated against a single
    row's own dest tree and that row's own (unioned) scanned set — there is
    no cross-row "the sibling row hasn't published yet" dependency for this
    property to legitimately be incomplete about, so `target_filtered` is
    accepted for signature symmetry with the other two legs but does not
    change severity here (documented explicitly rather than silently
    ignored).

    Returns True iff every repo root's unscanned set is either empty or
    fully covered by ratified exceptions; False otherwise. Never raises for
    a missing/malformed exceptions file at the "no entries" case — only a
    malformed ENTRY (present but missing `path`/`reason`) raises, via
    `_load_unscanned_exceptions`, and that propagates here as an
    unavailable-check failure (fail-closed, matching the other two legs'
    unimportable-checker handling) rather than being swallowed.

    `_STRUCTURAL_NEVER_PUBLISHED_PREFIX` (`.git`) is excluded from the
    `published` set at the mechanism level, not via the ratified-exceptions
    list: `.git/` is the destination repo's own pre-existing git plumbing —
    no row's sync ever copies INTO or deletes FROM it (verified:
    `coordinator/lib/percolate/publish_sync.py` contains zero `.git`
    references; its `sync_mirror`/`sync_flat_mirror` walks are scoped to
    named source-derived subtrees that never include it) — yet a toplevel
    row's `dest_dir` being the repo root means `iter_surface_files`'s raw
    `os.walk` DOES descend into it, and every `.git/*` entry (`HEAD`,
    `config`, `hooks/*.sample`, ...) correctly never matches any
    `include_extensions`/`shebang_prefixes`, so it is real, reproducible
    "unscanned." First confirmed live: this leg's first run against the
    real payload (via `percolate-full-payload-proof.py`) reported ~20 such
    entries before this exclusion was added. Treating `.git/*` as a
    "deliberate exclusion" via the ratified-exceptions file would require
    one entry per git-internal filename forever (and more on every git
    version bump) — the two-tables-rot shape this whole workstream is
    closing, not an instance of it to add to. `.git` is structural, not a
    content decision, so it is excluded here, not ratified there.
    """
    try:
        surface_module = _import_percolate_surface_module()
        exceptions = _load_unscanned_exceptions()
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed: unavailable check
        print(
            f"  Error: end-of-run unscanned-published check unavailable: {exc}",
            file=sys.stderr,
        )
        return False

    by_repo_root: "dict[Path, list[tuple]]" = {}
    for target, section in row_sections:
        repo_root = _dest_repo_root(target.dest_dir) or target.dest_dir
        by_repo_root.setdefault(repo_root, []).append((target, section))

    ok = True
    for repo_root, entries in by_repo_root.items():
        if not repo_root.is_dir():
            continue

        scanned: "set[Path]" = set()
        widest_params: dict = {}
        for target, section in entries:
            if not target.dest_dir.is_dir():
                continue
            file_surface_params = section.get("file_surface") or {}
            if visited_files_by_repo_root is None:
                # Back-compat fallback (§ docstring) — re-derives eligibility,
                # the pre-fix behavior. Never taken by the production call site.
                scanned.update(surface_module.iter_surface_files(target.dest_dir, **file_surface_params))
            if len(file_surface_params.get("include_extensions") or []) >= len(
                widest_params.get("include_extensions") or []
            ):
                widest_params = file_surface_params

        if visited_files_by_repo_root is not None:
            # The fix: assert against what this run ACTUALLY visited, never
            # against what a file merely happens to be ELIGIBLE for now (§
            # docstring) — no re-derivation, no merge with the eligibility set
            # computed above (that would silently reopen the same hole).
            scanned = set(visited_files_by_repo_root.get(repo_root, set()))

        if published_dest_dirs_by_repo_root is not None:
            # The false-positive fix: scope `published` to what THIS RUN
            # actually swapped, never the whole repo root (§ docstring) — a
            # dest_dir this run never swapped contributes nothing, so a file
            # that only lives elsewhere under the repo root cannot appear
            # here regardless of whether `scanned` covers it.
            published = {
                p
                for dest_dir in published_dest_dirs_by_repo_root.get(repo_root, set())
                for p in dest_dir.rglob("*")
                if p.is_file() and _STRUCTURAL_NEVER_PUBLISHED_PREFIX not in p.relative_to(repo_root).parts
            }
        else:
            published = {
                p
                for p in repo_root.rglob("*")
                if p.is_file() and _STRUCTURAL_NEVER_PUBLISHED_PREFIX not in p.relative_to(repo_root).parts
            }
        unscanned = sorted(published - scanned)
        if not unscanned:
            continue

        hard_failures = []
        for path in unscanned:
            relative_path = path.relative_to(repo_root).as_posix()
            if relative_path in exceptions:
                print(
                    f"  NOTE: {relative_path} is published but unscanned — "
                    f"DELIBERATE exclusion (ratified reason: "
                    f"{exceptions[relative_path]}).",
                    file=sys.stderr,
                )
                continue
            reason = _classify_unscanned_reason(
                surface_module,
                repo_root,
                path,
                widest_params,
                real_sweep_mode=visited_files_by_repo_root is not None,
            )
            print(
                f"  Error: end-of-run unscanned-published check FAILED for {repo_root}: "
                f"{relative_path} is published but was never visited by any row's "
                f"content-transform sweep — {reason}.",
                file=sys.stderr,
            )
            hard_failures.append(relative_path)

        if hard_failures:
            ok = False

    return ok


# ---------------------------------------------------------------------------
# PERCOLATE_ROOT resolution — see module docstring.
# ---------------------------------------------------------------------------
def _read_doe_root_pointer() -> str:
    """Cold-read the `.doe-root` pointer, durable-first (DR-071/DR-072).

    Read order:
      1. `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/machine-local/.doe-root`
      2. `${CLAUDE_HOME:-$HOME}/.claude/.doe-root`  (legacy fallback)

    Returns "" when neither is present/readable — every caller here already
    treats empty as "this rung did not resolve" and falls through.

    Kept as a local cold-read rather than importing
    `coordinator_core.doe_root_pointer`: this is a pointer-file rung used while
    LOCATING the engine repo checkout, so it must not depend on having located it.
    The durable rung was added 2026-07-28 when the generator stopped writing the
    legacy target (which lives in the cross-machine-synced `~/.claude` tree).
    """
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or str(Path.home()), ".coordinator-claude-settings"
    )
    claude_home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    for candidate in (
        Path(settings_home) / "machine-local" / ".doe-root",
        Path(claude_home) / ".claude" / ".doe-root",
    ):
        try:
            content = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if content:
            return content
    return ""


def _locate_cc_invoke() -> Optional[Path]:
    """3-rung search for `cc_invoke.py`, mirroring `setup/publish.sh`.

    Rung 1: `$CLAUDE_PLUGIN_ROOT/bin/lib/cc_invoke.py`.
    Rung 2: the sibling `lib/cc_invoke.py` next to THIS file — publish.py
      already lives at `coordinator/bin/publish.py`, exactly where the bash
      original's rung-2 `$SCRIPT_DIR/../bin/lib/cc_invoke.py` was reaching
      for, so the lookup collapses to a direct sibling read here.
    Rung 3: the `.doe-root` pointer file's `coordinator/bin/lib/cc_invoke.py`,
      read durable-first (see `_read_doe_root_pointer`).

    Returns None if no rung resolves (bash's silent `_cc_invoke_py=""` state).
    """
    env_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_plugin_root:
        candidate = Path(env_plugin_root) / "bin" / "lib" / "cc_invoke.py"
        if candidate.is_file():
            return candidate

    sibling = Path(__file__).resolve().parent / "lib" / "cc_invoke.py"
    if sibling.is_file():
        return sibling

    doe_root = _read_doe_root_pointer()
    if doe_root:
        candidate = Path(doe_root) / "coordinator" / "bin" / "lib" / "cc_invoke.py"
        if candidate.is_file():
            return candidate

    return None


def resolve_percolate_root(*, err: IO[str] = sys.stderr) -> Path:
    """Thin wrapper over `_resolve_percolate_root_and_rung` preserving the
    original Path-only contract for external callers. `main()` calls the
    rung-returning sibling directly instead, so the rung it threads into the
    AC15 FATAL messages is the one that actually produced this root — see
    that function's docstring (Finding 2, code-reviewer)."""
    root, _rung_label = _resolve_percolate_root_and_rung(err=err)
    return root


def _resolve_percolate_root_and_rung(*, err: IO[str] = sys.stderr) -> "tuple[Path, str]":
    """Native in-process port of `setup/publish.sh`'s PERCOLATE_ROOT
    resolution. Calls the SAME underlying resolver
    (`cc_invoke._resolve_claude_klabauter_root` -> `coordinator_core.percolate.
    runtime_root.coordinator_percolate_runtime_root`) the bash original
    invoked via a `python3 -c` subprocess — here it is a direct in-process
    call since this driver is already Python.

    Fallback order on ANY native-resolver failure (missing cc_invoke.py,
    unresolvable CLAUDE_KLABAUTER_ROOT, missing coordinator_core.percolate.runtime_root
    module, or an exception raised by it):
      1. Native resolver (above) — preferred, resolves the true percolation
         source root. Post-C1/C4, this is the ONLY correctness mechanism in
         the ordinary case: `coordinator_percolate_runtime_root()` itself now
         consults the registry-first `.doe-root` pointer rung ahead of the
         shared-install rung, so a correct DoE-clone answer is already
         produced here on every normal run.
      2. This function's OWN `.doe-root` pointer read (`_read_doe_root_pointer()`),
         validated by the presence of `setup/publish-targets.portable` at the
         pointed-to root. This is a cold-start backstop for genuine
         native-resolver failure (missing cc_invoke, unresolvable
         CLAUDE_KLABAUTER_ROOT) — a case rung 1's in-process pointer rung structurally
         cannot cover, because this local read runs while LOCATING the engine
         root and so cannot depend on having already located it. It is not, and
         post-C1/C4 no longer reads as, the primary correctness mechanism —
         it only fires when rung 1 has already failed outright.
      3. This repo's own root (`_REPO_ROOT`), with a non-fatal degrade
         warning — `_REPO_ROOT` is this repo's own root and is KNOWN-WRONG for
         locating `setup/` post-b644d5a9 (publish.py relocated into this repo's
         tree, out of the percolation source tree); rung 2 exists precisely
         to give a correct answer before falling back to this known-wrong
         last resort.

    Open question (not this chunk): whether rung 2's local
    `_read_doe_root_pointer()` read should later converge onto the shared
    `coordinator_core.doe_root_pointer` module is left for a future chunk.
    """
    cc_invoke_path = _locate_cc_invoke()
    failure_reason: Optional[str] = None
    root: Optional[str] = None

    if cc_invoke_path is None:
        failure_reason = "cc_invoke.py not found on any of the 3 search rungs"
    else:
        try:
            spec = importlib.util.spec_from_file_location("_publish_cc_invoke", cc_invoke_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"could not build a module spec for {cc_invoke_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(spec.name, None)
                raise

            claude_klabauter_root = module._resolve_claude_klabauter_root()
            if claude_klabauter_root and claude_klabauter_root not in sys.path:
                sys.path.insert(0, claude_klabauter_root)

            from coordinator_core.percolate.runtime_root import (  # type: ignore[import-not-found]
                coordinator_percolate_runtime_root,
            )

            root = coordinator_percolate_runtime_root()
            if not root:
                failure_reason = "coordinator_percolate_runtime_root() returned empty"
        except Exception as exc:  # noqa: BLE001 - catch-all matches the bash `except Exception` -c snippet
            failure_reason = str(exc)

    if root:
        return Path(root), "native"

    doe_root = _read_doe_root_pointer()
    if doe_root and (Path(doe_root) / "setup" / "publish-targets.portable").is_file():
        print(
            f"publish.py: coordinator_percolate_runtime_root (native) failed ({failure_reason}); "
            f"using .doe-root pointer PERCOLATE_ROOT={doe_root}",
            file=err,
        )
        return Path(doe_root), "doe-root-pointer-cold-start"

    print(
        f"publish.py: coordinator_percolate_runtime_root (native) failed ({failure_reason}); "
        f"falling back to repo-root guess PERCOLATE_ROOT={_REPO_ROOT} — verify this is correct",
        file=err,
    )
    return _REPO_ROOT, "repo-root-guess"


def _claude_klabauter_coordinator_bin() -> Optional[Path]:
    """Best-effort `<CLAUDE_KLABAUTER_ROOT>/coordinator/bin`, or None if unresolvable.

    Uses the same `cc_invoke._resolve_claude_klabauter_root()` seam as
    `_import_claude_klabauter_percolate`, so it honours the registry/pointer resolution
    chain rather than guessing a sibling-directory layout. Deliberately
    swallows every failure: this backs an optional lookup rung, and an
    unresolvable CLAUDE_KLABAUTER_ROOT should degrade to the caller's own diagnostic
    rather than crash target resolution.
    """
    try:
        cc_invoke_path = _locate_cc_invoke()
        if cc_invoke_path is None:
            return None
        spec = importlib.util.spec_from_file_location(
            "_publish_cc_invoke_binroot", cc_invoke_path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)
        claude_klabauter_root = module._resolve_claude_klabauter_root()
        if not claude_klabauter_root:
            return None
        return Path(claude_klabauter_root) / "coordinator" / "bin"
    except Exception:
        return None


def coordinator_bin_default(percolate_root: Path) -> Path:
    """Port of `setup/publish.sh`'s COORDINATOR_BIN_DEFAULT — picks
    whichever of `<root>/coordinator/bin` (flat meta-repo layout) or
    `<root>/bin` (live-install layout) actually contains
    `check-version-consistency.py`. Not consumed by this chunk (the
    version-consistency gate is C-W1d2's), but resolved here so that gate has
    a ready value to land against."""
    candidate = percolate_root / "coordinator" / "bin"
    if (candidate / "check-version-consistency.py").is_file():
        return candidate

    # Engine-repo rung. The executable surface — including this gate — migrated out
    # of the DoE clone into the engine repo, so on a maximalist install NEITHER
    # percolate-root layout below holds the script: the DoE clone tracks no
    # files under `coordinator/bin` at all. Without this rung the gate resolves
    # to a non-existent path and publish skips every target with
    # "version-consistency gate not found", which reads as a broken install
    # rather than a stale lookup path.
    #
    # Resolved through the same CLAUDE_KLABAUTER_ROOT seam the rest of this module uses, so it
    # honours the registry/pointer chain rather than assuming a sibling-directory
    # layout.
    claude_klabauter_bin = _claude_klabauter_coordinator_bin()
    if claude_klabauter_bin is not None and (claude_klabauter_bin / "check-version-consistency.py").is_file():
        return claude_klabauter_bin

    return percolate_root / "bin"


# ---------------------------------------------------------------------------
# Resolved-target row parsing
# ---------------------------------------------------------------------------
@dataclass
class ResolvedTarget:
    """One row from `targets.load_targets`, parsed into fields — port of the
    bash main loop's `IFS='|' read -r name mode SOURCE_DIR path native_slugs
    allowlist <<< "$target_entry"` (setup/publish.sh)."""

    name: str
    mode: str
    source_dir: Path
    dest_dir: Path
    native_slugs: str = ""
    allowlist: str = ""
    source_map: str = ""


def parse_target_row(row: str) -> ResolvedTarget:
    """Parse one resolved
    `name|mode|ABSsource|ABSdest[|native_slugs[|allowlist[|source_map]]]` row.
    Fields beyond index 3 are indexed, not greedily joined — an unexpected 8th+
    field is simply left unread rather than silently absorbed into
    `allowlist` (as a bash `read` degrade once did), which used to fail
    downstream as a confusing bogus-allowlist-entry error far from its cause."""
    fields = row.split("|")
    if len(fields) < 4:
        raise TargetsError(
            f"publish.py: malformed resolved target row (expected >=4 fields, got {len(fields)}): {row}",
            2,
        )
    name, mode, source, dest = fields[0], fields[1], fields[2], fields[3]
    native_slugs = fields[4] if len(fields) > 4 else ""
    allowlist = fields[5] if len(fields) > 5 else ""
    source_map = fields[6] if len(fields) > 6 else ""
    return ResolvedTarget(
        name=name,
        mode=mode,
        source_dir=Path(source),
        dest_dir=Path(dest),
        native_slugs=native_slugs,
        allowlist=allowlist,
        source_map=source_map,
    )


def _parse_source_map(raw: str) -> "dict[str, Path]":
    """Parse a resolved `source_map` field — `<abs_root>=<csv_of_entries>`
    segments joined by `;` — into an allowlist-entry -> contributing-root
    dict, the shape `build_allowlisted_source`/`assert_allowlist_applied`
    consume. Empty input yields an empty dict (single-source, per the fixed
    contract's `source_map is None/empty => SINGLE-SOURCE` clause)."""
    result: "dict[str, Path]" = {}
    if not raw:
        return result
    for segment in raw.split(";"):
        if not segment:
            continue
        root_str, sep, csv = segment.partition("=")
        if not sep or not root_str or not csv:
            raise TargetsError(
                f"publish.py: malformed source_map segment '{segment}' in resolved target row",
                2,
            )
        root_path = Path(root_str)
        for entry in csv.split(","):
            entry = entry.strip()
            if entry:
                result[entry] = root_path
    return result


def _contributing_roots(target: ResolvedTarget) -> List[Path]:
    """Primary `source_dir` plus every distinct root named in
    `target.source_map`, deduplicated and sorted (by string form) for
    deterministic gate ordering — see §3 (the four other gates)."""
    roots = {target.source_dir}
    roots.update(_parse_source_map(target.source_map).values())
    return sorted(roots, key=str)


# ---------------------------------------------------------------------------
# Publish-relevant path set (DR-227) — the path set `check_dirty_tree` is
# narrowed to, wired into `run_pre_sync_gates`'s per-root dirty-tree loop
# below. See docs/plans/2026-08-03-narrow-check-dirty-tree-to-publish-
# relevant-paths.md ("The hazard this plan must resolve first") and
# docs/decisions/DR-227-whole-tree-dirty-classifier-redundant-under-explicit-
# path-scoping.md.
# ---------------------------------------------------------------------------
_RAW_SOURCE_GATE_PATHS = (
    "marketplace.json",
    ".claude-plugin/marketplace.json",
    "plugin.json",
    "CHANGELOG.md",
)


def _git_ls_tree_entry_files(root: Path, entry: str, ref: str = "HEAD") -> "set[str]":
    """Returns the set of root-relative paths `git -C <root> ls-tree -r
    --name-only <ref> -- <entry>` reports tracked at `ref` beneath `entry` —
    the git-history half of `_publish_relevant_allowlist_leg`'s per-entry
    expansion (docs/plans/2026-08-04-publish-from-a-committed-ref.md C7a2,
    EM decision 2). Returns the empty set on any failure (root not a git
    work tree, `ref` unresolved, `git` missing) — this call is supplementary
    coverage for the dirty-tree pathspec, not an authoritative source, so a
    failure here must never block or narrow what the live-filesystem half
    already found; a `git status` pathspec entry that matches nothing is
    harmless (state/lessons/2026-07-05-git-stash-push-pathspec-silently-
    no-ops.yaml)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "--name-only", ref, "--", entry],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    if result.returncode != 0:
        return set()
    return {line for line in result.stdout.splitlines() if line}


def _publish_relevant_allowlist_leg(target: ResolvedTarget) -> "dict[Path, list[str]]":
    """Per-contributing-root allowlist-derived slice of the publish-relevant
    path set (DR-227) — plan Deliverable 1's rule (b)-i, factored out on its
    own so the AC9 anti-drift test can compare THIS leg — and nothing
    else — against `build_allowlisted_source`'s actual output.

    Consumes `target.allowlist` via the SAME parse primitives
    `build_allowlisted_source` uses (`parse_allowlist_csv` +
    `split_inclusion_exclusion`, the public aliases `allowlist.py` exports
    for this cross-module consumer), never a second hand-rolled parse — see the
    plan's Anti-scope ("do not let the set be computed twice, differently")
    and AC9. `!`-prefixed exclusion entries are never fed to git as a
    literal path named `!...` (AC1); instead, any already-admitted relative
    path they name (or that nests under them) is subtracted from the
    surviving inclusion-derived set, mirroring `_apply_exclusions`'
    narrows-only removal so this leg matches what `build_allowlisted_source`
    actually leaves on disk (AC9), never a superset that includes
    since-excluded content.

    Each surviving inclusion entry is resolved to its contributing root via
    `_parse_source_map(target.source_map)` (absent -> `target.source_dir`,
    the single-source default), then EXPANDED against BOTH that root's real
    filesystem tree AND `git ls-tree -r --name-only HEAD` scoped to the
    entry (`_git_ls_tree_entry_files`), UNIONED — never either alone (DR-227
    AC9 anti-drift knot, docs/plans/2026-08-04-publish-from-a-committed-
    ref.md C7a2, EM decision 2, resolved as BOTH directions together, not
    one): a directory entry becomes every file beneath it (root-relative),
    a file entry becomes itself, and an entry absent from disk is kept
    UNRESOLVED (the literal entry string, unexpanded) rather than dropped
    silently — a `git status` pathspec that matches nothing is harmless
    (state/lessons/2026-07-05-git-stash-push-pathspec-silently-no-ops.yaml);
    dropping the check outright would not be. The live-filesystem-only leg
    this function computed pre-C7a2 diverges from what actually publishes
    (post-C1a/C1b, from a committed ref) in BOTH directions: an untracked
    worktree file is in the live leg but can never publish, and a file
    present at `HEAD` but deleted in the worktree DOES publish yet was
    absent from a live-only leg (its loss would never nudge the dirty-tree
    gate). Unioning the two sources makes this leg a guaranteed SUPERSET of
    anything publishable — see `_publish_relevant_paths`'s docstring — which
    is what a nudge needs; it is deliberately never narrowed back to an
    exact match, so `TestPublishRelevantPathsAntiDrift`'s invariant is
    CONTAINMENT (this leg superset-of `build_allowlisted_source`'s actual
    output), not equality.

    Returns `{}` when `target.allowlist` is falsy — the caller,
    `_publish_relevant_paths`, applies rule (a)'s whole-dir default in that
    case; this function only ever computes the allowlist leg. A
    contributing root with NO surviving inclusion entry (every entry
    resolved elsewhere, or all were exclusions) is simply ABSENT from the
    returned dict — never present with an empty list — so callers can tell
    "no allowlist leg for this root" apart from "an allowlist leg that
    happens to be empty" by a plain `.get(root)` truthiness check.

    Invariant this leg's per-root exclusion matching relies on (Review:
    code-reviewer — exclusion targets are matched against every root's
    `rels` independently, without root-scoping the target itself): every
    contributing root's admitted entries occupy a disjoint relative-path
    namespace, enforced downstream by `_collision_preflight` (called inside
    `build_allowlisted_source`, which runs AFTER this gate) — a real
    cross-root collision aborts the actual publish at build time regardless
    of what this gate computed.

    NOTE: this function is consumed ONLY by the AC9 anti-drift test now —
    the pathspec actually handed to `git status`, AND the rule-(c)
    empty-leg fallback detection in `_publish_relevant_paths`, are both
    computed at DIRECTORY granularity by
    `_publish_relevant_allowlist_leg_dirspec` instead (see that function's
    docstring for why), never by walking this leg's per-file output into a
    git argv.
    """
    result: "dict[Path, list[str]]" = {}
    if not target.allowlist:
        return result

    entries, exclusion_targets = split_inclusion_exclusion(parse_allowlist_csv(target.allowlist))
    source_map = _parse_source_map(target.source_map)

    per_root: "dict[Path, set[str]]" = {}
    for entry in entries:
        root = source_map.get(entry, target.source_dir)
        entry_path = root / entry
        rels: "set[str]" = set()
        if entry_path.is_dir():
            for f in entry_path.rglob("*"):
                if f.is_file():
                    rels.add(f.relative_to(root).as_posix())
        elif entry_path.is_file():
            rels.add(entry)
        else:
            rels.add(entry)  # unresolved — see docstring
        rels.update(_git_ls_tree_entry_files(root, entry))  # git-history half — see docstring
        per_root.setdefault(root, set()).update(rels)

    if exclusion_targets:
        for rels in per_root.values():
            removed = {
                r
                for r in rels
                if any(r == t or r.startswith(t + "/") for t in exclusion_targets)
            }
            rels.difference_update(removed)

    for root, rels in per_root.items():
        if rels:
            result[root] = sorted(f":(literal){r}" for r in rels)

    return result


def _publish_relevant_allowlist_leg_dirspec(target: ResolvedTarget) -> "dict[Path, list[str]]":
    """DIRECTORY-granularity sibling of `_publish_relevant_allowlist_leg`,
    used to build the pathspec actually handed to `git status` (Review:
    code-reviewer Finding 1 — the file-level `rglob` expansion in
    `_publish_relevant_allowlist_leg` risks an unbounded `git status --
    :(literal)f1 :(literal)f2 ...` argv for a directory allowlist entry with
    many files, a real Windows argv-length hazard with no override escape).

    A git pathspec naming a directory (`:(literal)<entry>`) already matches
    every path beneath it in `git status` output WITHOUT a filesystem walk
    or one arg per file (this does NOT hold for a SYMLINKED directory entry —
    a pathspec naming a symlink matches the symlink itself, not a walk of its
    target; no shipping allowlist row uses one today, so this is named but
    unaddressed — Review: code-reviewer Finding 4) — so this leg is bounded
    in size by the number of allowlist entries, never by files on disk, while
    covering the exact same (or a WIDER) set of paths as the file-level leg.
    It deliberately
    does NOT replicate `_publish_relevant_allowlist_leg`'s per-file
    exclusion subtraction: an exclusion entry nested under an admitted
    directory entry is left uncovered-by-subtraction here, so the emitted
    pathspec covers files an exclusion entry removes from the PUBLISHED
    set too. That is the gate inspecting MORE than what is actually
    published — the fail-closed direction, exactly like `.percolate-ignore`
    never being subtracted (see `_publish_relevant_allowlist_leg`'s
    docstring) — and a later reader must not "tighten" this back down to
    per-file exclusion subtraction; that is what reintroduces the argv
    hazard this function exists to avoid. An entry that exactly matches a
    whole-entry exclusion (`!<entry>` naming that entry verbatim) IS
    dropped — nothing from it is ever published, so omitting it costs no
    coverage.

    Returns `{}` when `target.allowlist` is falsy, and omits a root with no
    surviving entry (never an empty list) — same contract as
    `_publish_relevant_allowlist_leg`.

    Invariant this function's whole-entry exclusion matching relies on, same
    as its sibling `_publish_relevant_allowlist_leg` (Review: code-reviewer
    Finding 3 — this invariant was documented only on that sibling's
    docstring, not here, though this function trusts it identically):
    `exclusion_set` is matched against `entry` with no root-scoping, which is
    only sound because every contributing root's admitted entries occupy a
    disjoint relative-path namespace, enforced downstream by
    `_collision_preflight` (called inside `build_allowlisted_source`, which
    runs AFTER this gate) — a real cross-root collision aborts the actual
    publish at build time regardless of what this gate computed.
    """
    result: "dict[Path, list[str]]" = {}
    if not target.allowlist:
        return result

    entries, exclusion_targets = split_inclusion_exclusion(parse_allowlist_csv(target.allowlist))
    source_map = _parse_source_map(target.source_map)
    exclusion_set = set(exclusion_targets)

    per_root: "dict[Path, set[str]]" = {}
    for entry in entries:
        if entry in exclusion_set:
            continue
        root = source_map.get(entry, target.source_dir)
        per_root.setdefault(root, set()).add(entry)

    for root, ents in per_root.items():
        if ents:
            result[root] = sorted(f":(literal){e}" for e in ents)

    return result


def _publish_relevant_paths(
    target: ResolvedTarget, roots: "Optional[List[Path]]" = None
) -> "dict[Path, list[str]]":
    """The publish-relevant path set for `target`, as a PER-CONTRIBUTING-ROOT
    MAPPING (`dict[Path, list[str]]`, keyed by contributing root, values
    root-relative `git status` pathspecs) — plan Deliverable 1, DR-227
    (`docs/decisions/DR-227-whole-tree-dirty-classifier-redundant-under-
    explicit-path-scoping.md`). NOT a flat set: a flat set handed to a
    per-root `check_dirty_tree` loop feeds root B's paths to `git -C rootA`,
    which exits non-zero and (via `_git_status_porcelain`'s pre-C1 swallow)
    reads as clean — the exact fail-open hazard this plan exists to close
    (see the plan's "The hazard this plan must resolve first" section).

    Composition, per contributing root (`_contributing_roots(target)`):

      (a) `target.allowlist` falsy -> every root's slice is the bare
          whole-subtree form (`["."]`) — the same scope `check_dirty_tree`
          uses today. No narrowing is legitimate when the publish reads the
          whole root.
      (b) Otherwise, per root, the UNION of:
            - the allowlist leg, at DIRECTORY granularity
              (`_publish_relevant_allowlist_leg_dirspec` — see its docstring
              for why this is directory-, not file-, granular);
            - `.percolate-ignore` for that root, unconditionally — read at
              allowlist-BUILD time regardless of whether it is itself
              allowlisted, and NEVER subtracted even when it matches an
              ignore rule — fail-closed per AC5/AC1;
            - for `target.source_dir` ONLY, `_RAW_SOURCE_GATE_PATHS` — kept
              in this leg for `check_dirty_tree`'s own diagnostic purpose
              (AC4: "uncommitted ≠ unpublishable, but it IS unshipped").
              `check_marketplace_version_regression` / `check_version_consistency`
              no longer read raw `target.source_dir` directly (docs/plans/
              2026-08-04-publish-from-a-committed-ref.md C1b relocated them
              to run against the materialized shadow tree, AFTER this dirty
              check) — but an uncommitted edit to one of these paths is
              still exactly the kind of "you will ship the last commit's
              bytes, not what's on disk" surprise this dirty-check pathspec
              exists to flag, so the paths stay in the leg regardless of
              which tree the version gates themselves read.
          Every emitted pathspec carries the `:(literal)` magic prefix so a
          `*`/`?`/`[`-bearing entry cannot be glob-interpreted by git.
      (c) A root whose ALLOWLIST LEG comes out empty (no inclusion entry
          resolves to it, or every entry for it was an exclusion) falls
          back to that root's whole-subtree `["."]` form INSTEAD of the (b)
          union — fail-closed on a degenerate set, per DR-227. Never an
          empty list: a `git status` with no pathspec after `--` inspects
          nothing and reads as clean.

    Deterministic (sorted) ordering within each root's slice (rule (d)).

    `roots`, when supplied (Review: code-reviewer Finding 6 — the EM
    dispositioned this as "thread it through" over "compute it twice and
    trust it stays in sync"), is used AS-IS instead of recomputing
    `_contributing_roots(target)` — the production call site
    (`run_pre_sync_gates`) already needs the same roots list for its own
    per-root loop and threads it here so the mapping's keys and that loop's
    iteration cannot diverge by construction. Omitted (the default), this
    computes `_contributing_roots(target)` itself — every existing direct
    caller (tests) keeps working unchanged.
    """
    if roots is None:
        roots = _contributing_roots(target)

    if not target.allowlist:
        return {root: ["."] for root in roots}

    allowlist_leg = _publish_relevant_allowlist_leg_dirspec(target)

    result: "dict[Path, list[str]]" = {}
    for root in roots:
        leg = allowlist_leg.get(root)
        if not leg:
            result[root] = ["."]
            continue

        slice_paths = set(leg)
        slice_paths.add(":(literal).percolate-ignore")
        if root == target.source_dir:
            slice_paths.update(f":(literal){p}" for p in _RAW_SOURCE_GATE_PATHS)
        result[root] = sorted(slice_paths)

    return result


# ---------------------------------------------------------------------------
# Identity-file owner+mode pre-source check — port of
# `setup/publish.sh` (SEC: secaudit MEDIUM :46-51). Runs ONCE at
# driver startup (see `main`), matching the bash original sourcing
# `.percolate-identity` once before the target loop — NOT per-target.
# ---------------------------------------------------------------------------
class IdentityFileUnsafeError(Exception):
    """Raised when `.percolate-identity` fails the owner/mode security gate.
    Mirrors the bash original's `exit 1` — fatal to the WHOLE run, not a
    per-target skip (there is no per-target `continue` for this one)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class IdentityFileMissingError(Exception):
    """Raised when `setup/.percolate-identity` is absent entirely (distinct
    from `IdentityFileUnsafeError`, which fires when the file IS present but
    fails the owner/mode gate). Mirrors that error's abort shape — fatal to
    the WHOLE run, not a per-target warn-and-continue.

    UNCONDITIONAL, WITH A NAMED DEPENDENCY: the shared-install `setup/` ships
    only `.percolate-identity.example`, never the real file, so on an
    unmodified shared install every `coordinator-claude*`/`deep-research-
    claude*` mirror/flat-mirror row would trip this. This is adopted
    unconditionally (not graded by resolution rung) because an install-root
    audit found no currently-shipping row that reads content FROM the
    install root — every row's `source_subdir` resolves back to the DoE
    clone via the `plugin-source:` sigil (docs/plans/2026-08-01-percolate-
    root-rung-ordering.md, chunk C14). If a future audit finds a
    shared-install row that DOES read local content, this must be
    revisited — this comment exists so a later reader does not treat
    "unconditional" as free of that dependency.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _machine_local_percolate_identity_path() -> Path:
    """The machine-local canonical `.percolate-identity` rung: settings-home
    ROOT (NOT `machine-local/`, unlike `_read_doe_root_pointer`'s `.doe-root`
    rung) — verified on disk at `~/.coordinator-claude-settings/.percolate-identity`.
    Mirrors `_read_doe_root_pointer`'s env-var precedence: `COORDINATOR_SETTINGS_HOME`
    wins if set, else a path relative to `CLAUDE_HOME`, else a path relative to the
    platform home directory."""
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or str(Path.home()), ".coordinator-claude-settings"
    )
    return Path(settings_home) / ".percolate-identity"


def resolve_percolate_identity_path(setup_dir: Path) -> Optional[Path]:
    """Resolve `.percolate-identity` across the two-rung ladder:

      1. `<setup_dir>/.percolate-identity` — the per-repo file. Wins
         unconditionally when present (a repo that deliberately carries its
         own must never be overridden by a machine-local one).
      2. the machine-local canonical copy (see
         `_machine_local_percolate_identity_path`) — added so an operator who
         has already placed one identity file on the machine doesn't have to
         hand-copy it into every repo that publishes (the recurrence this
         function exists to close off).

    Returns `None` when neither rung resolves — callers treat that as "run
    `check_identity_file_present` to raise the FATAL", mirroring
    `_read_doe_root_pointer`'s "" empty-string not-resolved convention but
    returning `Optional[Path]` since callers here need the winning path, not
    just a resolved/unresolved flag.
    """
    per_repo_path = setup_dir / ".percolate-identity"
    if per_repo_path.is_file():
        return per_repo_path
    machine_local_path = _machine_local_percolate_identity_path()
    if machine_local_path.is_file():
        return machine_local_path
    return None


def check_identity_file_present(identity_path: Optional[Path], setup_dir: Path) -> Path:
    """AC18: fail loud when `.percolate-identity` is absent on EITHER rung,
    rather than falling through with `identity_file_exists=False` for
    `warn_machine_slug_net` to WARN about later, per-target — an absent
    file leaves PERSONAL_REVIEW_PATTERNS empty and the Phase 4
    personal-codename audit INERT, a personal-data exposure, not merely a
    correctness bug.

    `identity_path` is the caller's already-resolved
    `resolve_percolate_identity_path(setup_dir)` result (`None` when neither
    rung resolved). Returns the resolved path unchanged when present, so
    callers can pass this straight into `check_identity_file_safe`/
    `parse_percolate_identity` without re-resolving.

    Raises `IdentityFileMissingError` (caller must abort the whole run,
    matching `IdentityFileUnsafeError`'s abort shape) naming BOTH candidate
    locations — the per-repo path and the machine-local path — so the
    operator knows either one works, plus the one-command remediation:
    `setup_dir / ".percolate-identity.example"` is present in the shared
    install, and copying it to `.percolate-identity` is a COLD CREATE (the
    destination does not yet exist) — permitted unconditionally by C6's
    careful-write guard and NOT a violation of C7's no-hand-clobber rule,
    which only governs overwriting an existing tracked destination.
    """
    if identity_path is not None and identity_path.is_file():
        return identity_path
    per_repo_path = setup_dir / ".percolate-identity"
    machine_local_path = _machine_local_percolate_identity_path()
    example_path = setup_dir / ".percolate-identity.example"
    raise IdentityFileMissingError(
        f"[publish.py] FATAL: neither {per_repo_path} nor {machine_local_path} "
        "is present — refusing to run. "
        "The machine-slug detection net (warn_machine_slug_net) depends on this "
        "file; publishing without it leaves the Phase 4 personal-codename audit "
        "inert. Fix (a cold create, not a hand-clobber — safe under C6/C7): "
        f"cp {example_path} {per_repo_path} && edit it to populate "
        "PERSONAL_REVIEW_PATTERNS (or place the same file at "
        f"{machine_local_path} to cover every repo on this machine)."
    )


def check_identity_file_safe(identity_path: Path, *, err: IO[str] = sys.stderr) -> None:
    """Port of the bash `-O` (owned-by-current-user) and mode
    group/world-writable checks. Raises `IdentityFileUnsafeError` (caller
    must abort the run, matching bash `exit 1`) when the file is foreign-owned
    or group/world-writable.

    Windows degrade: `os.geteuid`/POSIX owner semantics do not exist there.
    Per the chunk brief ("do not crash, and do not silently pass"), this
    prints a visible WARNING that the check could not be evaluated and
    proceeds — it does NOT silently treat the file as verified-safe, it
    visibly declines to verify and lets the (already machine-local,
    gitignored, trusted-by-convention) file through, exactly as the mode
    check has no meaning to enforce on a filesystem with no POSIX mode bits.
    """
    if not hasattr(os, "geteuid"):
        print(
            f"[publish.py] WARNING: ownership/mode security check for {identity_path} "
            "skipped — this platform has no POSIX ownership/permission semantics "
            "(Windows). Proceeding without verifying the identity file's owner or mode.",
            file=err,
        )
        return

    st = identity_path.stat()
    if st.st_uid != os.geteuid():
        raise IdentityFileUnsafeError(
            f"[publish.py] SECURITY: {identity_path} is not owned by the current user — refusing to source."
        )

    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o022:  # group-write (0o020) or other-write (0o002) — bash's [2367] digit check
        perm_octal = oct(mode)[2:].zfill(3)
        raise IdentityFileUnsafeError(
            f"[publish.py] SECURITY: {identity_path} has group/world-writable permissions "
            f"(mode {perm_octal}) — refusing to source."
        )


# ---------------------------------------------------------------------------
# Live-install-clobber guard — port of `setup/publish.sh`.
# Override: COORDINATOR_OVERRIDE_PUBLISH_DEST_HOME=1.
# ---------------------------------------------------------------------------
def check_live_install_clobber(
    dest_dir: Path,
    name: str,
    *,
    dry_run: bool,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> bool:
    claude_home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    live_root = str(Path(claude_home) / ".claude").rstrip("/").rstrip("\\")
    norm_dest = str(dest_dir).rstrip("/").rstrip("\\")

    if not live_root:
        return True
    if not (norm_dest == live_root or norm_dest.startswith(live_root + "/") or norm_dest.startswith(live_root + "\\")):
        return True

    if os.environ.get("COORDINATOR_OVERRIDE_PUBLISH_DEST_HOME", "0") == "1":
        print(
            f"  WARNING: DEST '{dest_dir}' is at or under the live-install root ('{live_root}'); "
            "COORDINATOR_OVERRIDE_PUBLISH_DEST_HOME=1 — publishing anyway.",
            file=err,
        )
        return True
    if dry_run:
        print(
            f"  WARNING (dry-run): DEST '{dest_dir}' is at or under the live-install root "
            f"('{live_root}') — would abort without override.",
            file=err,
        )
        return True

    print(f"  Error: DEST '{dest_dir}' is at or under the live-install root ('{live_root}').", file=err)
    print("         Publishing to the live-install root is banned (2026-05-20 clobber doctrine).", file=err)
    print("         Set publish.mirrors.<key>.path to an external publish-repo path,", file=err)
    print("         or set COORDINATOR_OVERRIDE_PUBLISH_DEST_HOME=1 to override.", file=err)
    print(f"  Skipping {name}.", file=out)
    print("", file=out)
    return False


# ---------------------------------------------------------------------------
# Dirty-tree guard — port of `setup/publish.sh`.
# Override: COORDINATOR_OVERRIDE_DIRTY_TREE=1.
# ---------------------------------------------------------------------------
def _git_is_inside_work_tree(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _git_status_porcelain(
    path: Path, pathspec: Optional[List[str]] = None
) -> "tuple[int, str]":
    """Runs `git -C <path> status --porcelain -- <pathspec>` (default `.`,
    the whole-subtree form every existing caller relies on — see
    `check_dirty_tree`'s docstring) and returns `(returncode, stdout)` RAW —
    unlike the pre-C1 shape this replaces, which swallowed a non-zero return
    into `""`, indistinguishable from "clean" (the fail-open hazard DR-227
    and this plan's hazard section name). Every caller is responsible for
    its own returncode handling; `check_dirty_tree` is the only caller
    today.

    An `OSError` (e.g. `git` not on `PATH`) maps to `(1, "")` — a
    non-zero-equivalent, the same fail-closed shape as a real non-zero git
    exit, never silently treated as clean.
    """
    args = ["git", "-C", str(path), "status", "--porcelain", "--"]
    args.extend(pathspec if pathspec else ["."])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return (1, "")
    return (result.returncode, result.stdout)


def check_dirty_tree(
    source_dir: Path,
    name: str,
    *,
    dry_run: bool,
    pathspec: Optional[List[str]] = None,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> bool:
    """Port of `setup/publish.sh`'s dirty-tree check, over `source_dir`. The
    production call site (`run_pre_sync_gates`) narrows `pathspec` to the
    DR-227 publish-relevant set (`_publish_relevant_paths`) —
    `docs/plans/2026-08-03-narrow-check-dirty-tree-to-publish-relevant-paths.md`.

    `pathspec`, when omitted (the default), preserves the PRE-narrowing
    behaviour byte-for-byte: a bare `git status --porcelain -- .` scoped to
    `source_dir`'s whole subtree, AND the original fail-open swallow (a
    non-zero git return reads as "clean"). This is deliberate — every
    existing `TestCheckDirtyTree` case exercising this shape is built on it
    and must stay unaffected (plan AC2/AC7). This pathspec-less default is a
    TEST-AFFORDANCE ONLY, not a supported production shape (DR-227,
    docs/decisions/DR-227-whole-tree-dirty-classifier-redundant-under-
    explicit-path-scoping.md) — a future caller must not silently pick up
    whole-tree scope at what should be a pathspec-scoped call site.

    WITH an explicit `pathspec`, a non-zero git return BLOCKS (prints a
    diagnostic naming the failing pathspec and returns `False`) — it never
    falls through to "clean". This is the fail-closed half of the same
    change: an empty stdout after a git FAILURE must never be
    indistinguishable from an empty stdout after a clean status.

    This non-zero+pathspec branch is DELIBERATELY NOT routed through
    `COORDINATOR_OVERRIDE_DIRTY_TREE` (Review: code-reviewer Finding 2). git
    could not answer "is this dirty" at all here, so there is no dirty-diff
    for an operator to consciously accept the risk of publishing past —
    unlike the "uncommitted changes" leg below, where the tree state IS
    knowable and the row proceeds from HEAD regardless.
    `_publish_relevant_allowlist_leg_dirspec`'s directory-granularity
    pathspec (Finding 1) removes the main foreseeable trigger for this
    branch (unbounded per-file argv length); the exception stays
    intentional independent of that fix. This is the ONLY leg of this
    function that still returns `False` on a real (non-dry-run) call.

    Post-`_git_materialize_ref` (plan `2026-08-04-publish-from-a-committed-
    ref.md`, C1a/C1b), the publish reads a shadow tree extracted from a
    committed ref, never `source_dir` itself — so a dirty `source_dir` can
    no longer make uncommitted bytes ship; that is now structurally
    impossible. What a dirty tree over the DR-227 publish-relevant pathspec
    still means is narrower but real: the bytes about to ship (HEAD) are
    STALE relative to what the operator has open in an editor. Because
    stale-but-published beats silently-dropped, the "uncommitted changes"
    leg below WARNS (naming the dirty paths individually) and PROCEEDS from
    HEAD rather than skipping the row — a prior version of this function
    dropped the row entirely on this leg, which cost a real incident (a
    sync that shipped 27 files instead of 1202, and ~40 downstream false
    positives from the silent drop). `COORDINATOR_OVERRIDE_DIRTY_TREE` is
    now logically redundant on this leg (both branches warn-and-proceed)
    but is left wired exactly as before — retiring it is a separate,
    user-visible decision this change does not make. The working tree
    itself is never touched, no matter which branch below fires.
    """
    if not _git_is_inside_work_tree(source_dir):
        return True  # can't assess — same as bash's guarded `if git ... ; then`

    returncode, dirty = _git_status_porcelain(source_dir, pathspec)
    if returncode != 0:
        if pathspec is None:
            # Pre-C1 fail-open swallow, preserved byte-for-byte for the
            # pathspec-less (test-affordance) call shape — AC2/AC7.
            dirty = ""
        else:
            print(
                f"  Error: git status failed for {source_dir} with pathspec "
                f"{pathspec!r} (exit code {returncode}) — refusing to treat "
                "this as clean.",
                file=err,
            )
            print(f"  Skipping {name}.", file=out)
            print("", file=out)
            return False

    if not dirty:
        return True

    sha = _git_head(source_dir) or "HEAD"

    if dry_run:
        print(
            f"  WARNING: {source_dir} has uncommitted changes in the publish-relevant set — "
            f"a real run would proceed from {sha}: the published bytes would be HEAD, not "
            "what is open in an editor:",
            file=err,
        )
        for line in dirty.splitlines():
            print(f"    {line}", file=err)
        return True

    if os.environ.get("COORDINATOR_OVERRIDE_DIRTY_TREE", "0") == "1":
        print(
            f"  WARNING: {source_dir} is dirty; COORDINATOR_OVERRIDE_DIRTY_TREE=1 set — "
            f"proceeding from {sha}: your uncommitted edits will not appear in the "
            "published output, but the working tree is not modified.",
            file=err,
        )
        return True

    print(
        f"  WARNING: {source_dir} has uncommitted changes in the publish-relevant set — "
        f"proceeding from {sha}: the published bytes will be HEAD, not what is open in "
        "an editor. Commit first (and re-run) to publish the current edits.",
        file=err,
    )
    for line in dirty.splitlines():
        print(f"    {line}", file=err)
    return True


# ---------------------------------------------------------------------------
# Version-regression gate — port of `setup/lib/percolate-gate.sh`
# `check_marketplace_version_regression` (~:77-115).
# Override: COORDINATOR_OVERRIDE_VERSION_REGRESSION=1.
# ---------------------------------------------------------------------------
_VERSION_FIELD_RE = re.compile(r'"version"\s*:\s*"([^"]*)"')


def _extract_json_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _VERSION_FIELD_RE.search(text)
    return m.group(1) if m else ""


def _version_key(version: str):
    """Natural-sort key approximating GNU `sort -V` for dot/hyphen-delimited
    version strings — numeric segments compare numerically, non-numeric
    segments compare as strings, and a numeric segment always sorts before a
    non-numeric one at the same position (matches ordinary semver ordering
    for the X.Y.Z strings this gate deals with)."""
    key = []
    for part in re.split(r"[.\-]", version):
        if part.isdigit():
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part))
    return key


def check_marketplace_version_regression(
    source_dir: Path,
    dest_dir: Path,
    name: str,
    *,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> bool:
    src_json = source_dir / "marketplace.json"
    tgt_json = dest_dir / "marketplace.json"
    if not src_json.is_file() or not tgt_json.is_file():
        return True  # no source marketplace.json (N/A) or no target yet (first publish)

    src_ver = _extract_json_version(src_json)
    tgt_ver = _extract_json_version(tgt_json)
    if not src_ver or not tgt_ver:
        return True  # unparseable version — skip gate (conservative, matches bash)

    if _version_key(src_ver) >= _version_key(tgt_ver):
        return True

    if os.environ.get("COORDINATOR_OVERRIDE_VERSION_REGRESSION", "0") == "1":
        print(
            f"  WARNING: version regression detected (source {src_ver} < target {tgt_ver}) — "
            "COORDINATOR_OVERRIDE_VERSION_REGRESSION=1 set; proceeding anyway.",
            file=err,
        )
        return True

    print(f"  ERROR: publish would downgrade marketplace.json: source {src_ver} < target {tgt_ver}.", file=err)
    print(f"         Source must lead. Bump the version in {src_json} before publishing.", file=err)
    print("         To override: set COORDINATOR_OVERRIDE_VERSION_REGRESSION=1", file=err)
    print(
        f"  Skipping {name} (version regression — fix source version or set "
        "COORDINATOR_OVERRIDE_VERSION_REGRESSION=1).",
        file=out,
    )
    print("", file=out)
    return False


# ---------------------------------------------------------------------------
# Version-consistency gate — port of `setup/publish.sh`. Invokes
# `check-version-consistency.py` (already a naked-Python CLI trampoline —
# see that file's header) in a subprocess, using THIS interpreter
# (`sys.executable`) rather than re-deriving a `$PYTHON`/python3/python
# search: this driver is already running under Python 3, so the bash
# original's "no Python 3 interpreter resolvable" fail-closed branch cannot
# occur here — a DELIBERATE simplifying divergence, not a dropped gate (the
# gate-file-missing fail-closed branch is preserved unchanged).
# Override: COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1.
# ---------------------------------------------------------------------------
def check_version_consistency(
    source_dir: Path,
    coordinator_bin_default_dir: Path,
    name: str,
    *,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> bool:
    marketplace = source_dir / ".claude-plugin" / "marketplace.json"
    if not marketplace.is_file():
        return True  # skips manifest sub-plugin targets that ship no marketplace.json

    coordinator_bin_env = os.environ.get("COORDINATOR_BIN")
    vc_gate = (
        Path(coordinator_bin_env) / "check-version-consistency.py"
        if coordinator_bin_env
        else coordinator_bin_default_dir / "check-version-consistency.py"
    )
    override = os.environ.get("COORDINATOR_OVERRIDE_VERSION_CONSISTENCY", "0") == "1"

    if not vc_gate.is_file():
        if override:
            print(
                f"  WARNING: version-consistency gate not found (tried {vc_gate}; "
                f"COORDINATOR_BIN={coordinator_bin_env or '<unset>'}, "
                f"COORDINATOR_BIN_DEFAULT={coordinator_bin_default_dir}); "
                f"COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1 set — publishing anyway, surfaces NOT checked for {name}.",
                file=err,
            )
            return True
        print(
            f"  Skipping {name} (version-consistency gate not found — tried {vc_gate}, "
            f"COORDINATOR_BIN={coordinator_bin_env or '<unset>'}, "
            f"COORDINATOR_BIN_DEFAULT={coordinator_bin_default_dir}; "
            "set COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1 for a deliberate opt-out).",
            file=out,
        )
        print("", file=out)
        return False

    result = subprocess.run(
        [sys.executable, str(vc_gate), "--root", str(source_dir), "--quiet"],
        check=False,
    )
    if result.returncode != 0:
        if override:
            print(
                f"  WARNING: version surfaces disagree in {source_dir}; "
                "COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1 set — publishing anyway.",
                file=err,
            )
            return True
        print(
            f"  Skipping {name} (version surfaces disagree — see docs/wiki/versioning-convention.md, "
            "or set COORDINATOR_OVERRIDE_VERSION_CONSISTENCY=1).",
            file=out,
        )
        print("", file=out)
        return False

    return True


# ---------------------------------------------------------------------------
# Machine-slug net — port of `setup/publish.sh`. WARN only, never
# fatal, never causes a skip.
# ---------------------------------------------------------------------------
def warn_machine_slug_net(
    name: str,
    mode: str,
    identity_file_exists: bool,
    identity: Optional[PercolateIdentity],
    totals: "RunTotals",
    *,
    out: IO[str] = sys.stdout,
) -> None:
    if not (name.startswith("coordinator-claude") or name.startswith("deep-research-claude")):
        return
    if mode not in ("mirror", "flat-mirror"):
        return

    if not identity_file_exists:
        warn(
            totals,
            f"machine-slug detection net is DOWN for '{name}': setup/.percolate-identity is absent. "
            "Personal machine codenames will NOT be caught by the Phase 4 audit. Create from "
            "setup/.percolate-identity.example and populate PERSONAL_REVIEW_PATTERNS.",
            out=out,
        )
    elif not identity or not identity.review:
        warn(
            totals,
            f"machine-slug detection net is DOWN for '{name}': PERSONAL_REVIEW_PATTERNS is empty in "
            "setup/.percolate-identity. Personal machine codenames will NOT be caught by the Phase 4 "
            "audit. Populate PERSONAL_REVIEW_PATTERNS (see setup/.percolate-identity.example).",
            out=out,
        )


# ---------------------------------------------------------------------------
# Gate seam — wires the above into the per-target dispatch loop.
# ---------------------------------------------------------------------------
class GateResult(NamedTuple):
    """Return shape for `run_pre_sync_gates`. `proceed=False` means the
    caller must skip this target (mirrors a bash `continue` in the main
    loop). `source_dir` is the EFFECTIVE source dir sync should read from —
    when the target declares an allowlist, this is the restricted temp tree
    `build_allowlisted_source` produced. Otherwise (docs/plans/2026-08-04-
    publish-from-a-committed-ref.md C1b) it is the materialized committed-ref
    SHADOW of the target's resolved `source_dir` — NEVER the target's raw
    resolved `source_dir` itself; even the un-allowlisted row, which never
    enters the allowlist branch, is repointed at its shadow before this
    function returns. `restricted_tmp_src` is the allowlist-narrowed temp
    tree (or None when no allowlist was declared) — threaded through so the
    caller (`process_target`) can remove it after sync completes, on both
    the success and failure paths.

    `shadow_roots` (C6) are the materialized committed-ref shadow trees
    created for this target's contributing roots, deduplicated by (git
    toplevel, sha) — see `_git_materialize_ref`. They must OUTLIVE this
    function's return on the success path: `process_target` reads through
    them across `dispatch_standalone_guards`, the mirror/manifest sync,
    `dispatch_percolate_post_rsync`, and `dispatch_percolate_pre_ci`, so this
    function cannot remove them locally the way it does `restricted_tmp_src`
    on the allowlist-branch failures. The caller removes every path in
    `shadow_roots` — via `_cleanup_shadow_roots`, which also evicts the
    process-lifetime materialization cache so a later target sharing the
    same (toplevel, sha) re-extracts rather than reading a deleted
    directory — both on its early `not proceed` return and in its `finally`
    block, since a gate failure that occurs AFTER materialization (e.g. a
    version-regression or version-consistency failure) still owns shadow
    trees that were already created and must not leak."""

    proceed: bool
    source_dir: Path
    restricted_tmp_src: Optional[Path] = None
    shadow_roots: "tuple[Path, ...]" = ()


def run_pre_sync_gates(
    target: ResolvedTarget,
    setup_dir: Path,
    identity_file_exists: bool,
    identity: Optional[PercolateIdentity],
    totals: "RunTotals",
    *,
    dry_run: bool,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> GateResult:
    """Runs the per-target GATES `setup/publish.sh` runs between "source path
    validated" and "sync dispatched", in the same order as the
    bash original: live-install-clobber, dirty-tree, version-regression,
    version-consistency, machine-slug warn. (The identity-file owner+mode
    check is NOT run here — it runs once at driver startup, see `main` —
    `identity_file_exists`/`identity` are its already-computed results,
    threaded through for the machine-slug warn.)

    Between dirty-tree and version-regression, every contributing root
    (docs/plans/2026-08-04-publish-from-a-committed-ref.md C1b) is
    materialized from its committed ref via `_git_materialize_ref`, over the
    SAME root set the dirty-tree loop above just walked. `GateResult.source_dir`
    is UNCONDITIONALLY the shadow of `target.source_dir` from that point on —
    never the target's raw resolved `source_dir` — so even a row with no
    declared allowlist (which never enters the branch below) publishes from a
    committed ref, not the live tree. `check_marketplace_version_regression`
    and `check_version_consistency` are relocated to run AFTER materialization
    for the same reason: they read raw source directly, and `check_dirty_tree`
    is override-escapable / warn-only under --dry-run, so reading live source
    there could ship a version regression past the gate that exists to stop
    it. When an allowlist IS declared, `build_allowlisted_source` narrows the
    already-materialized shadow tree — it receives shadow roots via
    `real_src` + `source_map`, unchanged in shape, with no `git archive`
    knowledge of its own.

    Allowlist enforcement (`coordinator/lib/percolate/allowlist.py`) runs
    LAST, in the same position `setup/publish.sh` runs it — after
    the machine-slug warn, before the pre-rsync hooks / `case "$mode"`
    dispatch, and it never tests `target.mode`: a flat-mirror row
    can carry an allowlist exactly as a mirror row can (AC18(b)). On success
    `GateResult.source_dir` is repointed to the restricted temp tree
    `build_allowlisted_source` produced; on any allowlist-gate failure this
    returns `proceed=False` (mirrors the bash `continue`) having already
    cleaned up its own temp tree.
    """
    if not check_live_install_clobber(target.dest_dir, target.name, dry_run=dry_run, out=out, err=err):
        return GateResult(proceed=False, source_dir=target.source_dir)

    contributing_roots = _contributing_roots(target)
    publish_relevant_paths = _publish_relevant_paths(target, contributing_roots)
    for root in contributing_roots:
        if not check_dirty_tree(
            root,
            target.name,
            dry_run=dry_run,
            pathspec=publish_relevant_paths[root],
            out=out,
            err=err,
        ):
            return GateResult(proceed=False, source_dir=target.source_dir)

    # Materialize every contributing root from a committed ref (docs/plans/
    # 2026-08-04-publish-from-a-committed-ref.md C1b) BEFORE any gate reads
    # source bytes, over the SAME root set `check_dirty_tree` just walked
    # above — never a re-derived one, so the gate and the materialization it
    # gates cannot disagree on scope. `shadow` maps every real contributing
    # root to its shadow (committed-ref) counterpart; every gate and copy
    # from here on reads through `shadow`, never `target.source_dir` or a
    # `source_map` root directly — that includes the version gates below,
    # which used to read raw source and are relocated here for exactly that
    # reason (see their call sites' comment).
    # C2 (docs/plans/2026-08-04-publish-from-a-committed-ref.md): a
    # contributing root that is not a git work tree has no ref to read, so
    # `_git_materialize_ref` raises `GitMaterializeError` rather than falling
    # back to a live-tree copy (silent reintroduction of the TOCTOU this
    # plan closes for that root) or silently skipping the root (silent
    # incomplete-tree publish). Refuse the publish loud, naming the failing
    # root. Deliberately NOT routed through `COORDINATOR_OVERRIDE_DIRTY_TREE`
    # — that override exists for an operator to knowingly accept a dirty
    # DIFF; a non-materializable root has no diff to accept, the same
    # reasoning `check_dirty_tree` already applies to its own non-zero-git
    # branch.
    # C6 (docs/plans/2026-08-04-publish-from-a-committed-ref.md): report the
    # resolved provenance SHA per contributing root, unconditionally (real
    # run and --dry-run both) — "shipped from <sha>" is what makes a publish
    # reproducible, promised to doe-claude-em in
    # 2026-08-04-claude-klabauter-em-ref-materialization-ratified-here-is-the-
    # path.md. `shadow_toplevels` collects the distinct materialized (git
    # toplevel, sha) shadow trees this target's roots resolved to — several
    # contributing roots commonly share one toplevel+sha (AC11 dedup), so
    # this is built by matching each root's shadow against
    # `_MATERIALIZED_REF_CACHE`'s values rather than by re-deriving
    # toplevel/sha here, and is threaded through `GateResult.shadow_roots`
    # for the caller to clean up once it has finished reading through them.
    shadow: "dict[Path, Path]" = {}
    shadow_toplevels: "set[Path]" = set()
    try:
        for root in contributing_roots:
            shadow[root] = _git_materialize_ref(root)
            sha = _git_rev_parse(root, "HEAD")
            print(f"  Provenance: {root} shipped from {sha or 'unknown'}", file=out)
            for cached_shadow_toplevel in _MATERIALIZED_REF_CACHE.values():
                if shadow[root] == cached_shadow_toplevel or cached_shadow_toplevel in shadow[root].parents:
                    shadow_toplevels.add(cached_shadow_toplevel)
                    break
    except GitMaterializeError as exc:
        print(f"  Error: cannot materialize a contributing root from its committed ref — {exc}", file=err)
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))
    effective_source_dir = shadow[target.source_dir]

    # Relocated from above `check_dirty_tree` (docs/plans/2026-08-04-publish-
    # from-a-committed-ref.md C1b) — these gates read raw source directly, and
    # `check_dirty_tree` is override-escapable (COORDINATOR_OVERRIDE_DIRTY_TREE=1)
    # and warn-only under --dry-run. Reading `target.source_dir` here, before
    # C1b, meant a bumped-but-uncommitted marketplace.json version would PASS
    # this gate while HEAD's older marketplace.json is what actually ships —
    # a version regression shipped past the exact gate meant to stop it. They
    # now read `effective_source_dir` (the materialized shadow of
    # `target.source_dir`), the same bytes that will publish.
    if not check_marketplace_version_regression(effective_source_dir, target.dest_dir, target.name, out=out, err=err):
        return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

    coordinator_bin = coordinator_bin_default(setup_dir.parent)
    if not check_version_consistency(effective_source_dir, coordinator_bin, target.name, out=out, err=err):
        return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

    warn_machine_slug_net(target.name, target.mode, identity_file_exists, identity, totals, out=out)

    restricted_tmp_src: Optional[Path] = None

    if target.allowlist:
        print("", file=out)
        print(f"  Allowlist enforcement: {target.allowlist.replace(',', ', ')}", file=out)
        source_map_dict = _parse_source_map(target.source_map)
        shadow_source_map = {entry: shadow[root] for entry, root in source_map_dict.items()}
        try:
            restricted_tmp_src = build_allowlisted_source(
                effective_source_dir,
                target.allowlist,
                source_map=shadow_source_map or None,
                stderr=err,
            )
        except AllowlistError as exc:
            print(f"  Error: failed to build allowlisted source tree — skipping {target.name}. ({exc})", file=err)
            print("", file=out)
            return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

        print(f"  Restricted source: {restricted_tmp_src}", file=out)
        effective_source_dir = restricted_tmp_src

        if not check_working_data_paths(
            restricted_tmp_src, paths=get_pre_filter_paths(restricted_tmp_src), stderr=err
        ):
            print(f"  Error: secondary working-data assertion failed — skipping {target.name}.", file=err)
            shutil.rmtree(restricted_tmp_src, ignore_errors=True)
            print("", file=out)
            return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

        try:
            assert_allowlist_applied(
                target_name=target.name,
                allowlist_csv=target.allowlist,
                restricted_tmp_src=restricted_tmp_src,
                effective_source_dir=effective_source_dir,
                unrestricted_source_dirs=set(contributing_roots) | set(shadow.values()),
            )
        except AllowlistError as exc:
            print(f"  {exc}", file=err)
            shutil.rmtree(restricted_tmp_src, ignore_errors=True)
            print("", file=out)
            return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

    return GateResult(
        proceed=True,
        source_dir=effective_source_dir,
        restricted_tmp_src=restricted_tmp_src,
        shadow_roots=tuple(shadow_toplevels),
    )


# ---------------------------------------------------------------------------
# Copy-gate primitives — port of setup/lib/percolate-gate.sh, scoped to the
# manifest leg (mirror/flat-mirror get their own in-process copy-needed check
# via setup/publish_sync.py's _needs_copy).
# ---------------------------------------------------------------------------
def bytes_differ(a: Path, b: Path) -> bool:
    """Port of percolate-gate.sh `bytes_differ` — True iff `a` and `b` differ
    byte-for-byte (`filecmp.cmp(..., shallow=False)` is the `cmp -s` analog)."""
    return not filecmp.cmp(a, b, shallow=False)


def files_differ(src: Path, dst: Path) -> bool:
    """Port of percolate-gate.sh `files_differ` — content-aware copy-needed
    check. Returns True (needs copy) when dst is missing, src is strictly
    newer than dst, or (mtime-tie-or-src-older AND bytes differ). Returns
    False only when dst exists and bytes match, regardless of mtime."""
    if not src.is_file():
        return True
    if not dst.is_file():
        return True
    if src.stat().st_mtime > dst.stat().st_mtime:
        return True
    return bytes_differ(src, dst)


# ---------------------------------------------------------------------------
# Run totals + warn() — port of setup/publish.sh's `warn()` and the
# script-global total_synced/total_deleted/total_warnings/processed counters.
# ---------------------------------------------------------------------------
@dataclass
class RunTotals:
    synced: int = 0
    deleted: int = 0
    warnings: int = 0
    processed: int = 0
    audit_files: List[Path] = field(default_factory=list)


def warn(totals: RunTotals, message: str, *, out: IO[str] = sys.stdout) -> None:
    print(f"  WARNING: {message}", file=out)
    totals.warnings += 1


# ---------------------------------------------------------------------------
# Fleet-only fence strip — the copy-time transform seam this driver's raw
# `shutil.copy2` calls previously lacked. `<!-- coordinator:fleet-only:start
# --> ... <!-- coordinator:fleet-only:end -->` marks content authored for the
# internal fleet (DoE-claude's `CLAUDE.md`, `global-doctrine/CLAUDE.md`) that
# must never reach the public OSS mirror byte-for-byte — see those files'
# own fence usage for the documented contract. Before this seam existed,
# every copy site here was a plain `shutil.copy2`, so a fenced file
# published verbatim, fence markers and all: the HTML comment renders
# invisibly and the "private" content ships anyway.
# ---------------------------------------------------------------------------
_FLEET_ONLY_START_RE = re.compile(r"<!--\s*coordinator:fleet-only:start\s*-->")
_FLEET_ONLY_END_RE = re.compile(r"<!--\s*coordinator:fleet-only:end\s*-->")


class FleetOnlyFenceError(Exception):
    """A `coordinator:fleet-only` fence in a file about to be published is
    malformed — unbalanced (`start` with no `end`, `end` with no `start`)
    or nested (a second `start` before the first's `end`). Raised instead
    of guessing at a strip, because passing the fenced content through
    unscrubbed is the dangerous direction: the caller must treat this as
    fatal to the whole publish run, never a per-file skip."""


def _fence_line(text: str, pos: int) -> int:
    """1-based line number of `pos` within `text`, for error messages."""
    return text.count("\n", 0, pos) + 1


def strip_fleet_only_fences(text: str, *, source_label: str) -> tuple[str, int, int]:
    """Removes every `coordinator:fleet-only` fenced span (markers
    inclusive) from `text`. Handles multiple fences per file, a fence
    spanning many lines, and a fence whose markers sit inline within a
    single line of surrounding prose — the prose on either side of the
    markers is preserved untouched in all three shapes.

    Fails loud on a malformed fence (see `FleetOnlyFenceError`), naming
    `source_label` and the 1-based line of the offending marker.

    Returns `(stripped_text, fences_stripped, lines_removed)` —
    `fences_stripped` is 0 (and `stripped_text == text`) when the file
    carries no fence at all; `lines_removed` counts newlines inside the
    removed span(s) and can legitimately be 0 for an inline fence that
    embeds no line break of its own.
    """
    markers: list[tuple[str, int, int]] = []
    for m in _FLEET_ONLY_START_RE.finditer(text):
        markers.append(("start", m.start(), m.end()))
    for m in _FLEET_ONLY_END_RE.finditer(text):
        markers.append(("end", m.start(), m.end()))
    markers.sort(key=lambda t: t[1])

    out_parts: list[str] = []
    pos = 0
    depth = 0
    fence_open_pos = -1
    fences_stripped = 0
    lines_removed = 0

    for kind, mstart, mend in markers:
        if kind == "start":
            if depth > 0:
                raise FleetOnlyFenceError(
                    f"{source_label}:{_fence_line(text, mstart)}: nested "
                    "coordinator:fleet-only 'start' found before the enclosing "
                    "fence's 'end' — aborting publish, not stripping a guess."
                )
            out_parts.append(text[pos:mstart])
            fence_open_pos = mstart
            depth = 1
        else:  # end
            if depth == 0:
                raise FleetOnlyFenceError(
                    f"{source_label}:{_fence_line(text, mstart)}: "
                    "coordinator:fleet-only 'end' with no matching 'start' — "
                    "aborting publish, not stripping a guess."
                )
            # A fence that occupies whole lines (the common case — the
            # `start`/`end` markers each sit alone on their own line) leaves
            # a stray blank line behind if only the marker text itself is
            # removed: the newline preceding `start` is prose's own line
            # break and stays, but the newline immediately trailing `end`
            # is the fence's closing line break, not prose's — consume it
            # too so the lines before and after the fence join cleanly. An
            # inline fence (prose follows `end` on the same line) has no
            # such trailing newline immediately after `end`, so this is a
            # no-op for that shape.
            consumed_end = mend
            if consumed_end < len(text) and text[consumed_end] == "\n":
                consumed_end += 1
            lines_removed += text.count("\n", fence_open_pos, consumed_end)
            fences_stripped += 1
            pos = consumed_end
            depth = 0

    if depth != 0:
        raise FleetOnlyFenceError(
            f"{source_label}:{_fence_line(text, fence_open_pos)}: unbalanced "
            "coordinator:fleet-only fence — 'start' with no matching 'end' — "
            "aborting publish, not stripping a guess."
        )

    out_parts.append(text[pos:])
    return "".join(out_parts), fences_stripped, lines_removed


def _publish_copy_file(
    src_file: Path,
    dst_file: Path,
    *,
    dry_run: bool,
    out: IO[str] = sys.stdout,
) -> None:
    """The single transform-or-byte-copy decision point for this driver's
    copy sites — every write here MUST route through this helper rather
    than calling `shutil.copy2` directly, so a future additional copy site
    cannot silently reopen the raw-byte-copy gap the fleet-only strip
    closes. Non-`.md` files (including `plugin.json`) are always a
    byte-identical `copy2` — the strip is deliberately narrowed to
    markdown, never risking a binary or template file. A `.md` file with
    no fence also falls through to `copy2` unchanged. No-op under
    `dry_run`, but still runs the strip (against `src_file`'s own content —
    dry-run never touches `dst_file`) so it can print a `STRIP:` preview
    line; the caller's existing NEW/UPDATE/REPLACE line is printed
    separately and unconditionally."""
    if src_file.suffix.lower() != ".md":
        if not dry_run:
            shutil.copy2(src_file, dst_file)
        return

    text = src_file.read_text(encoding="utf-8", errors="replace", newline="")
    stripped, fences_stripped, lines_removed = strip_fleet_only_fences(
        text, source_label=str(src_file)
    )
    if fences_stripped == 0:
        if not dry_run:
            shutil.copy2(src_file, dst_file)
        return

    rel_note = f"  STRIP:  {src_file.name} — {fences_stripped} fence(s), {lines_removed} line(s) removed (fleet-only)"
    if dry_run:
        print(rel_note, file=out)
        return

    dst_file.write_text(stripped, encoding="utf-8", newline="")
    shutil.copystat(src_file, dst_file)
    print(rel_note, file=out)


# ---------------------------------------------------------------------------
# Manifest mode — port of setup/publish.sh sync_manifest.
# ---------------------------------------------------------------------------
_SCAN_RE = re.compile(r"^SCAN:\s*(.*)$")
_DELETE_RE = re.compile(r"^DELETE:\s*(.*)$")
_COMMENT_RE = re.compile(r"^\s*#")


def sync_manifest(
    source_dir: Path,
    target_dir: Path,
    totals: RunTotals,
    *,
    dry_run: bool,
    out: IO[str] = sys.stdout,
) -> bool:
    """Port of `sync_manifest`. Returns True on success, False if the
    manifest file itself is absent (mirrors the bash `return 1` — the caller
    must treat this as a per-target skip, matching bash's `set -e` abort
    contract being scoped to THIS function's failure, not the whole run,
    because the bash caller never checks this function's return code in a
    guarded context — see the main-loop dispatch note for why this driver
    treats a manifest-missing condition as fatal-to-the-run instead, a
    deliberate (and safer) divergence: silently skipping a misconfigured
    manifest target is worse than a loud abort)."""
    manifest = target_dir / "publish-manifest.txt"
    if not manifest.is_file():
        print(f"  Error: manifest not found at {manifest}", file=sys.stderr)
        return False

    print(f"  Mode: manifest ({manifest})", file=out)
    print("", file=out)

    lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()

    scan_plugins: dict[str, int] = {}
    manifest_files: dict[str, int] = {}
    synced = 0
    deleted = 0

    # Pass 1: DELETE and SCAN lines.
    for line in lines:
        if line == "" or _COMMENT_RE.match(line):
            continue
        m = _SCAN_RE.match(line)
        if m:
            scan_plugins[m.group(1)] = 1
            continue
        m = _DELETE_RE.match(line)
        if m:
            del_path = m.group(1)
            del_target = target_dir / del_path
            if del_target.is_file():
                if dry_run:
                    print(f"  DELETE: {del_path} (would remove)", file=out)
                else:
                    del_target.unlink()
                    print(f"  DELETE: {del_path}", file=out)
                deleted += 1
            else:
                print(f"  DELETE: {del_path} (already absent)", file=out)

    # Pass 2: COPY lines.
    for line in lines:
        if (
            line == ""
            or _COMMENT_RE.match(line)
            or line.startswith("DELETE:")
            or line.startswith("SCAN:")
        ):
            continue

        src_path = line
        dst_path = line
        src_file = source_dir / src_path
        dst_file = target_dir / dst_path
        manifest_files[src_path] = 1

        if not src_file.is_file():
            warn(totals, f"Source file missing: {src_path}", out=out)
            continue

        if not files_differ(src_file, dst_file):
            continue

        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)

        content_replace = dst_file.is_file() and bytes_differ(src_file, dst_file)

        if dry_run:
            if not dst_file.is_file():
                print(f"  NEW:    {dst_path}", file=out)
            elif content_replace:
                warn(totals, f"REPLACE (content differs) — would overwrite: {dst_path}", out=out)
            else:
                print(f"  UPDATE: {dst_path}", file=out)
            _publish_copy_file(src_file, dst_file, dry_run=True, out=out)
        else:
            is_new = not dst_file.is_file()
            _publish_copy_file(src_file, dst_file, dry_run=False, out=out)
            totals.audit_files.append(dst_file)
            if is_new:
                print(f"  NEW:    {dst_path}", file=out)
            elif content_replace:
                warn(totals, f"REPLACE (content differs) — overwrote: {dst_path}", out=out)
            else:
                print(f"  UPDATE: {dst_path}", file=out)
        synced += 1

    # Structural plugin.json copy — both target shapes (single-plugin depth-2,
    # nested-multi depth-3), matching find's `-maxdepth 3 -path
    # "*/.claude-plugin/plugin.json"` exactly.
    pj_candidates = sorted(
        set(source_dir.glob(".claude-plugin/plugin.json")) | set(source_dir.glob("*/.claude-plugin/plugin.json"))
    )
    for pj_src in pj_candidates:
        pj_rel = pj_src.relative_to(source_dir).as_posix()
        pj_dst = target_dir / pj_rel

        if not files_differ(pj_src, pj_dst):
            continue

        if not dry_run:
            pj_dst.parent.mkdir(parents=True, exist_ok=True)

        pj_content_replace = pj_dst.is_file() and bytes_differ(pj_src, pj_dst)

        if dry_run:
            if not pj_dst.is_file():
                print(f"  NEW:    {pj_rel} (plugin.json — structural)", file=out)
            elif pj_content_replace:
                warn(
                    totals,
                    f"REPLACE (content differs) — would overwrite: {pj_rel} (plugin.json — structural)",
                    out=out,
                )
            else:
                print(f"  UPDATE: {pj_rel} (plugin.json — structural)", file=out)
            _publish_copy_file(pj_src, pj_dst, dry_run=True, out=out)
        else:
            pj_is_new = not pj_dst.is_file()
            _publish_copy_file(pj_src, pj_dst, dry_run=False, out=out)
            totals.audit_files.append(pj_dst)
            if pj_is_new:
                print(f"  NEW:    {pj_rel} (plugin.json — structural)", file=out)
            elif pj_content_replace:
                warn(
                    totals,
                    f"REPLACE (content differs) — overwrote: {pj_rel} (plugin.json — structural)",
                    out=out,
                )
            else:
                print(f"  UPDATE: {pj_rel} (plugin.json — structural)", file=out)
        synced += 1

    # Staleness scan: only SCAN:-declared plugins.
    print("", file=out)
    print("  --- staleness scan ---", file=out)
    stale_count = 0
    if not scan_plugins:
        print("    (no SCAN: directives — skipping)", file=out)
    for plugin_dir in sorted(scan_plugins):
        src_plugin = source_dir / plugin_dir
        if not src_plugin.is_dir():
            continue
        for src_file in sorted(p for p in src_plugin.rglob("*") if p.is_file()):
            rel_path = src_file.relative_to(source_dir).as_posix()
            if rel_path.endswith("/.claude-plugin/plugin.json") or rel_path == ".claude-plugin/plugin.json":
                continue
            if "_archived" in rel_path:
                continue
            if rel_path not in manifest_files:
                warn(totals, f"Not in manifest: {rel_path}", out=out)
                stale_count += 1
    if stale_count == 0:
        print("    (all source files covered)", file=out)

    totals.synced += synced
    totals.deleted += deleted
    print("", file=out)
    print(f"  Synced: {synced} file(s), Deleted: {deleted} file(s)", file=out)
    return True


# ---------------------------------------------------------------------------
# Mirror / flat-mirror dispatch — imports whichever publish_sync.py wins the
# seam in-process (§ AMENDED 2026-08-03, DR-079 `26450311a` — "the seam, not
# the copy"). No `setup/publish_sync.py` copy ever lands in claude-klabauter: the
# generic sync engine lands ONCE as `coordinator/lib/percolate/publish_sync.py`,
# beside the `ignore.py` it already imports, and `setup_dir`'s own
# `publish_sync.py` — DoE's per-root override — keeps winning when present.
# This mirrors the precedent `_claude_klabauter_coordinator_bin()` already sets in this
# same file for the executable surface: percolate-root first, engine repo as
# fallback — not a new abstraction, an extension of that one.
# ---------------------------------------------------------------------------
_ENGINE_PUBLISH_SYNC_PATH = _COORDINATOR_LIB / "percolate" / "publish_sync.py"


def _resolve_publish_sync_module_path(setup_dir: Path) -> Path:
    """Resolve which `publish_sync.py` wins the seam for `setup_dir`:
    `setup_dir/publish_sync.py` if present (DoE's per-root override, or any
    other percolate-root's own copy), else this repo's engine-side module at
    `coordinator/lib/percolate/publish_sync.py`. Provenance-blind by design —
    `check_publish_sync_contract` validates the INTERFACE of whichever module
    this resolves to, identically regardless of which path won (§ AMENDED
    2026-08-03: "never provenance... that is exactly what keeps both paths
    fail-closed")."""
    override = setup_dir / "publish_sync.py"
    if override.is_file():
        return override
    return _ENGINE_PUBLISH_SYNC_PATH


def _import_publish_sync(setup_dir: Path):
    """Import whichever module `_resolve_publish_sync_module_path` resolves
    to for `setup_dir` — claude-klabauter has no `setup/` directory of its own before
    this plan's C1 lands one, so a claude-klabauter-rooted run resolves straight to the
    engine module; a DoE-rooted run keeps resolving `setup/publish_sync.py`
    exactly as before.

    The engine module (`coordinator/lib/percolate/publish_sync.py`) lives
    inside the `percolate` PACKAGE and uses a plain relative import
    (`from .ignore import ...`, § its own docstring's cut 1) — a
    `spec_from_file_location`-loaded module has no package context to
    resolve that against and raises `ImportError: attempted relative import
    with no known parent package`. Import it through the package
    (`percolate.publish_sync`, already reachable since `_COORDINATOR_LIB` is
    on `sys.path` — see the module-level `sys.path` bootstrap above)
    instead of the ad hoc `spec_from_file_location` machinery an arbitrary
    `setup_dir` override still needs."""
    module_path = _resolve_publish_sync_module_path(setup_dir)
    if module_path == _ENGINE_PUBLISH_SYNC_PATH:
        return importlib.import_module("percolate.publish_sync")

    spec = importlib.util.spec_from_file_location("publish_sync", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build a module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    # Defensive: register before exec so any future dataclass/typing
    # introspection inside publish_sync.py (module-level __module__ lookups)
    # does not hit the same sys.modules-not-yet-populated trap this driver's
    # own module load had to guard against.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# AC15 (C11) — the mirror-dispatch keyword-argument set `dispatch_mirror_like`
# splats into `sync_mirror`/`sync_flat_mirror`. Single source of truth: used
# BOTH to build the actual call-site kwargs below AND, with a placeholder
# value, to validate the loaded `publish_sync` module's API contract ONCE in
# `main()` (see `check_publish_sync_contract`) — never a separately
# hand-maintained parameter-name list, so the validated set and the passed
# set cannot drift apart independently.
def _mirror_dispatch_kwargs(copy_file) -> dict:
    return {"copy_file": copy_file}


_MIRROR_ENTRY_POINTS = ("sync_mirror", "sync_flat_mirror")


class ProcessTargetCallerContractError(RuntimeError):
    """Raised by `process_target` when a mirror/flat-mirror target is
    dispatched without a resolved `publish_sync_module` — the caller's own
    contract violation (`main()` must resolve it once, pre-loop, per AC15),
    not a user-facing publish failure. Explicit raise rather than a bare
    `assert` (Finding 5, code-reviewer): `python -O` strips asserts, which
    would let `None` fall through to `dispatch_mirror_like` and surface a
    confusing `AttributeError` instead of this clear message."""


class PublishSyncContractError(Exception):
    """Raised by `check_publish_sync_contract` (AC15, chunk C11) when the
    dynamically imported `publish_sync.py` module does not satisfy the API
    contract `dispatch_mirror_like` depends on: a missing `sync_mirror`/
    `sync_flat_mirror` symbol, a signature that rejects the mirror-dispatch
    keyword arguments (`copy_file` — the incident's `TypeError: sync_mirror()
    got an unexpected keyword argument 'copy_file'`), or a bare
    `*args`/`**kwargs` callee that would pass a superficial signature check
    while still failing at runtime. The caller (`main`) must abort the WHOLE
    run before any target's sync dispatch — this is an API-contract
    violation, distinct from `EngineUnavailableError` (the percolate-engine
    fail-closed contract) and from `IdentityFileMissingError`/
    `IdentityFileUnsafeError` (the identity-file gate).

    REASONING TO RECORD (do not delete this check as "redundant with C1"):
    C1 (registry-first pointer rung) + C6 (installer guard) + C8 (removal
    leg) close THIS incident's specific vector — once resolution prefers the
    DoE clone and the installed `setup/` residual is gone, there is no stale
    callee left on this path to meet. What survives is the CLASS of failure:
    a dynamically imported module that satisfies the import while failing
    the caller's actual API contract has no detector anywhere, so a
    recurrence through any other future path (a new rung, an operator
    override, a new install shape) presents identically — every gate green,
    then a raw `TypeError` from deep inside a dispatch. This is the
    general-purpose detector for that class, not a narrower patch for the
    one incident."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def check_publish_sync_contract(
    publish_sync_module,
    module_path: Path,
    rung_label: str,
) -> None:
    """AC15 (chunk C11): assert `publish_sync_module` (loaded from
    `module_path`, resolved via `rung_label` — see `main`) exposes the API
    `dispatch_mirror_like` actually depends on, BEFORE any target's sync
    dispatch. Called ONCE in `main()`, pre-loop — never per-target (a
    per-target check only fails loud "before any dispatch" accidentally,
    whichever target happens to be first). Runs UNCHANGED regardless of
    whether `publish_sync_module` resolved to `setup_dir/publish_sync.py` or
    the engine-side `coordinator/lib/percolate/publish_sync.py` fallback (§
    `_resolve_publish_sync_module_path`, AMENDED 2026-08-03) — it validates
    the interface, never provenance, so both paths stay fail-closed alike.

    For each of `sync_mirror`/`sync_flat_mirror`:
      1. the symbol must be present on the module;
      2. `inspect.signature` must be computable on it;
      3. its signature must not be a bare `*args`/`**kwargs` wrapper (that
         would satisfy a superficial signature check while still failing at
         runtime for arguments python's binder cannot actually place);
      4. `inspect.signature(fn).bind_partial(**mirror_kwargs)` must succeed
         against the SAME dict `_mirror_dispatch_kwargs` builds for the real
         call site — never a separately hand-maintained name list.

    `load_ignore` gets the same four-part treatment (presence, inspectable
    signature, not a bare var-wrapper, binds a single path-or-None argument)
    — closing the gap `_MIRROR_ENTRY_POINTS` alone left open:
    `dispatch_mirror_like` also calls `publish_sync_module.load_ignore(...)`
    at dispatch time, so a module that cleared the pre-loop gate on
    `sync_mirror`/`sync_flat_mirror` alone could still `AttributeError` (or
    raise a `TypeError` from an incompatible signature) mid-publish — the
    exact fail-open this gate exists to prevent, and it matters more now
    that a second module can win the seam (§ AMENDED 2026-08-03).

    Raises `PublishSyncContractError` naming: (1) `module_path`, (2) the
    missing symbol/parameter, (3) `rung_label` (from C1's
    `coordinator_percolate_runtime_root_explained()`, threaded through by the
    caller) — the three facts whose absence made the original incident's raw
    `TypeError` unreadable.
    """
    mirror_kwargs = _mirror_dispatch_kwargs(None)

    for symbol in _MIRROR_ENTRY_POINTS:
        fn = getattr(publish_sync_module, symbol, None)
        if fn is None:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"does not define {symbol!r} — dispatch_mirror_like cannot call it. "
                "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
            )

        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError) as exc:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"defines {symbol!r} but its signature could not be inspected: {exc}. "
                "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
            ) from exc

        params = list(sig.parameters.values())
        is_bare_var_wrapper = bool(params) and all(
            p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            for p in params
        )
        if is_bare_var_wrapper:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"defines {symbol!r} as a bare (*args/**kwargs) wrapper — this would pass "
                "a superficial signature check while still failing at runtime for the "
                f"mirror-dispatch keyword arguments {sorted(mirror_kwargs)}. Refusing to "
                "dispatch any mirror/flat-mirror target (AC15 fail-closed)."
            )

        try:
            sig.bind_partial(**mirror_kwargs)
        except TypeError as exc:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"defines {symbol!r} but its signature does not accept the mirror-dispatch "
                f"keyword arguments {sorted(mirror_kwargs)}: {exc}. Refusing to dispatch "
                "any mirror/flat-mirror target (AC15 fail-closed)."
            ) from exc

    # `sync_mirror`-only: `renamed_dir_names` (§ `dispatch_mirror_like`'s own
    # docstring; state/audits/2026-08-05-first-full-payload-identity-
    # findings.md Group E) is not part of the shared `_mirror_dispatch_kwargs`
    # bind-check above (that dict is also used against `sync_flat_mirror`,
    # which has no equivalent parameter) — checked separately here so an
    # override `setup_dir/publish_sync.py` module lacking it fails loud
    # pre-loop, not with a `TypeError` mid-publish at the real mirror-mode
    # dispatch call site.
    sync_mirror_fn = getattr(publish_sync_module, "sync_mirror")
    try:
        inspect.signature(sync_mirror_fn).bind_partial(renamed_dir_names=None)
    except TypeError as exc:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            f"defines 'sync_mirror' but its signature does not accept "
            f"'renamed_dir_names': {exc}. Refusing to dispatch any mirror/"
            "flat-mirror target (AC15 fail-closed)."
        ) from exc

    load_ignore_fn = getattr(publish_sync_module, "load_ignore", None)
    if load_ignore_fn is None:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            "does not define 'load_ignore' — dispatch_mirror_like cannot call it. "
            "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
        )

    try:
        load_ignore_sig = inspect.signature(load_ignore_fn)
    except (TypeError, ValueError) as exc:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            f"defines 'load_ignore' but its signature could not be inspected: {exc}. "
            "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
        ) from exc

    load_ignore_params = list(load_ignore_sig.parameters.values())
    load_ignore_is_bare_var_wrapper = bool(load_ignore_params) and all(
        p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in load_ignore_params
    )
    if load_ignore_is_bare_var_wrapper:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            "defines 'load_ignore' as a bare (*args/**kwargs) wrapper — this would pass "
            "a superficial signature check while still failing at runtime for the single "
            "path-or-None argument dispatch_mirror_like passes. Refusing to dispatch any "
            "mirror/flat-mirror target (AC15 fail-closed)."
        )

    try:
        load_ignore_sig.bind_partial(None)
    except TypeError as exc:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            "defines 'load_ignore' but its signature does not accept a single "
            f"path-or-None argument: {exc}. Refusing to dispatch any mirror/flat-mirror "
            "target (AC15 fail-closed)."
        ) from exc


def dispatch_mirror_like(
    publish_sync_module,
    target: ResolvedTarget,
    effective_source_dir: Path,
    totals: RunTotals,
    *,
    dry_run: bool,
    renamed_dir_names: "frozenset[str] | None" = None,
    out: IO[str] = sys.stdout,
) -> None:
    """Calls `publish_sync.sync_mirror`/`sync_flat_mirror` directly
    (in-process — never subprocessed), and folds the returned (synced,
    removed) counts into `totals`. Port of the bash `sync_mirror`/
    `sync_flat_mirror` wrapper functions minus the subprocess capture-and-
    replay-stdout machinery those needed only because bash was shelling out
    to a separate `publish_sync.py` process.

    `publish_sync_module` is resolved ONCE in `main()` (via
    `_import_publish_sync`) and its API contract validated there
    (`check_publish_sync_contract`, AC15) — this function never re-imports
    or re-validates it per target.

    `renamed_dir_names` (default `None`) is forwarded to `sync_mirror` ONLY
    (§ that function's own docstring; `sync_flat_mirror` has no equivalent
    parameter — flat-mirror rows have no per-plugin top-level orphan sweep
    for a directory rename to collide against). `process_target` resolves
    this from the row's own rename-generation ledger BEFORE this call, so
    a directory the upcoming content-transform sweep is about to reproduce
    is exempted from this sync pass's own orphan-deletion (state/audits/
    2026-08-05-first-full-payload-identity-findings.md Group E)."""
    print(f"  Mode: {target.mode} (copy + delete)", file=out)
    print("", file=out)

    ignore_file = effective_source_dir / ".percolate-ignore"
    ignore_matcher = publish_sync_module.load_ignore(ignore_file if ignore_file.is_file() else None)

    def _copy_file(src_file: Path, dst_file: Path, file_dry_run: bool) -> None:
        """Injects this driver's fleet-only-fence strip into the mirror-like
        copy engines — the seam that closes the "strip exists but nothing on
        the real publish path calls it" gap (mirror/flat-mirror targets never
        went through `_publish_copy_file`, only manifest-mode did). Single-
        sourced in THIS module (`_publish_copy_file`/`strip_fleet_only_fences`)
        and passed DOWN as a callable — `publish_sync.py` never re-derives the
        strip itself, so the two copy engines cannot drift apart on it."""
        _publish_copy_file(src_file, dst_file, dry_run=file_dry_run, out=out)

    mirror_kwargs = _mirror_dispatch_kwargs(_copy_file)
    if target.mode == "mirror":
        synced, removed = publish_sync_module.sync_mirror(
            effective_source_dir,
            target.dest_dir,
            ignore_matcher,
            dry_run,
            renamed_dir_names=renamed_dir_names,
            **mirror_kwargs,
        )
    else:
        synced, removed = publish_sync_module.sync_flat_mirror(
            effective_source_dir, target.dest_dir, ignore_matcher, dry_run, **mirror_kwargs
        )

    totals.synced += synced
    totals.deleted += removed
    print("", file=out)
    print(f"  Synced: {synced} file(s), Removed: {removed} file(s)", file=out)


# ---------------------------------------------------------------------------
# Last-sync marker — port of setup/publish.sh (Phase 5).
# ---------------------------------------------------------------------------
def _is_git_repo(path: Path) -> bool:
    if (path / ".git").is_dir():
        return True
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _git_head(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Ref materialization primitive — docs/plans/2026-08-04-publish-from-a-
# committed-ref.md C1a. `run_pre_sync_gates` reads a committed ref instead of
# the live working tree so gate-time and copy-time observe identical bytes
# by construction; this is the standalone primitive, not yet wired into any
# gate (C1b's job).
# ---------------------------------------------------------------------------
class GitMaterializeError(RuntimeError):
    """A contributing root could not be materialized from a committed ref —
    e.g. it is not inside a git work tree, or `ref` does not resolve to a
    commit there. Callers must fail the publish loud rather than fall back
    to a live-tree copy (see plan Anti-scope: a live-tree fallback would
    silently reintroduce the TOCTOU this plan closes for that root)."""


def _git_rev_parse(path: Path, *args: str) -> Optional[str]:
    """Runs `git -C <path> rev-parse <args>` and returns stripped stdout, or
    `None` on any non-zero exit or `OSError` (e.g. `git` not on `PATH`) —
    never raises, so callers decide how to fail."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


_MATERIALIZED_REF_CACHE: "dict[tuple[str, str], Path]" = {}


def _extract_git_archive(toplevel: Path, sha: str) -> Path:
    """`git archive <sha>` of the whole `toplevel` work tree (NEVER
    pathspec-scoped — a pathspec-scoped archive would drop
    `.percolate-ignore` from a single-source shadow root and silently widen
    the publish set, the exact failure class this plan removes; narrowing is
    `build_allowlisted_source`'s job, not this one's) to a temp file,
    unpacked with `tarfile.extractall(filter=...)`.

    `filter='tar'`, not `'data'`: `'data'` normalizes group/other
    permission bits, and this repo tracks 561 files at mode `100755`
    (all of `coordinator/bin/` and `bin/` — the payload of the
    `claude-klabauter-bin` publish row), whose executable bit must survive
    extraction byte-for-byte. `'tar'` still refuses absolute paths and `..`
    traversal — the safety property that matters for an archive this
    process produced itself. An explicit `filter=` is required regardless
    of choice: `DeprecationWarning` on 3.12/3.13, default flips on 3.14.

    Never a `tar` subprocess — that shell-out site is not a member of the
    closed list in `docs/reference/shell-out-carve-outs.md`.
    """
    shadow_dir = Path(tempfile.mkdtemp(prefix="claude-klabauter-publish-materialize-"))
    fd, archive_path_str = tempfile.mkstemp(prefix="claude-klabauter-publish-archive-", suffix=".tar")
    os.close(fd)
    archive_path = Path(archive_path_str)
    try:
        try:
            result = subprocess.run(
                ["git", "-C", str(toplevel), "archive", "--format=tar", "-o", str(archive_path), sha],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise GitMaterializeError(
                    f"git archive {sha!r} failed for {toplevel} (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
            with tarfile.open(archive_path) as archive:
                archive.extractall(path=shadow_dir, filter="tar")
        except Exception:
            # Review: code-reviewer Finding 1 — shadow_dir is created via
            # mkdtemp above, before either failure mode below can occur. On
            # a non-zero `git archive` or a tarfile raise (corrupt archive,
            # disk full), shadow_dir was never returned to any caller, so it
            # never enters _MATERIALIZED_REF_CACHE / GateResult.shadow_roots
            # and is unreachable to _cleanup_shadow_roots — an orphaned temp
            # dir on every failed materialization, contradicting AC9. Reclaim
            # it here before re-raising, mirroring the archive_path.unlink
            # pattern below.
            shutil.rmtree(shadow_dir, ignore_errors=True)
            raise
    finally:
        archive_path.unlink(missing_ok=True)
    return shadow_dir


def _git_materialize_ref(root: Path, ref: str = "HEAD") -> Path:
    """Materializes `root` as it exists at the committed `ref` into an
    on-disk shadow tree, and returns the shadow path corresponding to
    `root` (not the shadow of the whole toplevel).

    The unit of materialization is `(git toplevel, resolved sha)`, memoized
    for the process lifetime (`_MATERIALIZED_REF_CACHE`) — never `root`
    itself. Every contributing root across `setup/publish-targets.portable`
    's five klabauter rows is a subdirectory of this repo's own single git
    toplevel, so naively archiving per-root would do N full-tree
    extractions of the SAME commit for any row whose `source_map` routes
    multiple entries into one repo (9,854 tracked files, ~84 MiB pack, per
    row, per publish run) — and would destroy the nesting relationship
    between the real roots, since two shadow trees that should be one tree
    become disjoint copies.

    Raises `GitMaterializeError` if `root` is not inside a git work tree,
    or if `ref` does not resolve to a commit there — never falls back to a
    live-tree copy.
    """
    toplevel_str = _git_rev_parse(root, "--show-toplevel")
    if toplevel_str is None:
        raise GitMaterializeError(f"{root} is not inside a git work tree — cannot materialize {ref!r}")
    toplevel = Path(toplevel_str)

    prefix = _git_rev_parse(root, "--show-prefix") or ""

    sha = _git_rev_parse(toplevel, ref)
    if sha is None:
        raise GitMaterializeError(f"could not resolve ref {ref!r} to a commit for {toplevel}")

    cache_key = (str(toplevel), sha)
    shadow_toplevel = _MATERIALIZED_REF_CACHE.get(cache_key)
    if shadow_toplevel is None:
        shadow_toplevel = _extract_git_archive(toplevel, sha)
        _MATERIALIZED_REF_CACHE[cache_key] = shadow_toplevel

    return shadow_toplevel / prefix


def _cleanup_shadow_roots(shadow_roots: "tuple[Path, ...]") -> None:
    """Removes each materialized committed-ref shadow tree in `shadow_roots`
    (`GateResult.shadow_roots`, docs/plans/2026-08-04-publish-from-a-
    committed-ref.md C6) and evicts it from `_MATERIALIZED_REF_CACHE`.

    Eviction is required, not optional cleanliness: `_MATERIALIZED_REF_CACHE`
    is memoized for the WHOLE PROCESS lifetime (`_git_materialize_ref`'s
    docstring), and every klabauter row in `setup/publish-targets.portable`
    shares this repo's own git toplevel — so two targets processed in the
    same `publish.py` run almost always resolve the same (toplevel, sha) and
    share one cache entry. Removing a shadow tree after one target's
    iteration completes without evicting its cache entry would leave the
    NEXT target that reuses the same (toplevel, sha) holding a cached path to
    a directory that no longer exists; evicting instead makes that next
    lookup a cache miss, which re-extracts rather than reading a deleted
    tree.
    """
    for shadow_root in shadow_roots:
        shutil.rmtree(shadow_root, ignore_errors=True)
        for cache_key, cached_path in list(_MATERIALIZED_REF_CACHE.items()):
            if cached_path == shadow_root:
                del _MATERIALIZED_REF_CACHE[cache_key]


def write_lastsync_marker(setup_dir: Path, name: str, dest_dir: Path, *, dry_run: bool) -> None:
    """Records the DESTINATION repo HEAD at publish time — the pre-publish
    HEAD (before the operator commits the synced files), matching the bash
    original's documented semantics exactly. No-op in dry-run, when dest_dir
    is not a git working tree, or when HEAD cannot be resolved (e.g. an
    empty/unborn repo)."""
    if dry_run:
        return
    if not _is_git_repo(dest_dir):
        return
    dest_head = _git_head(dest_dir)
    if not dest_head:
        return
    marker_dir = setup_dir / "percolate-state"
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / f"{name}.lastsync").write_text(dest_head + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-target processing + main driver.
# ---------------------------------------------------------------------------
def _dest_has_git_ancestor(dest_dir: Path) -> bool:
    """True when `dest_dir` or any ancestor up to the filesystem root holds a
    `.git` entry. `.git` is tested with `.exists()`, not `.is_dir()`, because
    worktrees and submodules record it as a gitfile rather than a directory.

    `ResolvedTarget` carries only the fully-resolved `dest_dir` (repo root +
    dest_subdir), with no separate repo-root field, so repo membership has to
    be derived by walking upward rather than read off the row."""
    return _dest_repo_root(dest_dir) is not None


def _dest_repo_root(dest_dir: Path) -> Optional[Path]:
    """Return the nearest of `dest_dir` or its ancestors that holds a `.git`
    entry (repo root), or `None` when no ancestor up to the filesystem root
    does. Same walk as `_dest_has_git_ancestor`, but returns the resolved
    root itself rather than a bool — needed by
    `dispatch_percolate_pre_ci` to anchor the destination's own
    `.github/scripts/check-persona-names.py` checker, which only ever lands
    at the destination REPO ROOT, never at a `dest_subdir` beneath it (see
    that function's docstring)."""
    for candidate in (dest_dir, *dest_dir.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _ensure_dest_ready(target: ResolvedTarget, totals: RunTotals, *, out: IO[str] = sys.stdout) -> bool:
    """Basic sync-dispatch precondition (NOT one of the C-W1d2 gates): the
    dest path must be, or be creatable inside, a real destination repo. One
    rule for every mode.

    A missing subdirectory *inside a real git repo* is a virgin mirror that
    has simply never received this row — safe and expected to create, so it
    bootstraps. A missing directory with NO `.git` ancestor means the
    destination sigil resolved to nowhere (unset registry key, wrong clone
    path, typo); that must fail loudly rather than let `mkdir(parents=True)`
    fabricate a whole tree in the wrong place and report success. Flat-mirror
    rows previously bootstrapped unconditionally, which is exactly that hole;
    mirror rows previously refused unconditionally, which hard-skipped every
    row of a freshly created mirror repo until a human mkdir'd by hand.

    Port of setup/publish.sh."""
    if target.dest_dir.is_dir():
        return True
    if _dest_has_git_ancestor(target.dest_dir):
        warn(
            totals,
            f"Target path does not exist — bootstrapping inside the destination repo: {target.dest_dir}",
            out=out,
        )
        target.dest_dir.mkdir(parents=True, exist_ok=True)
        return True
    print(
        f"  Error: target path does not exist and is not inside a git repo "
        f"(destination unresolved, refusing to create): {target.dest_dir}",
        file=sys.stderr,
    )
    print(f"  Skipping {target.name}.", file=out)
    print("", file=out)
    return False


# ---------------------------------------------------------------------------
# Guard-before-mutate staging (state/audits/2026-08-05-first-full-payload-
# identity-findings.md — a failed post_rsync/inject/pre_ci guard used to leave
# whatever the sync dispatch had already written at the REAL destination,
# untransformed, with no rollback: one row alone had already rsynced 1014
# files before its own `no-residual-pattern` guard tripped). `process_target`
# routes every phase that can mutate the destination — the sync dispatch
# itself, the content-transform sweep + its guards, inject, and pre_ci — at a
# destination-adjacent STAGING COPY instead of `target.dest_dir`, and only
# swaps that staging copy into the real destination once every one of those
# phases has already succeeded. A raise anywhere in that sequence discards
# the staging copy; the real destination is never touched.
# ---------------------------------------------------------------------------
def _create_publish_staging_dir(dest_dir: Path) -> Path:
    """Materializes a fresh, destination-ADJACENT staging directory seeded
    with a copy of `dest_dir`'s current on-disk content (`.git` excluded),
    for a staged publish row's sync/sweep/guard/inject/pre_ci phases to run
    against instead of the real destination.

    Same filesystem as `dest_dir` by construction
    (`tempfile.mkdtemp(dir=dest_dir.parent)`) — `_swap_publish_staging_into_dest`'s
    `os.rename` calls are only cheap, atomic-as-the-OS-provides metadata
    operations when source and destination share a volume; an unqualified
    `tempfile.mkdtemp()` would resolve to the system temp dir, frequently a
    different one, and turn the swap into a full copy (or a POSIX/Windows
    cross-device `OSError`) exactly at the moment this fix is supposed to
    make cheap and safe.

    `.git` is deliberately excluded from the copy: `sync_mirror`'s own
    top-level orphan sweep already skips top-level dotfiles/dot-directories
    (state/audits' orphan-sweep invariant), so no phase this staging tree
    feeds ever needs `.git` present, and copying a repo's full history on
    every publish row for content this fix never reads would be a severe,
    unbounded cost with no correctness benefit. `_swap_publish_staging_into_dest`
    re-homes the REAL `.git` into the staged tree at swap time via a plain
    rename, not a copy — `dest_dir`'s own repo identity, never duplicated.

    `dest_dir` not yet existing (a virgin publish row, § `_ensure_dest_ready`'s
    bootstrap leg already having created it as an empty dir by the time this
    runs) yields an all-but-empty staging dir — correct, there is no prior
    content to seed it with.
    """
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{dest_dir.name}.publish-staging-", dir=str(dest_dir.parent))
    )
    if dest_dir.is_dir():
        shutil.copytree(
            dest_dir,
            staging_dir,
            ignore=shutil.ignore_patterns(".git"),
            symlinks=True,
            dirs_exist_ok=True,
        )
    return staging_dir


def _swap_publish_staging_into_dest(dest_dir: Path, staging_dir: Path) -> None:
    """Replaces `dest_dir`'s content with the fully-verified content of
    `staging_dir` (§ `_create_publish_staging_dir`) — the ONLY point in a
    staged publish row where the real destination is ever mutated, reached
    only after sync + the content-transform sweep + its guards + inject +
    pre_ci have all already succeeded against `staging_dir`.

    Every rename below is same-filesystem (`staging_dir` was created via
    `tempfile.mkdtemp(dir=dest_dir.parent)`), so each is a metadata-only
    operation on every OS this driver supports, never a full-tree copy.

    `.git` (excluded from the staging copy, § that function's docstring) is
    re-homed into `staging_dir` first via a plain rename — `dest_dir`'s own
    repo identity, never re-created or copied. The prior `dest_dir` is
    renamed aside rather than deleted outright, and only reclaimed after
    `staging_dir` has successfully taken its place — this keeps the window
    in which the destination NAME resolves to neither tree as small as a
    single `os.rename` call, on both POSIX and Windows (neither of which
    supports atomically renaming onto an existing, non-empty directory, so
    the aside-then-remove sequence is the portable shape, not a POSIX-only
    single rename)."""
    dest_git = dest_dir / ".git"
    if dest_git.exists():
        os.rename(dest_git, staging_dir / ".git")

    prior_backup = staging_dir.with_name(staging_dir.name + ".prior")
    if dest_dir.exists():
        os.rename(dest_dir, prior_backup)

    try:
        os.rename(staging_dir, dest_dir)
    except OSError:
        # Best-effort: put the prior tree back under the real name so a
        # mid-swap OSError does not strand the destination missing entirely.
        if prior_backup.exists():
            os.rename(prior_backup, dest_dir)
        raise

    if prior_backup.exists():
        shutil.rmtree(prior_backup, ignore_errors=True)


def _discard_publish_staging_dir(staging_dir: Optional[Path]) -> None:
    """Reclaims a staged publish row's staging directory on any abort path —
    the real destination was never touched in that case, so there is nothing
    to reconcile, only this throwaway tree to remove."""
    if staging_dir is not None:
        shutil.rmtree(staging_dir, ignore_errors=True)


def process_target(
    target: ResolvedTarget,
    setup_dir: Path,
    totals: RunTotals,
    *,
    identity_file_exists: bool,
    identity: Optional[PercolateIdentity],
    dry_run: bool,
    engine_ctx: PercolateEngineContext,
    percolate_store_path: Optional[Path] = None,
    publish_sync_module: object = None,
    shadow_roots_sink: "Optional[List[Path]]" = None,
    visited_files_sink: "Optional[set[Path]]" = None,
    published_dest_dirs_sink: "Optional[set[Path]]" = None,
    out: IO[str] = sys.stdout,
) -> None:
    print(f"=== {target.name} ({target.mode}) ===", file=out)
    print(f"  Source: {target.source_dir}", file=out)
    print(f"  Target: {target.dest_dir}", file=out)

    for root in _contributing_roots(target):
        if not root.is_dir():
            print(f"  Error: source path does not exist: {root}", file=sys.stderr)
            print(f"  Skipping {target.name}.", file=out)
            print("", file=out)
            return

    gate_result = run_pre_sync_gates(
        target, setup_dir, identity_file_exists, identity, totals, dry_run=dry_run, out=out
    )
    if not gate_result.proceed:
        # Individual gate checks already emitted their own "Skipping" line —
        # matches bash, where each gate's own `continue` block prints it once.
        # C6 (docs/plans/2026-08-04-publish-from-a-committed-ref.md): a gate
        # failure that occurs AFTER materialization (e.g. version-regression,
        # version-consistency) still owns shadow trees `run_pre_sync_gates`
        # already created and threaded through `shadow_roots` rather than
        # cleaning up locally — this early `return` happens BEFORE the
        # try/finally below, so it is the only point this path reaches; clean
        # up here or they leak.
        _cleanup_shadow_roots(gate_result.shadow_roots)
        return
    effective_source_dir = gate_result.source_dir
    restricted_tmp_src = gate_result.restricted_tmp_src
    # Toplevels `dispatch_percolate_inject` newly materializes during this
    # target's iteration (Review: code-reviewer Finding 2) — distinct from
    # `gate_result.shadow_roots`, since `run_pre_sync_gates` has already
    # returned by the time inject dispatches. Folded into the same run-end
    # sweep as `gate_result.shadow_roots` below (Finding 3).
    inject_shadow_toplevels: "tuple[Path, ...]" = ()
    # Guard-before-mutate staging (§ `_create_publish_staging_dir` module
    # comment) — `None` until the `else:` branch just below creates it (only
    # reached when the engine is actually going to run phases that could
    # mutate the destination); `staging_swapped` flips True only once every
    # staged phase has succeeded and `_swap_publish_staging_into_dest` has
    # actually run. The `finally` block below discards `staging_dir` on every
    # path that leaves `staging_swapped` False — every early `return` in this
    # `try`, and any exception.
    staging_dir: Optional[Path] = None
    staging_swapped = False

    try:
        if not _ensure_dest_ready(target, totals, out=out):
            return

        print("", file=out)

        # percolate-engine cutover (C-W2) — the pre_rsync phase (preserve-
        # destination-native BACKUP leg) MUST run while target.dest_dir still
        # holds the PRIOR destination tree, i.e. before the sync dispatch
        # below. Skipped under --dry-run: the engine has no non-mutating
        # preview mode (unlike the sync dispatchers below, which do), so
        # dispatching it under --dry-run would actually mutate the
        # destination tree, defeating the whole point of a preview run.
        if dry_run:
            print("  percolate engine phases: skipped (dry-run — engine has no preview mode)", file=out)
        elif engine_ctx.claude-klabauter is None or engine_ctx.store is None or percolate_store_path is None:
            print(
                f"  Error: percolate engine unavailable — refusing to publish {target.name} "
                "(AC15 fail-closed, see startup error above).",
                file=sys.stderr,
            )
            print(f"  Skipping {target.name}.", file=out)
            print("", file=out)
            return
        else:
            try:
                dispatch_percolate_pre_rsync(engine_ctx, percolate_store_path, target)
                # C-W3 item 7 — the 2 standalone Shape E guard hooks (game-dev
                # source-dir-absent against SOURCE; prune-stale-handoff-cruft
                # against DEST, pre-sync timing) — see `dispatch_standalone_guards`.
                dispatch_standalone_guards(engine_ctx, target, effective_source_dir)
            except EngineUnavailableError as exc:
                print(f"  Error: {exc}", file=sys.stderr)
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                return

            # Every phase from here through `dispatch_percolate_pre_ci` can
            # mutate a destination tree — reached only in this `else:` branch
            # (not dry-run, engine available), the same condition gating the
            # post_rsync/inject/pre_ci dispatch below. Stage now, before the
            # sync dispatch, so the sync itself also lands on the staging
            # copy rather than the real destination.
            staging_dir = _create_publish_staging_dir(target.dest_dir)

        # `sync_target` is `target` itself with `dest_dir` swapped to the
        # staging copy when one was created above — every dispatcher below
        # that writes to "the destination" reads `.dest_dir` off whichever
        # target object it is handed, so this one substitution redirects the
        # sync + every percolate-engine phase without touching their own
        # bodies. Falls back to the real `target` unchanged for dry-run and
        # engine-unavailable rows (staging_dir stays `None` there), matching
        # those paths' pre-existing behavior exactly.
        sync_target = replace(target, dest_dir=staging_dir) if staging_dir is not None else target

        if target.mode in ("mirror", "flat-mirror"):
            # `publish_sync_module` is resolved ONCE in `main()` (§ AC15,
            # chunk C11) and threaded through here — never re-imported per
            # target.
            # Review: code-reviewer Finding 5 — explicit raise, not a bare
            # `assert` (strippable under `python -O`).
            if publish_sync_module is None:
                raise ProcessTargetCallerContractError(
                    "process_target: mirror/flat-mirror target dispatched without a resolved "
                    "publish_sync_module — caller must resolve it once in main() before the loop"
                )
            # Read the row's rename-generation ledger for its PRIOR
            # directory-rename output BEFORE dispatching sync (state/audits/
            # 2026-08-05-first-full-payload-identity-findings.md Group E) --
            # this sync pass is about to recreate the pre-rename source
            # directory fresh, and this pass's own upcoming content-transform
            # sweep is about to rename it again, so the destination copy of
            # last pass's rename target must survive THIS sync's orphan
            # sweep rather than being deleted (or FATAL-aborting the whole
            # publish) as an apparent stray. Guarded on `not dry_run` and a
            # live engine explicitly (never assumed from an earlier return):
            # under `--dry-run`, or when the engine failed to import and this
            # driver degraded to a sync-only preview (§ `main`'s own
            # EngineUnavailableError/dry-run warning path), CLAUDE_KLABAUTER_ROOT may
            # never have been placed on `sys.path` at all, and this module
            # import would raise instead of degrading gracefully. `mode ==
            # "mirror"` only -- flat-mirror rows have no top-level orphan
            # sweep this exemption applies to.
            renamed_dir_names = None
            if target.mode == "mirror" and not dry_run and engine_ctx.claude-klabauter is not None:
                rewrite_basename_module = _import_percolate_rewrite_basename_module()
                ledger = rewrite_basename_module.rename_ledger_path(target.name)
                renamed_dir_names = frozenset(
                    rewrite_basename_module.read_directory_rename_ledger(ledger)
                )
            dispatch_mirror_like(
                publish_sync_module,
                sync_target,
                effective_source_dir,
                totals,
                dry_run=dry_run,
                renamed_dir_names=renamed_dir_names,
                out=out,
            )
        elif target.mode == "manifest":
            if not sync_manifest(effective_source_dir, sync_target.dest_dir, totals, dry_run=dry_run, out=out):
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                return
        else:
            print(f"  Error: unknown mode '{target.mode}'", file=sys.stderr)
            print("", file=out)
            return

        # post_rsync -> inject (separate, not phase-wired) -> pre_ci, in that
        # order (§ dispatch_percolate_inject docstring). Same dry-run skip as
        # the pre_rsync dispatch above.
        if not dry_run and engine_ctx.claude-klabauter is not None and engine_ctx.store is not None and percolate_store_path is not None:
            # `staging_dir` is guaranteed non-None here — the same condition
            # (not dry_run, engine available) is what created it above.
            # `row_visited` collects staged-path entries locally; they are
            # translated to real-destination paths and folded into the
            # caller's `visited_files_sink` below, AFTER the swap, so the
            # end-of-run unscanned-published check still sees real paths.
            row_visited: "set[Path]" = set()
            try:
                rename_manifest = dispatch_percolate_post_rsync(
                    engine_ctx,
                    percolate_store_path,
                    sync_target,
                    effective_source_dir,
                    visited_sink=row_visited,
                )
                inject_shadow_toplevels = dispatch_percolate_inject(
                    engine_ctx,
                    sync_target,
                    percolate_root=setup_dir.parent,
                    visited_sink=row_visited,
                )
                dispatch_percolate_pre_ci(
                    engine_ctx,
                    percolate_store_path,
                    sync_target,
                    effective_source_dir,
                    rename_manifest,
                    identity_dest_dir=target.dest_dir,
                )
            except EngineUnavailableError as exc:
                # A raise from dispatch_percolate_inject itself attaches
                # whatever it materialized before failing (§ that function's
                # docstring) — recover it here so the finally block below
                # still reclaims it rather than leaking it in
                # _MATERIALIZED_REF_CACHE for the rest of this process.
                inject_shadow_toplevels = getattr(exc, "materialized_shadow_roots", ())
                print(f"  Error: {exc}", file=sys.stderr)
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                # `staging_dir` is discarded by the `finally` block below
                # (`staging_swapped` stays False) — the real destination was
                # never touched by this row's sync, sweep, guards, or inject.
                return

            # Every staged phase above succeeded — swap the verified staging
            # copy into the real destination now, the ONLY point this row
            # ever mutates it.
            _swap_publish_staging_into_dest(target.dest_dir, staging_dir)
            staging_swapped = True
            if visited_files_sink is not None:
                for staged_path in row_visited:
                    rel = staged_path.relative_to(staging_dir)
                    visited_files_sink.add(target.dest_dir / rel)
            # § `dispatch_end_of_run_unscanned_published_check` fix (unscanned-
            # published-guard false-positive) — reached ONLY after this row's
            # swap has actually landed, i.e. `target.dest_dir` right now holds
            # exactly what THIS run published for it. Recorded here, not
            # derived later from `target.dest_dir.is_dir()` at check time,
            # because a dest_dir this run never reached (gate failure, --target
            # exclusion, unmatched mode) must NOT be treated as "published by
            # this run" even though it may still exist on disk from a prior run.
            if published_dest_dirs_sink is not None:
                published_dest_dirs_sink.add(target.dest_dir)

        write_lastsync_marker(setup_dir, target.name, target.dest_dir, dry_run=dry_run)

        totals.processed += 1
        print("", file=out)
    finally:
        # Guard-before-mutate staging reclaim (§ `_create_publish_staging_dir`
        # module comment) — every early `return` above and every exception
        # leaves `staging_swapped` False; discard the throwaway staging copy
        # in that case (the real destination was never touched). A `None`
        # `staging_dir` (dry-run, engine unavailable, or a `return` before
        # staging was ever created) is a no-op.
        if not staging_swapped:
            _discard_publish_staging_dir(staging_dir)
        # Allowlist restricted-tree cleanup — matches the bash original's
        # `rm -rf "$_ALLOWLIST_TMP_SRC"` at the end of each target iteration
        # (setup/publish.sh). Runs on both the success path above and
        # every early `return` inside this `try` (dest-not-ready, manifest
        # failure, unknown mode) — a restricted temp tree must never survive
        # past its target's iteration, win or lose.
        if restricted_tmp_src is not None:
            shutil.rmtree(restricted_tmp_src, ignore_errors=True)
        # Committed-ref shadow-tree reclaim (docs/plans/2026-08-04-publish-
        # from-a-committed-ref.md C6). `gate_result.shadow_roots` had to
        # OUTLIVE `run_pre_sync_gates`'s return on the success path — this
        # `try` body reads through the shadow tree via
        # `dispatch_standalone_guards`, the mirror/manifest sync,
        # `dispatch_percolate_post_rsync`, `dispatch_percolate_inject`, and
        # `dispatch_percolate_pre_ci` — so every reader for this target's
        # iteration is guaranteed done with it here, win or lose.
        #
        # Review: code-reviewer Finding 3 — this used to call
        # _cleanup_shadow_roots(gate_result.shadow_roots) directly, evicting
        # the (toplevel, sha) cache entry at the end of EVERY target's
        # iteration. The 5 klabauter rows in setup/publish-targets.portable
        # share this repo's own git toplevel and sha, so that per-target
        # eviction defeated the process-lifetime memoization
        # `_git_materialize_ref`'s docstring promises: each row re-extracted
        # the full ~84 MiB pack instead of reusing row 1's extraction.
        # `shadow_roots_sink`, when supplied (the production call site in
        # `main()` always supplies it), collects both this target's
        # `gate_result.shadow_roots` AND any `inject_shadow_toplevels`
        # (Finding 2) here instead of reclaiming them immediately — `main()`
        # sweeps the deduplicated union ONCE after its target loop, inside
        # its own `finally`, so a mid-loop exception still reclaims
        # everything accumulated so far. A caller that does not supply a
        # sink (e.g. a unit test calling `process_target` in isolation)
        # falls back to the prior per-call cleanup, unchanged.
        if shadow_roots_sink is not None:
            shadow_roots_sink.extend(gate_result.shadow_roots)
            shadow_roots_sink.extend(inject_shadow_toplevels)
        else:
            _cleanup_shadow_roots(gate_result.shadow_roots + tuple(inject_shadow_toplevels))


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="publish.py",
        description=(
            "Sync (a.k.a. percolate / push-to-publish-repo) plugin files from "
            "canonical source to downstream release repos."
        ),
    )
    p.add_argument(
        "target",
        nargs="?",
        default="",
        help="Publish to one named target only (default: all resolved targets).",
    )
    p.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    p.add_argument(
        "--full-audit",
        action="store_true",
        help="Reserved for the Phase-4 audit gate — accepted for CLI parity, not wired by this driver.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    # Review: code-reviewer Finding 2 — capture the rung that actually
    # resolved `percolate_root`/`setup_dir` here, once, and thread it into
    # every AC15 FATAL message below instead of re-deriving a fresh (and
    # potentially different) answer at each call site.
    percolate_root, percolate_root_rung = _resolve_percolate_root_and_rung()
    setup_dir = percolate_root / "setup"

    print("publish: plugin sources → downstream repos")
    if args.dry_run:
        print("(dry-run mode — no files will be modified)")
    print("")

    try:
        rows = load_targets(setup_dir, target_filter=args.target)
    except TargetsError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code if exc.code else 1

    # Fail loud on an unknown/absent --target instead of silently processing
    # zero targets and returning 0. `load_targets` raises TargetsError only
    # when the resolved set is GLOBALLY empty (see its docstring); a
    # `--target` naming an absent-but-otherwise-populated set previously fell
    # through this function's own filter loop below (`if args.target and
    # target.name != args.target: continue`) with no row ever matching,
    # printed "Done. 0 target(s) processed.", and returned 0 — cwd-
    # independent, pre-existing, and worst from the shared-install rung-4
    # path a fresh operator hits first (docs/plans/
    # 2026-08-03-klabauter-rows-relocate-into-claude-klabauter.md, C1 AMENDED).
    if args.target:
        resolved_names = sorted({row.split("|", 1)[0] for row in rows})
        if args.target not in resolved_names:
            print(
                f"[publish.py] FATAL: requested target {args.target!r} not found "
                f"under PERCOLATE_ROOT {percolate_root} (resolved via rung "
                f"{percolate_root_rung!r}). Targets present: "
                f"{', '.join(resolved_names) if resolved_names else '(none)'}.",
                file=sys.stderr,
            )
            return 1

    # percolate-engine cutover (C-W2) — resolve the engine repo's engine + load/validate
    # the store ONCE, before the target loop (both are shared preconditions
    # for every target's phase dispatch). AC15 fail-closed: on a REAL
    # (non-dry-run) run, an unreachable engine or a bad/skewed store aborts
    # the WHOLE run here — no target may publish unscrubbed content. Under
    # --dry-run, engine phases never mutate the destination (they are skipped
    # unconditionally in process_target), so a preview run degrades to
    # sync-only preview with a visible warning instead of hard-aborting.
    percolate_store_path = locate_percolate_store(setup_dir)
    engine_ctx = PercolateEngineContext(claude-klabauter=None, store=None)
    try:
        claude_klabauter_pct = _import_claude_klabauter_percolate()
        store = assert_percolate_store_ready(claude_klabauter_pct, percolate_store_path)
        engine_ctx = PercolateEngineContext(claude-klabauter=claude_klabauter_pct, store=store)
    except EngineUnavailableError as exc:
        if args.dry_run:
            print(
                f"publish.py: WARNING — percolate engine unavailable ({exc}); "
                "dry-run will preview sync only, engine phases skipped.",
                file=sys.stderr,
            )
        else:
            print(
                f"publish.py: FATAL — percolate engine unavailable, refusing to publish "
                f"any target (AC15 fail-closed, not best-effort): {exc}",
                file=sys.stderr,
            )
            return 1

    # Identity-file presence + owner/mode security gates — run ONCE here,
    # matching the bash original sourcing `.percolate-identity` once at
    # script startup (before the target loop), not per-target. An absent
    # file (AC18, C14) or an unsafe present file both abort the WHOLE run
    # (bash `exit 1`), not a single target.
    identity_path = resolve_percolate_identity_path(setup_dir)
    try:
        identity_path = check_identity_file_present(identity_path, setup_dir)
    except IdentityFileMissingError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    identity: Optional[PercolateIdentity] = None
    try:
        check_identity_file_safe(identity_path)
    except IdentityFileUnsafeError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    identity = parse_percolate_identity(identity_path)
    if not identity.review or not any(pattern.strip() for pattern in identity.review):
        example_path = setup_dir / ".percolate-identity.example"
        print(
            f"[publish.py] FATAL: {identity_path} is present but "
            "PERSONAL_REVIEW_PATTERNS is empty — refusing to run. "
            "The machine-slug detection net (warn_machine_slug_net) depends on this "
            "field; publishing with it empty leaves the Phase 4 personal-codename audit "
            "inert. Fix: copy "
            f"{example_path} to {identity_path} and edit it to populate "
            "PERSONAL_REVIEW_PATTERNS.",
            file=sys.stderr,
        )
        return 1
    # Review: code-reviewer Finding 6 — post-AC18, main() only reaches this
    # line after check_identity_file_present + check_identity_file_safe both
    # succeed, so identity_file_exists is unconditionally True here. The
    # `False` branch downstream (run_pre_sync_gates, warn_machine_slug_net)
    # is dead in the production path — it survives only for tests exercising
    # it directly in isolation. Don't go hunting for a main()-reachable
    # False case; there isn't one. The populated-PERSONAL_REVIEW_PATTERNS
    # gate above closes the remaining gap Finding 6 didn't cover: a
    # present-but-empty-patterns file previously reached warn_machine_slug_net
    # as a per-target WARN (and, for any `name` outside the
    # `coordinator-claude*`/`deep-research-claude*` prefix, not even that) —
    # it now aborts the whole run here instead, before any target is touched.
    identity_file_exists = True

    # AC15 (chunk C11) — import `publish_sync.py` ONCE here (not per-target
    # inside the mirror-dispatch loop) and assert its API contract before ANY
    # target's sync dispatch. A per-target check only fails loud "before any
    # dispatch" accidentally (whichever target happens to be first) — see
    # `check_publish_sync_contract`'s docstring for the general-detector
    # reasoning this guards.
    publish_sync_module_path = _resolve_publish_sync_module_path(setup_dir)
    try:
        publish_sync_module = _import_publish_sync(setup_dir)
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed: unimportable module
        print(
            f"[publish.py] FATAL: {publish_sync_module_path} (resolved via rung "
            f"{percolate_root_rung!r}) could not be imported: {exc}. Refusing to dispatch any "
            "mirror/flat-mirror target (AC15 fail-closed).",
            file=sys.stderr,
        )
        return 1

    try:
        check_publish_sync_contract(
            publish_sync_module, publish_sync_module_path, percolate_root_rung
        )
    except PublishSyncContractError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    totals = RunTotals()

    # Review: code-reviewer Finding 3 — the run-wide shadow-tree accumulator
    # `process_target` feeds via `shadow_roots_sink` instead of reclaiming
    # its own target's shadow trees immediately. Swept ONCE below, after the
    # loop, over the deduplicated union of every target's shadow roots —
    # `dict.fromkeys` dedups while preserving first-seen order (Path is
    # hashable) — inside this `finally` so an exception partway through the
    # loop still reclaims everything accumulated so far, never leaking the
    # rest on an abnormal exit.
    all_shadow_roots: "List[Path]" = []
    # End-of-run legs (§ `dispatch_end_of_run_identity_check` and
    # `dispatch_end_of_run_install_doc_payload_check` docstrings) — every
    # distinct destination repo root this invocation's rows resolve to,
    # collected regardless of --target filtering or of whether a given
    # row's own sync/gates succeeded: BOTH checks scan the WHOLE destination
    # tree, so what matters is which repo roots this invocation touched, not
    # which row happened to touch them. Shared between the two checks — one
    # collection pass, not two independently-drifting ones.
    end_of_run_check_roots: "List[Path]" = []
    # § `dispatch_end_of_run_unscanned_published_check` — needs each row's
    # OWN resolved section (for its `file_surface` params), not just its
    # repo root, so this is a separate accumulator rather than folded into
    # `end_of_run_check_roots` above. Only populated when the engine is
    # actually available (never under --dry-run, matching every other
    # engine-backed collection in this loop) — an empty list here is exactly
    # right for a dry-run, since that leg is skipped entirely below anyway.
    end_of_run_row_sections: "List[tuple]" = []
    # § `dispatch_end_of_run_unscanned_published_check` fix (unscanned-published-
    # guard-hole) — the REAL, executed-sweep visited set for each repo root this
    # run touches, keyed the same way `end_of_run_check_roots` resolves repo roots.
    # Populated per-row from `process_target`'s `visited_files_sink` (which
    # `dispatch_percolate_post_rsync`/`dispatch_percolate_inject` both write into),
    # then unioned in below — this is what lets the end-of-run check assert
    # against what THIS run's sweep/inject actually visited instead of
    # re-deriving eligibility via `iter_surface_files` at check time.
    end_of_run_visited_by_repo_root: "dict[Path, set[Path]]" = {}
    # § `dispatch_end_of_run_unscanned_published_check` fix (unscanned-published-
    # guard FALSE-POSITIVE on a file this invocation never published) — the set
    # of `dest_dir`s this run actually SWAPPED (§ `process_target`'s
    # `published_dest_dirs_sink`, populated only after `_swap_publish_staging_
    # into_dest` has succeeded for that row), keyed by repo root. `published`
    # (§ that function's docstring) is scoped down to files under one of these
    # dest_dirs, never the whole repo root — a file elsewhere under the repo
    # root (a prior publish, a `--target`-excluded sibling row, a row this
    # invocation skipped via a failed pre-sync gate) has no entry here and is
    # therefore correctly out of scope for THIS run's verdict, distinct from
    # `end_of_run_visited_by_repo_root` above (which scopes what was SCANNED,
    # not what was PUBLISHED).
    end_of_run_published_dest_dirs_by_repo_root: "dict[Path, set[Path]]" = {}
    try:
        for row in rows:
            target = parse_target_row(row)
            if args.target and target.name != args.target:
                continue
            repo_root = _dest_repo_root(target.dest_dir) or target.dest_dir
            end_of_run_check_roots.append(repo_root)
            if engine_ctx.claude-klabauter is not None and engine_ctx.store is not None:
                try:
                    section = engine_ctx.claude-klabauter.resolve_target(engine_ctx.store, target.name)
                    end_of_run_row_sections.append((target, section))
                except KeyError:
                    pass  # unresolvable target already surfaces via process_target's own dispatch below
            row_visited: "set[Path]" = set()
            row_published_dest_dirs: "set[Path]" = set()
            process_target(
                target,
                setup_dir,
                totals,
                identity_file_exists=identity_file_exists,
                identity=identity,
                dry_run=args.dry_run,
                engine_ctx=engine_ctx,
                percolate_store_path=percolate_store_path,
                publish_sync_module=publish_sync_module,
                shadow_roots_sink=all_shadow_roots,
                visited_files_sink=row_visited,
                published_dest_dirs_sink=row_published_dest_dirs,
            )
            end_of_run_visited_by_repo_root.setdefault(repo_root, set()).update(row_visited)
            end_of_run_published_dest_dirs_by_repo_root.setdefault(repo_root, set()).update(
                row_published_dest_dirs
            )
    finally:
        _cleanup_shadow_roots(tuple(dict.fromkeys(all_shadow_roots)))

    print("===============================")
    print(f"Done. {totals.processed} target(s) processed.")
    print(f"  Files synced:   {totals.synced}")
    print(f"  Files deleted:  {totals.deleted}")
    print(f"  Warnings:       {totals.warnings}")
    if args.dry_run:
        print("  (dry-run — no changes were made)")
        return 0

    # Never fired under --dry-run (see `dispatch_end_of_run_identity_check`
    # docstring's "Never called under --dry-run" note) — the early return
    # just above is what enforces that, not a flag threaded into the call.
    # All three legs always run (never short-circuited by an earlier one's
    # failure) so a single run surfaces every defect it can find, not just
    # the first.
    deduped_roots = list(dict.fromkeys(end_of_run_check_roots))
    identity_ok = dispatch_end_of_run_identity_check(
        engine_ctx,
        deduped_roots,
        target_filtered=bool(args.target),
    )
    install_doc_ok = dispatch_end_of_run_install_doc_payload_check(
        deduped_roots,
        target_filtered=bool(args.target),
    )
    unscanned_ok = dispatch_end_of_run_unscanned_published_check(
        end_of_run_row_sections,
        target_filtered=bool(args.target),
        visited_files_by_repo_root=end_of_run_visited_by_repo_root,
        published_dest_dirs_by_repo_root=end_of_run_published_dest_dirs_by_repo_root,
    )
    if not identity_ok or not install_doc_ok or not unscanned_ok:
        print(
            "publish.py: FATAL — end-of-run check(s) failed; treat this run's "
            "published bytes as unverified (AC15 fail-closed).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
