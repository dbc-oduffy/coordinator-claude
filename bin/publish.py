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
startup — see `main`), live-install-clobber guard,
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
`coordinator/bin/lib/cc_invoke.py`, call its `resolve_engine_root()`, then
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
import contextlib
import functools
import filecmp
import glob
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import IO, Any, Callable, List, NamedTuple, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COORDINATOR_LIB = _REPO_ROOT / "coordinator" / "lib"

GENERATES = []  # writes land only under a tempfile.TemporaryDirectory() synthetic fixture (dispatch_oss_gate_registry_fixture) or the resolved destination percolate root's lastsync marker (a foreign publish-mirror tree, not claude-klabauter's own tree)

#: Filename of the engine build stamp this publisher writes into the engine
#: row's restricted tree. Duplicated rather than imported from
#: `coordinator_core.warm.skew.ENGINE_STAMP_FILENAME`: this script runs
#: standalone against a `percolate` lib path and must not take an import
#: dependency on the very package it publishes. Pinned equal to that constant
#: by `coordinator/bin/tests/test_publish_engine_stamp.py`.
_ENGINE_STAMP_FILENAME = "_engine_stamp"

#: Repo-relative paths that count as "engine-touching" for the build stamp's
#: scoping (`_scoped_engine_stamp_sha`, below) — duplicated rather than
#: imported from `coordinator_core.warm.skew._ENGINE_TOUCHING_PATHS` for the
#: SAME reason `_ENGINE_STAMP_FILENAME` above is duplicated: this script
#: cannot import the package it publishes. This is NOT a second, independent
#: notion of "engine surface" that happens to share a name — `skew.py`'s
#: `publish_lag()` scopes its own unpublished-commit check to this identical
#: pair, and the stamp below must agree with it: a commit `publish_lag` would
#: count as engine lag is exactly the kind of commit that must rotate the
#: stamp, and a commit it would NOT count must not rotate it either, or the
#: two signals disagree about what "engine code changed" means. The two
#: definitions must never diverge; pinned equal by
#: `coordinator/bin/tests/test_publish_engine_stamp.py`, the same mechanism
#: that already pins `_ENGINE_STAMP_FILENAME` above.
_ENGINE_TOUCHING_PATHS = ("coordinator_core/", "coordinator/")


_BOOTSTRAP_DONE = False


_BOOTSTRAPPED_NAMES = (
    "_INHERITED_LOCK_ROOTS_ENV",
    "AllowlistError",
    "assert_allowlist_applied",
    "build_allowlisted_source",
    "check_working_data_paths",
    "get_pre_filter_paths",
    "parse_allowlist_csv",
    "split_inclusion_exclusion",
    "_CLOSURE_PACKAGE_NAME",
    "find_import_closure_violations",
    "run_assembled_mirror_gate",
    "format_assembled_mirror_gate_refusal",
    "find_modules_missing_tests",
    "format_test_coverage_warning",
    "PercolateIdentity",
    "parse_percolate_identity",
    "PUBLISH_MODES",
    "descriptor_for",
    "mirror_like_wire_names",
    "_is_structural_build_artifact",
    "TargetsError",
    "load_targets",
    "raw_dest_sigil_by_name",
    "_iter_portable_rows",
    "_resolve_portable_file",
    "directive_cli_arity",
    "publish_lane",
    "payload_parity",
    "_resolve_git_dir",
    "_resolve_show_toplevel",
    "_native_resolve_git_dir",
    "_native_resolve_git_common_dir",
)


def _bootstrap_engine() -> None:
    """Bind `coordinator.lib` (and this repo root) on `sys.path`, then every
    non-stdlib name this module's body used to import at MODULE scope.
    Idempotent; safe to call more than once.

    What moved, and what did NOT: this whole sequence used to run at MODULE
    scope, which made every import of this file mutate the `sys.path` of a
    warm server ~50 sessions share, and eagerly imported 13 non-stdlib
    modules on every load. The order and the comments below are preserved
    byte-for-byte; only the trigger moved.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:
        if str(_COORDINATOR_LIB) not in sys.path:
            sys.path.insert(0, str(_COORDINATOR_LIB))
        # percolate.targets resolves sibling modules via absolute `coordinator.lib.percolate.*`
        # imports, so the repo root must be importable too — else a bareword
        # `python coordinator/bin/publish.py` (the invocation docs + the /percolate skill now
        # point at) dies with ModuleNotFoundError before argparse runs.
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))

        #: D1 fix — single source of truth shared with
        #: `percolate-round.py::_INHERITED_LOCK_ROOTS_ENV` (one wire contract
        #: between the two scripts, same as the `NEW:`/`UPDATE:`/`RENAME:`
        #: change-line tags elsewhere in this pairing). See `main`'s lock loop
        #: below for the read side.
        from percolate.wire_contract import INHERITED_LOCK_ROOTS_ENV as _INHERITED_LOCK_ROOTS_ENV

        from percolate.allowlist import (  # noqa: E402
            AllowlistError,
            assert_allowlist_applied,
            build_allowlisted_source,
            check_working_data_paths,
            get_pre_filter_paths,
            parse_allowlist_csv,
            split_inclusion_exclusion,
        )
        from percolate.import_closure import (  # noqa: E402
            PACKAGE_NAME as _CLOSURE_PACKAGE_NAME,
            find_import_closure_violations,
        )
        from percolate.assembled_mirror_gate import (  # noqa: E402
            find_modules_missing_tests,
            format_refusal as format_assembled_mirror_gate_refusal,
            format_test_coverage_warning,
            run_assembled_mirror_gate,
        )
        from percolate.phase4_audit import PercolateIdentity, parse_percolate_identity  # noqa: E402

        from percolate.publish_modes import (  # noqa: E402
            PUBLISH_MODES,
            descriptor_for,
            mirror_like_wire_names,
        )
        from percolate.publish_sync import _is_structural_build_artifact  # noqa: E402
        from percolate.targets import (  # noqa: E402  (path setup must precede this import)
            TargetsError,
            load_targets,
            raw_dest_sigil_by_name,
            _iter_portable_rows,
            _resolve_portable_file,
        )

        # § chunk C4 (docs/plans/2026-08-15-bind-the-klabauter-publish-rows-into-a-
        # parity-group.md) — `directive_cli_arity` is THIS repo's own
        # `coordinator_core` module (not the resolved-engine one `PercolateEngineContext`
        # lazily imports below), so it is imported statically at module scope like
        # `percolate.*` above: `_REPO_ROOT` is already on `sys.path` (see the path
        # setup preceding the `percolate.*` imports). `argv_parity_report` itself
        # never imports or executes a target script — AST reads only — so importing
        # this module carries none of the fail-closed/engine-resolution concerns the
        # lazy `coordinator_core.percolate.*` imports below exist to guard.
        from coordinator_core import directive_cli_arity  # noqa: E402
        from coordinator_core import publish_lane  # noqa: E402
        from coordinator_core.percolate import payload_parity  # noqa: E402
        from coordinator_core.git.repo_root import git_dir as _resolve_git_dir  # noqa: E402
        from coordinator_core.git.repo_root import show_toplevel as _resolve_show_toplevel  # noqa: E402
        from coordinator_core.git.git_dir import (  # noqa: E402
            resolve_git_dir as _native_resolve_git_dir,
            resolve_git_common_dir as _native_resolve_git_common_dir,
        )

        # Publish LAST, once every name is bound -- a publish placed mid-function
        # silently omits everything imported after it, and the omission surfaces as a
        # KeyError from `__getattr__` rather than as anything pointing here.
        #
        # NEVER overwrite a name a caller already installed: a test that monkeypatches
        # one of these names on this module and then calls a function that triggers the
        # bootstrap would otherwise have its patch replaced by the real resolver on
        # the first call, and the failure reads as "the patch never applied".
    finally:
        # Publish whatever bound, EVEN IF a later import raised. A bootstrap that
        # dies partway would otherwise lose the names that did bind, and the next
        # caller sees a missing name instead of the original exception -- which is
        # a strictly worse error than the one that actually happened.
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    # Only on a clean run: a partial bootstrap must stay retryable.
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for a bootstrapped name BEFORE `main()`
    has run -- a test monkeypatching this module, or any consumer importing it
    rather than executing it -- triggers `_bootstrap_engine()` lazily instead of
    finding the name absent.

    This is the piece whose absence made the first repair pass hoist these
    imports back to module scope: deferring them alone leaves the module's own
    API missing until `main()` runs, and a `global`-bound name is module-visible
    only after its binder has been called. Only fires for names not already in
    `__dict__`, so once the bootstrap has run the plain global wins.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            # The sentinel says bootstrapped, yet this name is absent: a prior
            # partial run published some names and set nothing else. Force one
            # re-run rather than surfacing a KeyError from the line below, which
            # names the symptom and hides which import actually failed.
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


class PublishSwapPartial(OSError):
    """Raised by `_swap_publish_staging_into_dest` in two distinct
    situations, discriminated by `content_swapped`:

    - `content_swapped=True` — the new content has already landed at
      `dest_dir` (the `staging_dir -> dest_dir` rename succeeded) but
      re-homing `prior_backup / ".git"` back into `dest_dir` then failed.
      Content is current, repo metadata (`.git`) is stranded at
      `prior_backup`. The caller (`process_target`) must NOT treat this as a
      no-op failure: it still marks the row FAILED overall, but must first
      record that the published bytes DID change (`staging_swapped = True`,
      diff report emitted, sinks updated), matching this module's invariant
      that a path reported as written was actually written this run.
    - `content_swapped=False` — the refuse-on-stranded-`.prior` guard at swap
      entry found a `.prior` directory from an EARLIER incomplete swap that
      still holds a `.git`, and refused before touching `dest_dir` or
      `staging_dir` at all this run. Nothing this run did changed the
      destination; `process_target` must not record a swap."""

    def __init__(self, message: str, *, prior_backup: Path, content_swapped: bool = True) -> None:
        super().__init__(message)
        self.content_swapped = content_swapped
        self.prior_backup = prior_backup


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
    run_function_gate: "Callable[..., object]"
    run_parse_sweep: "Callable[..., object]"
    oss_shaped_subprocess_env: "Callable[..., dict]"
    find_functional_identifier_output_drift_in_tree: "Callable[..., list]"
    load_functional_identifier_output_drift_baseline: "Callable[..., object]"
    store_validation_error: type
    schema_version_error: type
    # § chunk C3 -- the executing ENTRYPOINT gate (C2's `run_entrypoint_gate`)
    # and its supporting seam: enumeration, the `mktcache` hermetic env, and
    # this repo's real two-term worker-cap derivation (`derive_worker_cap`,
    # `coordinator_core/diagnostics/contained_run.py` -- the CLAUDE.md-cited
    # `min(physical_cores/2, usable_RAM_GB*1024/150MB)` formula already has a
    # canonical home in this engine repo; reused rather than re-derived here).
    hermetic_gate_env: "Callable[..., object]"
    mktcache_gate_env: "Callable[..., object]"
    run_entrypoint_gate: "Callable[..., object]"
    enumerate_gate_entrypoints: "Callable[..., tuple]"
    derive_worker_cap: "Callable[[], int]"
    # § chunk C5 -- C4's pure, no-subprocess changed-set selector, plus the
    # engine module itself (needed only to reach C4's private closure-walk
    # helpers, `_build_first_party_import_index`/`_entrypoint_closure_
    # reaches_any`, for this driver's own always-swept-floor computation, §
    # `_compute_always_swept_entrypoints` below -- no equivalent PUBLIC seam
    # exists in engine.py for "does this entrypoint's closure reach anything
    # beyond itself", and engine.py is C4-committed, not ours to extend).
    derive_changed_entrypoints: "Callable[..., tuple]"
    percolate_engine_module: object


def _describe_engine_import_failure(engine_root: "Optional[str]", exc: Exception) -> str:
    """Failure text for `_import_claude_klabauter_percolate`'s AC15 catch-all, discriminating
    the ONE misdiagnosable shape from every other import failure.

    A publish MIRROR is a destination, not a publisher: `setup/publish-targets.
    portable` field 7 carries explicit `!ops/percolate_*.py` negations, so a
    published tree deliberately carries no percolate engine. Because
    `resolve_engine_root()` walks up from the SCRIPT'S OWN location, running the
    mirror's copy of this driver resolves the engine root TO that mirror and
    dies on `No module named coordinator_core.ops.percolate_run` — which reads
    as "publish is broken fleet-wide" when the source repo's own copy publishes
    normally. That misreading survived 9 days as
    `state/bug-backlog/2026-08-11-klabauter-mirror-ships-the-ops-registry-
    287f6526da3a` and was escalated to a P1 outage that was never true.

    Detected structurally — the resolved root has no `coordinator_core/ops/
    percolate_run.py` on disk — rather than by matching the exception text, so a
    renamed module or a genuine ImportError inside a PRESENT percolate_run.py
    still falls through to the generic message with its real cause attached.

    Returns the generic text unchanged when `engine_root` is None (the root was
    never resolved: the failure happened at or before `require_engine_on_path`).

    Names `COORDINATOR_ENGINE_ROOT`, never `CLAUDE_KLABAUTER_ROOT`, for two independent
    reasons — the first sufficient on its own (Review: code-reviewer, slice s2,
    2026-08-21, which found it):

    1. `resolve_engine_root` does not consult `CLAUDE_KLABAUTER_ROOT` at all. Post-C14 the
       dual-read window closed; `_ENGINE_ROOT_OLD_VAR` survives as a constant but
       no rung reads it. So the old advice was inert in the SOURCE tree too, with
       no mirror involved — a reader who followed it would set a variable nothing
       reads and conclude the refusal was lying.
    2. The publish transform rewrites repo-token identifiers including env-var
       NAMES, so a copy of this string living in the mirror renders as
       `CLAUDE_KLABAUTER_ROOT` — advising a reader to point the mirror's own root
       variable at a foreign checkout.

    `COORDINATOR_ENGINE_ROOT` is rung 1 in both trees and carries no repo stem, so
    it is both actually-read and transform-stable. Do not restate reason 2 as "the
    mirror's copy is the only one that reaches this branch": the branch is
    reachable from any tree whose resolved root lacks a percolate engine, and
    `publish.py` is now denied from the mirror payload (though the copy published
    before that deny is stranded there — a withdrawn top-level file is never
    deleted at a mirror destination).
    """
    if engine_root is not None:
        root = Path(engine_root)
        if not (root / "coordinator_core" / "ops" / "percolate_run.py").is_file():
            return (
                f"resolved engine root {root} is a publish destination, not a "
                f"publisher — it carries no percolate engine by design. Run the "
                f"source repo's own copy of this driver, or point "
                f"COORDINATOR_ENGINE_ROOT at that checkout."
            )
    return f"claude-klabauter percolate engine import failed: {exc}"


def _import_claude_klabauter_percolate() -> ClaudeKlabauterPercolate:
    """Resolve the engine root via the same `cc_invoke.resolve_engine_root()` shim
    (§ module docstring), then import the engine repo's percolate-engine
    surface this driver dispatches against. `resolve_engine_root()` adds a
    self-location walk-up rung ahead of the settings-home pointer / machine-
    local registry rungs `_resolve_claude_klabauter_root()` alone would fall through to
    — this driver's own file lives inside the claude-klabauter checkout, so that rung
    resolves it correctly even on an install whose registry was never
    populated.

    Raises `EngineUnavailableError` — never returns partially — on: no
    `cc_invoke.py` resolvable on any of the 3 search rungs, a
    `resolve_engine_root()` failure (raises RuntimeError when every rung
    misses), or ANY exception importing the engine repo's modules
    (missing checkout, syntax error, ImportError, etc.). This is the AC15
    engine-absent / import-failure fail-closed path.
    """
    cc_invoke_path = _locate_cc_invoke()
    if cc_invoke_path is None:
        raise EngineUnavailableError(
            "cc_invoke.py not found on any of the 3 search rungs — cannot resolve the engine root"
        )

    engine_root: Optional[str] = None
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

        engine_root = module.require_engine_on_path(__file__)

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
        # Review: staff-eng (MAJOR-2, slice-D-drift-store.md) -- the output
        # functional-identifier drift detector had no production caller;
        # bundled here so `dispatch_end_of_run_functional_identifier_output_
        # drift_check` can wire it into the same end-of-run gate sequence
        # the other legs use.
        from coordinator_core.percolate.store import (  # type: ignore[import-not-found]
            find_functional_identifier_output_drift_in_tree as
            _find_functional_identifier_output_drift_in_tree,
        )
        from coordinator_core.percolate.store import (  # type: ignore[import-not-found]
            load_functional_identifier_output_drift_baseline as
            _load_functional_identifier_output_drift_baseline,
        )
        # § chunk C3 -- the executing ENTRYPOINT gate's own seam (C2's
        # `run_entrypoint_gate`/`enumerate_gate_entrypoints`/`mktcache_gate_
        # env`, engine.py), plus this repo's canonical two-term worker-cap
        # derivation (already lives in `coordinator_core.diagnostics.
        # contained_run`, § that module's own CLAUDE.md-cited formula --
        # reused rather than re-derived a second time in this driver).
        from coordinator_core.diagnostics.contained_run import (  # type: ignore[import-not-found]
            derive_worker_cap as _derive_worker_cap,
        )
    except EngineUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-closed catch-all, AC15
        raise EngineUnavailableError(
            _describe_engine_import_failure(engine_root, exc)
        ) from exc

    return ClaudeKlabauterPercolate(
        run_percolate=_run_percolate,
        load_store=_load_store,
        resolve_target=_resolve_target,
        run_inject_for_section=_pct_engine.run_inject_for_section,
        iter_surface_files=_pct_surface.iter_surface_files,
        run_guards=_pct_guards.run_guards,
        run_identity_check=_run_identity_check,
        run_function_gate=_pct_engine.run_function_gate,
        run_parse_sweep=_pct_engine.run_parse_sweep,
        oss_shaped_subprocess_env=_pct_engine.oss_shaped_subprocess_env,
        find_functional_identifier_output_drift_in_tree=(
            _find_functional_identifier_output_drift_in_tree
        ),
        load_functional_identifier_output_drift_baseline=(
            _load_functional_identifier_output_drift_baseline
        ),
        store_validation_error=_StoreValidationError,
        schema_version_error=_SchemaVersionError,
        hermetic_gate_env=_pct_engine.hermetic_gate_env,
        mktcache_gate_env=_pct_engine.mktcache_gate_env,
        run_entrypoint_gate=_pct_engine.run_entrypoint_gate,
        enumerate_gate_entrypoints=_pct_engine.enumerate_gate_entrypoints,
        derive_worker_cap=_derive_worker_cap,
        derive_changed_entrypoints=_pct_engine.derive_changed_entrypoints,
        percolate_engine_module=_pct_engine,
    )


def locate_percolate_store(setup_dir: Path) -> Path:
    """The production DoE percolate-store the engine repo's engine consumes for every
    target (§ `setup/percolate-hooks/percolate-store.yaml`'s own header)."""
    return setup_dir / "percolate-hooks" / "percolate-store.yaml"


def assert_percolate_store_ready(engine_claude_klabauter: ClaudeKlabauterPercolate, store_path: Path) -> dict:
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
        store = engine_claude_klabauter.load_store(store_path)
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

    engine_claude_klabauter: Optional[ClaudeKlabauterPercolate]
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
    engine_claude_klabauter: ClaudeKlabauterPercolate,
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
        for _ in engine_claude_klabauter.iter_surface_files(
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
    assert engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    try:
        engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    try:
        wire = engine_claude_klabauter.run_percolate(str(store_path), target.name, str(target.dest_dir), phase="pre_rsync")
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

    assert engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    try:
        section = engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    guard_entries = [g for g in (section.get("guards") or []) if g.get("kind") == spec["kind"]]
    if not guard_entries:
        return

    check_root = effective_source_dir if spec["against"] == "source" else target.dest_dir

    try:
        results = engine_claude_klabauter.run_guards(check_root, guard_entries)
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
    sync_changed_paths: "Optional[set[str]]" = None,
) -> "tuple[Optional[list[dict]], Optional[frozenset[str]]]":
    """post_rsync phase — MUST run AFTER the driver's own sync dispatch (rsync
    equivalent) has completed: restore leg -> full content-transform sweep ->
    post_rsync guards (§ engine.py `run_post_rsync`). Computes
    `effective_source_count` from `effective_source_dir` (§
    `_compute_effective_source_count`) so the `file-count-delta` guard entry
    (coordinator-claude-toplevel-wiki) has what it needs without a store-
    declared `expected_count` fallback. A section declaring no such guard entry
    yields `None` there, forwarded unchanged as "not supplied".

    Returns the phase's `rename_manifest` (a list of `{old_path, new_path,
    kind}` dicts, § `RenameManifest.as_records()`, or `None`) — the caller
    MUST forward this unchanged into `dispatch_percolate_pre_ci` (§
    module docstring, rename-manifest reconciliation). `kind` travels on
    this shape (2026-08-14 fix, docs/plans/2026-08-14-publishing-runs-
    itself.md § C1) so a directory-kind rename does not silently downgrade
    to a file-kind record on the wire (the older flat `{old_path: new_path}`
    shape this used to carry had no room for `kind` at all). Raises
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

    `dest_prefix` (§ `_dest_prefix_for`, § engine.py `_repo_relative_path`) is now
    ALWAYS computed from `target.dest_dir` and forwarded to the wire call --
    Review: code-reviewer (Finding 1, P1). Previously omitted entirely, so every
    non-toplevel row's content-transform sweep composed attribution-surface
    checks against the wrong (target_root-relative, not repo-root-relative) path.

    `sync_changed_paths` (optional, § docs/plans/2026-08-16-percolate-round-
    timing-and-changed-only.md chunk C4, § engine.py `run_post_rsync`'s own
    param): forwarded unchanged to the wire call. `None` (the default) leaves
    the returned `changed_files` (this function's second return value)
    `None` too — undeterminable, per that param's own fail-wide contract.

    Returns `(rename_manifest, changed_files)`: `rename_manifest` is
    unchanged from this function's pre-existing single-value return (§
    docstring above); `changed_files` is the wire's `changed_files` --
    `target.dest_dir`-relative posix ids (same shape as `visited_files`), or
    `None` when undeterminable (§ `sync_changed_paths` above / engine.py
    `PhaseResult.changed_files`).
    """
    assert engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    try:
        section = engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    effective_source_count = _compute_effective_source_count(engine_claude_klabauter, effective_source_dir, section)

    try:
        wire = engine_claude_klabauter.run_percolate(
            str(store_path),
            target.name,
            str(target.dest_dir),
            phase="post_rsync",
            effective_source_count=effective_source_count,
            source_root=str(effective_source_dir),
            dest_prefix=_dest_prefix_for(target.dest_dir),
            sync_changed_paths=sync_changed_paths,
        )
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        raise EngineUnavailableError(f"{target.name}: post_rsync phase raised: {exc}") from exc

    _assert_no_guard_failures(wire.get("guard_results", []), target.name, "post_rsync")
    if visited_sink is not None:
        for relative_id in wire.get("visited_files", []):
            visited_sink.add(target.dest_dir / relative_id)
    wire_changed_files = wire.get("changed_files")
    changed_files = None if wire_changed_files is None else frozenset(wire_changed_files)
    return wire.get("rename_manifest"), changed_files


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


def _materialize_inject_srcs(
    section: dict,
    percolate_root: Optional[Path],
    round_pinned_shas: "Optional[dict[str, str]]" = None,
) -> dict:
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

    `<coordinator-content-root>` USED to be exempt: it resolves into
    `percolate_root / "coordinator"`, DoE's own separate checkout, and entries
    inside it were passed through live-tree-sourced on the reasoning that
    materializing a sibling's checkout means reading a tree claude-klabauter does not
    own (the original plan's "Out of scope"). That exemption is removed — PM
    ruling, 2026-08-18. It shipped whatever bytes happened to be sitting in
    DoE's working tree, so an uncommitted local edit in a sibling checkout
    reached a published artifact with nothing recording where it came from,
    which is the exact hole AC6 exists to close and which C1/C1b closed for
    every other row. Negative spec: ownership governs WRITES, not reads —
    materializing reads a sibling's committed ref and writes only claude-klabauter's
    own shadow tree, so "a tree claude-klabauter does not own" was never a reason the
    bytes could go ungated. A DoE-checkout `src` that is uncommitted, or that
    sits in no git work tree at all, now fails the publish loud rather than
    silently publishing live bytes.

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
    # A caller that passes no pin (direct unit-test use of
    # `dispatch_percolate_inject`) gets a call-scoped dict, matching
    # `run_pre_sync_gates`' own None-handling — one pin per call rather than
    # one per round, which is exactly today's behaviour for those callers.
    if round_pinned_shas is None:
        round_pinned_shas = {}
    resolved_entries = []
    for entry in inject_entries:
        resolved_entry = dict(entry)
        src = resolved_entry.get("src", "")
        src_path = Path(src)
        if src_path.is_absolute():
            resolved_src_path = src_path.resolve()
            # `_git_materialize_ref`/`_git_rev_parse` shell `git -C <root>`,
            # which requires a DIRECTORY — a file `src` (today's only real
            # entry, the vendored LICENSE) made `-C` fail and this raise
            # GitMaterializeError unconditionally, blocking every publish
            # of this row. Resolve the git root from the containing
            # directory for a file entry, then re-append the filename.
            git_root = src_path if resolved_src_path.is_dir() else src_path.parent
            # Round-pinned sha, never a fresh `ref="HEAD"` read
            # (§ `_round_pin_source_sha`). C4/AC6 closed the hole where
            # injected payload bypassed materialization altogether, but it
            # resolved HEAD per call, so C1b's round-pin amendment never
            # reached this site: on a box where peers commit during a round,
            # the injected CI-harness files materialized from a LATER commit
            # than the sha the round pinned, printed as `Provenance: ...
            # shipped from <sha>`, and promised as reproducible. One publish,
            # two commits, one provenance line -- and a second full-tree
            # extraction (~40s on a 26k-file tree) to produce it.
            # `late=True`: inject runs during per-row processing, by
            # definition after `main`'s round-start pinning pass.
            sha = _round_pin_source_sha(git_root, round_pinned_shas, late=True)
            shadow_root = _git_materialize_ref(git_root, ref=sha)
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
    round_pinned_shas: "Optional[dict[str, str]]" = None,
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

    `dest_prefix` (§ `_dest_prefix_for`, § engine.py `_repo_relative_path`) is now
    ALWAYS computed from `target.dest_dir` and forwarded to `run_inject_for_section`
    -- Review: code-reviewer (Finding 1, P1), same gap as
    `dispatch_percolate_post_rsync`'s wire call: previously omitted, so injected
    content on a non-toplevel row was scrubbed with the wrong composed path.

    Raises `EngineUnavailableError` (AC15) on any engine failure.
    """
    assert engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    try:
        section = engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    section = _resolve_inject_src_placeholders(section, percolate_root)
    _cache_before = set(_MATERIALIZED_REF_CACHE.values())
    section = _materialize_inject_srcs(section, percolate_root, round_pinned_shas)
    newly_materialized = tuple(
        shadow for shadow in _MATERIALIZED_REF_CACHE.values() if shadow not in _cache_before
    )

    try:
        engine_claude_klabauter.run_inject_for_section(
            target.dest_dir,
            section,
            stdin=io.StringIO(""),
            visited_sink=visited_sink,
            dest_prefix=_dest_prefix_for(target.dest_dir),
        )
    except Exception as exc:  # noqa: BLE001 - AC15 phase-raise fail-closed path
        wrapped = EngineUnavailableError(f"{target.name}: inject raised: {exc}")
        wrapped.materialized_shadow_roots = newly_materialized  # type: ignore[attr-defined]
        raise wrapped from exc

    return newly_materialized


def _resolve_identity_checker_source_script(
    engine_claude_klabauter: Any,
    store: dict,
    percolate_root: Optional[Path],
) -> Optional[Path]:
    """Locate THIS RUN's source-of-truth for `.github/scripts/
    check-persona-names.py`, independent of which row `dispatch_percolate_pre_ci`
    is currently evaluating.

    Root cause this closes: a publish round judges every row's identity by
    whatever `check-persona-names.py` copy the DESTINATION already happens to
    carry (§ `dispatch_percolate_pre_ci` docstring) — a prior run's stale
    output, not this run's ruling. This run's ruling is the checker this
    repo's OWN working tree ships for delivery, discoverable the same way
    `dispatch_percolate_inject` finds it: the store's `inject` entry with
    `dst == ".github"` naming `scripts/check-persona-names.py` in
    `required_children` (today: `claude-klabauter-publish-repo-toplevel`'s
    entry, `percolate-store.yaml`) — walked generically across every declared
    target rather than hardcoding that target name, so a second store/target
    that ships the same checker is picked up without a code change here.

    Returns the resolved absolute path to the SOURCE `check-persona-names.py`
    file (not the `.github` dir, not the `scripts` dir), or `None` when no
    declared target's `inject` carries this checker at all — e.g. a store
    exercised in a unit test with no persona-checker entry. Callers treat
    `None` as "nothing to refresh from" and fall back to scanning whatever
    the destination already carries, unchanged from pre-fix behavior.
    """
    for target_name in store.get("targets") or {}:
        try:
            section = engine_claude_klabauter.resolve_target(store, target_name)
        except KeyError:
            continue
        section = _resolve_inject_src_placeholders(section, percolate_root)
        for entry in section.get("inject") or []:
            dst = str(entry.get("dst", "")).strip("/")
            required_children = entry.get("required_children") or []
            names_checker = any(
                str(child).replace("\\", "/") == "scripts/check-persona-names.py"
                for child in required_children
            )
            if dst == ".github" and names_checker:
                src = entry.get("src")
                if not src:
                    continue
                return Path(src) / "scripts" / "check-persona-names.py"
    return None


def _refresh_identity_checker_at_dest(
    scan_dest: Path,
    source_script: Optional[Path],
) -> str:
    """`pre_ci` PRECONDITION (§ module docstring, overturning the prior C6
    advisory-staleness acceptance below): overwrite `<scan_dest>/.github/
    scripts/check-persona-names.py` with `source_script`'s current bytes
    BEFORE any row's identity check runs, so the check always judges this
    run's own ruling rather than whatever a prior run's stale destination
    copy happened to carry.

    Deliberately scoped to a REFRESH, not a create: only overwrites when the
    destination file already exists. Creating a checker that has genuinely
    never been published to this destination is the `identity_result[
    "skipped"]` advisory-skip case one call site up in
    `dispatch_percolate_pre_ci` — a legitimate ordering (a subdir row running
    before the toplevel row has ever placed `.github/`), not this
    precondition's job to paper over by fabricating a file.

    Only the files the identity check actually executes are touched — not
    the other 15 files `.github/` ships (`run-all-checks.py`, the other 8
    checkers, allowlists, templates) — keeping this precondition's write
    footprint on a possibly-live destination tree minimal and exactly
    scoped to the drift class this closes.

    TWO files, not one, and the second is why this docstring changed. The
    checker `import`s its sibling `_repo.py` (file enumeration, the
    `SKIP_DIR_NAMES` exclusion set, gitignore fallback), so a meaningful part
    of "this run's own ruling" lives there rather than in the entry point.
    Refreshing only the entry point left the destination's stale `_repo.py`
    deciding WHICH FILES get scanned while the fresh script decided what
    counts as a finding — the precondition's own stated goal, unmet for half
    its logic.

    It also produced a DEADLOCK, which is the concrete reason this is a fix
    and not a tidy-up. `.github/` reaches the mirror through the toplevel row.
    When the identity check fails, that row does not land. So a correction
    made in `_repo.py` — the exclusion set being exactly where a
    false-positive fix belongs — could never take effect: the round it must
    fix is the round that refuses to ship it. Observed 2026-08-25 on
    `claude-klabauter`, where a `.percolate` exclusion added to `_repo.py`
    was live in source and inert at the destination across two consecutive
    rounds.

    Each file is refreshed independently and fail-open in the same shape as
    before: a missing sibling is reported in the currency note, never raised,
    so a destination that predates `_repo.py` is not turned into a hard
    failure by this precondition.

    Returns a short currency note for the failure message this call's
    caller builds: "refreshed from source" on a successful overwrite,
    "source not found in store" when `source_script` is None, or "refresh
    skipped, dest has no existing checker" when there is nothing to
    overwrite yet.
    """
    if source_script is None:
        return "no source checker declared in this store's inject entries — currency unverified"
    dest_script = scan_dest / ".github" / "scripts" / "check-persona-names.py"
    if not dest_script.is_file():
        return f"no existing checker at {dest_script} to refresh (nothing overwritten)"
    if not source_script.is_file():
        return f"declared source checker {source_script} does not exist on disk — currency unverified"
    shutil.copyfile(source_script, dest_script)

    note = f"refreshed from source ({source_script}) immediately before this check"

    # The imported sibling, refreshed on the same terms. Absence on either
    # side is a note, never a raise: this precondition must not convert a
    # destination or store shape it does not recognise into a failed round.
    source_repo_mod = source_script.parent / "_repo.py"
    dest_repo_mod = dest_script.parent / "_repo.py"
    if not source_repo_mod.is_file():
        return f"{note}; sibling _repo.py absent at source — its currency unverified"
    if not dest_repo_mod.is_file():
        return f"{note}; no existing _repo.py at dest to refresh (nothing overwritten)"
    shutil.copyfile(source_repo_mod, dest_repo_mod)
    return f"{note} (with its imported sibling _repo.py)"


def dispatch_percolate_pre_ci(
    engine_ctx: PercolateEngineContext,
    store_path: Path,
    target: "ResolvedTarget",
    effective_source_dir: Path,
    rename_manifest: "Optional[list[dict]]",
    *,
    identity_dest_dir: Optional[Path] = None,
    percolate_root: Optional[Path] = None,
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
    `run_percolate` guards, but ONLY for the row whose `scan_dest` resolves to
    its OWN staging tree (`scan_dest == target.dest_dir`, below) — genuinely
    guard-before-mutate, since that staged content is about to be swapped
    into the real destination. Every other row's `scan_dest` is the mirror
    root itself, unstaged; re-scanning it once per such row cost ~28-33s per
    row for the byte-identical tree (state/audits/2026-08-16-percolate-round-
    first-measured-cost-distribution.md) — `dispatch_end_of_run_identity_check`
    scans that same tree once per repo root, unconditionally, after the round,
    so the per-row scan is dropped for those rows rather than duplicated. When
    it runs, it folds a failure into the SAME `_assert_no_guard_failures` list
    those guards populate rather than raising through a second, out-of-band
    channel — one design call, made deliberately:
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
    assert engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None  # narrowed by caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    try:
        section = engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
    except KeyError as exc:
        raise EngineUnavailableError(
            f"{target.name}: not declared in percolate-store.yaml targets — cannot dispatch"
        ) from exc

    effective_source_count = _compute_effective_source_count(engine_claude_klabauter, effective_source_dir, section)

    _run_percolate_start = time.perf_counter()
    try:
        wire = engine_claude_klabauter.run_percolate(
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
    finally:
        print(
            f"  [timing] {target.name}: dispatch_percolate_pre_ci: run_percolate: "
            f"{time.perf_counter() - _run_percolate_start:.3f}s",
            file=sys.stdout,
        )

    guard_results = list(wire.get("guard_results", []))

    real_dest_dir = identity_dest_dir if identity_dest_dir is not None else target.dest_dir
    identity_dest = _dest_repo_root(real_dest_dir)
    if identity_dest is None:
        identity_dest = real_dest_dir
        identity_dest_note = f"{identity_dest} (no .git ancestor found; used dest_dir as-is)"
    else:
        identity_dest_note = str(identity_dest)

    # C6 (a gate that reads the stale destination can never let the fix
    # through): when this row's repo root resolves to its OWN real
    # destination (i.e. this row itself publishes the repo root, not a
    # subdir under a sibling toplevel row's repo), `target.dest_dir` is the
    # STAGED tree about to be swapped into that real destination (§
    # `process_target`'s guard-before-mutate staging — `target` here is
    # `sync_target`, whose `dest_dir` is the staging copy, while
    # `identity_dest_dir`/`real_dest_dir` is threaded through separately as
    # the REAL path, needed above only to walk the on-disk `.git` ancestor
    # chain). Scanning `identity_dest` (the real, still-stale tree) in that
    # case is the deadlock this fix closes: a publish that would overwrite
    # the very file tripping the checker can never pass a gate that reads
    # what's already there instead of what's about to be written. A sibling
    # toplevel row's repo root (this row's `dest_dir` is a subdirectory) has
    # no staged content available here — that row stages and swaps
    # independently in its own `process_target` call.
    #
    # SUPERSEDED (this fix): that sibling-row fallback used to scan the real,
    # possibly-stale tree unchanged and call the result advisory-acceptable —
    # "the real (possibly stale) tree" was itself the finding, not a bug.
    # It is a bug: a publish round that judges every row by whatever
    # `check-persona-names.py` copy the destination happened to be carrying
    # BEFORE this run started is judging this run's content against a rule
    # this run may have already retired (state/audits/2026-08-14 diagnosis —
    # PM ruling in commit 500e6b298 deleted the DoE/DoE-claude ban patterns
    # from the SOURCE checker; a stale destination copy still carries them).
    # `_refresh_identity_checker_at_dest` below is the fix: a `pre_ci`
    # PRECONDITION that overwrites the checker AT `scan_dest` with this run's
    # own source bytes before the check runs, so both branches below are
    # judged by this run's ruling, not a prior run's leftovers.
    scan_dest = identity_dest
    if identity_dest == real_dest_dir and target.dest_dir != real_dest_dir:
        scan_dest = target.dest_dir
        identity_dest_note = f"{identity_dest_note} (scanning staged content at {scan_dest})"

    # C-round-scan (measured: run_identity_check cost 27.7-33.0s on EVERY one
    # of 8 rows, ~225s/~30% of one round, six of them scanning the byte-
    # identical `scan_dest` — state/audits/2026-08-16-percolate-round-first-
    # measured-cost-distribution.md): the per-row scan below now runs ONLY
    # for the row whose `scan_dest` is its OWN staging tree (`scan_dest ==
    # target.dest_dir`, the branch just above) — genuinely guard-before-
    # mutate, since that staged content is about to be swapped into the real
    # destination and nothing else will ever scan it before the swap. Every
    # other row's `scan_dest` is the mirror root itself: read-only, no
    # commit/add/push/checkout/reset anywhere in this module, nothing leaves
    # the machine between rows (percolate-round.py commits once, afterward,
    # in a separate process), and `dispatch_end_of_run_identity_check`
    # already scans that same final tree once per repo root, unconditionally,
    # after every row (including a failed/skipped one) has had its chance to
    # write. A later row cannot hide an earlier row's leak from that scan —
    # enumeration is `git ls-files --cached --others --exclude-standard`, and
    # no declared row writes into an ignored/skipped directory — so re-
    # scanning the identical mirror root once per subdir row bought nothing
    # this round's own end-of-run leg does not already cover.
    if scan_dest == target.dest_dir:
        source_checker_script = _resolve_identity_checker_source_script(
            engine_claude_klabauter, engine_ctx.store, percolate_root
        )
        currency_note = _refresh_identity_checker_at_dest(scan_dest, source_checker_script)
        # Surfaced on every run, not only a failing identity check: a refresh
        # that silently fails (no declared source, or source missing on disk)
        # plus a stale dest checker that happens to PASS would otherwise leave
        # zero record anywhere that currency was never established.
        print(f"  {target.name}: identity checker currency: {currency_note}", file=sys.stderr)

        _identity_check_start = time.perf_counter()
        try:
            identity_result = engine_claude_klabauter.run_identity_check(str(scan_dest))
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            raise EngineUnavailableError(f"{target.name}: identity check raised: {exc}") from exc
        finally:
            print(
                f"  [timing] {target.name}: dispatch_percolate_pre_ci: run_identity_check: "
                f"{time.perf_counter() - _identity_check_start:.3f}s "
                f"(scan_dest={scan_dest})",
                file=sys.stdout,
            )

        # The checker's scanned/checked counts are emitted on the passing path, not
        # only on failure: a count that reveals how much a gate actually walks is
        # worthless if it appears only once the gate has already gone wrong. A
        # ranking error of three orders of magnitude survived precisely because this
        # number existed and stayed unprinted
        # (state/audits/2026-08-16-percolate-round-first-measured-cost-distribution.md).
        if identity_result["ran"]:
            # Review: skipped is always False on this branch (run_identity_check's
            # two return shapes are mutually exclusive) — exit_code varies instead.
            print(
                f"  [timing] {target.name}: identity check: exit_code={identity_result['exit_code']}: "
                f"{identity_result['findings'].strip()}",
                file=sys.stderr,
            )

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
                        f"checker currency: {currency_note}. "
                        f"{identity_result['findings'].strip()}"
                    ),
                }
            )
    else:
        print(
            f"  {target.name}: pre_ci per-row identity scan skipped — "
            f"scan_dest ({scan_dest}) is the mirror root, not this row's own "
            "staging tree; covered once for the whole repo root by the "
            "end-of-run identity scan instead.",
            file=sys.stderr,
        )

    _assert_no_guard_failures(guard_results, target.name, "pre_ci")


def _attribute_identity_finding_row(
    finding_line: str,
    rows: "List[ResolvedTarget]",
) -> "Optional[ResolvedTarget]":
    """Maps one `check-persona-names.py` finding line
    (`"{rel}:{lineno}: ..."`, repo-root-relative POSIX path) to the row
    whose `dest_subdir` (§ `_dest_prefix_for`) is the LONGEST prefix of
    `rel` — the toplevel row (`dest_subdir == ""`) is the fallback when no
    subdir row's prefix matches. `None` only when `rows` is empty."""
    rel = finding_line.split(":", 1)[0].strip().replace("\\", "/")
    best: "Optional[ResolvedTarget]" = None
    best_len = -1
    fallback: "Optional[ResolvedTarget]" = None
    for row in rows:
        prefix = _dest_prefix_for(row.dest_dir)
        if prefix == "":
            if fallback is None:
                fallback = row
            continue
        if rel == prefix or rel.startswith(prefix + "/"):
            if len(prefix) > best_len:
                best = row
                best_len = len(prefix)
    return best if best is not None else fallback


def _attribute_identity_findings(
    findings: str,
    rows: "List[ResolvedTarget]",
    skipped_row_names: "List[str]",
) -> str:
    """Annotates each non-blank line of `findings` (§ `run_identity_check`'s
    `"findings"` key) with the row `_attribute_identity_finding_row`
    resolves it to, and whether that row published THIS run or was
    `--delta`-skipped (in which case the finding is pre-existing in that
    row's subtree, not introduced by this round) — recovers, at no extra
    scan, the per-row attribution the dropped per-row scan (C-round-scan)
    used to give away for free. Lines this call cannot attribute (no rows
    given) pass through unchanged."""
    if not rows:
        return findings
    annotated: "List[str]" = []
    for line in findings.splitlines():
        if not line.strip():
            continue
        row = _attribute_identity_finding_row(line, rows)
        if row is None:
            annotated.append(line)
            continue
        status = "skipped this run (pre-existing)" if row.name in skipped_row_names else "published this run"
        annotated.append(f"{line}  [row: {row.name}, {status}]")
    return "\n".join(annotated) if annotated else findings


def dispatch_end_of_run_identity_check(
    engine_ctx: PercolateEngineContext,
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
    percolate_root: Optional[Path] = None,
    rows_by_repo_root: "Optional[dict[Path, List[ResolvedTarget]]]" = None,
    skipped_row_names: "Optional[List[str]]" = None,
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

    C-round-scan HOIST (§ `dispatch_percolate_pre_ci`'s per-row scan
    reduced to the toplevel row only): the `_resolve_identity_checker_
    source_script` -> `_refresh_identity_checker_at_dest` PRECONDITION pair
    moves here, once per `repo_root`, immediately before `run_identity_
    check` — `dispatch_percolate_pre_ci`'s own per-row refresh, for the
    subdir rows that no longer scan, is gone with it, and this function
    performed NO refresh before this change; without moving it, a repo root
    whose toplevel row was skipped or failed would have this backstop scan
    under a STALE checker, reintroducing by the back door the exact "judged
    by a prior run's leftovers" defect the C6 comment in `dispatch_
    percolate_pre_ci` exists to close. `percolate_root` is threaded through
    for `_resolve_identity_checker_source_script`'s placeholder resolution;
    `None` (e.g. a caller with no store-backed target set) degrades to
    "nothing to refresh from", same as that function's own contract.

    `rows_by_repo_root`/`skipped_row_names` (optional, default `None`/
    unattributed) recover per-row attribution for a failing finding — §
    `_attribute_identity_findings` — since the dropped per-row scan used to
    give that away for free via which row's own check failed. Passing
    `None` for either degrades to the pre-attribution behaviour (raw
    `findings` text, no `[row: ...]` suffix).
    """
    assert engine_ctx.engine_claude_klabauter is not None  # narrowed by caller (never called under dry-run)
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    ok = True
    for repo_root in repo_roots:
        source_checker_script = _resolve_identity_checker_source_script(
            engine_claude_klabauter, engine_ctx.store, percolate_root
        )
        currency_note = _refresh_identity_checker_at_dest(repo_root, source_checker_script)
        print(f"  end-of-run identity check ({repo_root}): checker currency: {currency_note}", file=sys.stderr)
        try:
            identity_result = engine_claude_klabauter.run_identity_check(str(repo_root))
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
            findings_text = identity_result["findings"].strip()
            rows_for_root = (rows_by_repo_root or {}).get(repo_root, [])
            if rows_for_root:
                findings_text = _attribute_identity_findings(
                    findings_text, rows_for_root, skipped_row_names or []
                )
            print(
                f"  Error: end-of-run identity check FAILED for {repo_root}: "
                f"check-persona-names.py exited {identity_result['exit_code']} — "
                f"{findings_text}",
                file=sys.stderr,
            )
            ok = False

    return ok


# Minimum-viable FUNCTION-gate seed set (§ chunk C4B brief "What to gate
# on", plan chunk C4): coordinator_registry itself, plus both data_root
# twins (`coordinator/bin/lib/coordinator_data_root.py`,
# `coordinator_core/data_root.py`) — the modules C4's own design doc names
# as the floor, out of the 32 `coordinator/bin` CLIs that import
# `coordinator_registry`. Each entry is (repo-root-relative file path,
# dotted module name to import from a hermetic subprocess whose cwd is the
# repo root).
#
# ROT RISK (named per brief, not silently hardcoded): this seed set does
# NOT grow automatically when a NEW `coordinator/bin` CLI starts importing
# `coordinator_registry` — only these 3 modules are ever gated. A CLI added
# or removed from the 32-CLI surface never changes what this function
# checks. Presence in the WRITTEN PAYLOAD is still checked dynamically (§
# `_function_gate_modules_and_search_paths_for_repo_root` below) so a repo
# root that legitimately never ships one of these three (a `--target`-
# scoped row that only ever touches a subtree) is not gated on a module it
# never published — but widening WHICH modules are seeded here is a
# deliberate, manual follow-up, not something this chunk automates.
_FUNCTION_GATE_SEED_MODULES: "tuple[tuple[str, str], ...]" = (
    ("coordinator/bin/lib/coordinator_registry.py", "coordinator_registry"),
    ("coordinator/bin/lib/coordinator_data_root.py", "coordinator_data_root"),
    ("coordinator_core/data_root.py", "coordinator_core.data_root"),
)


def _function_gate_in_scope_seed_entries(rel_root: str) -> "List[tuple[str, str]]":
    """Which `_FUNCTION_GATE_SEED_MODULES` entries (unchanged `rel_path`,
    `module_name` pairs) are IN SCOPE for a row whose resolved dest sits
    `rel_root` (`_dest_prefix_for(target.dest_dir)`) below its repo root —
    i.e. whose seed entry's repo-relative `rel_path` starts with `rel_root`
    (a toplevel row, `rel_root == ""`, is in scope for all three). Shared
    identity basis for both the presence probe below and the pre-swap
    gate's EXPECTED-SUBSET assertion (§ chunk C1 brief AC4) — `rel_path` is
    the stable identity compared on both sides, never a module name that
    the probe itself may rewrite (see `_function_gate_modules_and_search_
    paths_for_repo_root`'s own docstring).

    Unaffected by the toplevel destination-layout narrowing applied by
    `_function_gate_expected_seed_rel_paths_for_rel_root` (§ its own
    docstring) — that narrowing lives entirely in the EXPECTED-set
    derivation, not here, so the presence probe below keeps testing all
    three literal nested paths regardless of the destination's own
    layout, exactly as before this chunk."""
    if not rel_root:
        return list(_FUNCTION_GATE_SEED_MODULES)
    prefix = f"{rel_root.rstrip('/')}/"
    # Review: code-reviewer — bare str.startswith relies on an invariant this
    # function does not enforce: _FUNCTION_GATE_SEED_MODULES is a fixed
    # 3-entry tuple with no accidental rel_path prefix-stem overlap. A future
    # 4th seed entry sharing a rel_root prefix stem with a sibling directory
    # would degrade this check silently rather than asserting the mismatch.
    return [(rel_path, name) for rel_path, name in _FUNCTION_GATE_SEED_MODULES if rel_path.startswith(prefix)]


def _function_gate_expected_seed_rel_paths_for_rel_root(
    rel_root: str, staging_dir: "Path | None" = None
) -> "frozenset[str]":
    """The `rel_path` identities (§ `_function_gate_in_scope_seed_entries`)
    expected for a row whose `dest_subdir` is `rel_root`. Used by the
    pre-swap gate (§ chunk C1 brief AC4) to assert EXPECTED-SUBSET EQUALITY
    against what actually resolved in the row's own staging tree, never
    bare non-emptiness — four of six live rows (`docs/reference`,
    `docs/install`, `bin`, `scripts`) legitimately expect the empty set
    here (none of the three seed `rel_path`s fall under their
    `dest_subdir`), and an unconditional non-empty assertion would red
    every publish on the box.

    A FIFTH legitimately-empty case, distinct from the four `dest_subdir`-
    scoped ones above, applies only at `rel_root == ""`: a row whose staged
    payload is FLAT at its destination root — no `coordinator/` or
    `coordinator_core/` top-level directory at all — can never contain any
    of the three seed `rel_path`s, however complete its own publish is.
    `target.mode == "flat-mirror"` is NOT this discriminator on its own:
    `coordinator-claude`'s main `mode == "mirror"` row also lands flat at
    its destination root — its `source_map` (`plugin-source:project-
    claude-klabauter/coordinator=bin,lib`) renames `coordinator/bin` and `coordinator/
    lib` to the dest-relative top-level names `bin`/`lib`, so its own
    staged tree never contains a `coordinator/` directory either, same as
    the two genuinely `flat-mirror`-mode rows. Reconciled against the
    row's OWN STAGED layout instead (`staging_dir`, DESTINATION-LAYOUT
    RECONCILIATION over parsing `source_map`/`allowlist` syntax): each seed
    `rel_path`'s own top-level path component (`"coordinator"` for the two
    bare entries, `"coordinator_core"` for the dotted one) is checked for
    presence as a DIRECTORY under `staging_dir` — not the seed `rel_path`
    itself, which is exactly what the resolved leg (§
    `_function_gate_modules_and_search_paths_for_repo_root`) already
    checks. Testing the coarser directory-presence signal here, rather
    than re-running the same literal-file probe the resolved leg runs,
    keeps this an independent EXPECTED-SUBSET assertion instead of a
    tautology: a row whose `coordinator/` directory genuinely landed but
    is missing one seed file inside it (a real regression) still expects
    that entry and still fails the equality check, exactly as before.
    An EMPTY `staging_dir` is not a flat payload — it is a row that staged
    nothing. Directory-presence alone cannot tell those apart, and reading
    absence as "legitimately flat" would degrade this gate from "assert the
    payload landed" to "assert whatever landed is self-consistent" for
    exactly the total-staging-failure case it exists to catch: expected and
    resolved would both collapse to the empty set and the row would swap
    through. The narrowing therefore requires at least one staged entry;
    a row that produced nothing keeps the full all-three expectation and
    fails. A row that staged SOME of a nested payload but lost
    `coordinator/` specifically is still admitted here — no live row is
    nested at `rel_root == ""` (every row carrying `coordinator/` or
    `coordinator_core/` lands at a non-empty `dest_subdir`), so that case
    is currently held off by row configuration rather than by this code.

    `staging_dir=None` (a caller that predates this, or a `rel_root !=
    ""` call — the `coordinator_core` row's own mis-rooting check never
    reaches this branch at all) falls back to the pre-existing
    all-three-toplevel behavior, unchanged."""
    entries = _function_gate_in_scope_seed_entries(rel_root)
    if not rel_root and staging_dir is not None and any(staging_dir.iterdir()):
        entries = [
            (rel_path, name)
            for rel_path, name in entries
            if (staging_dir / rel_path.split("/", 1)[0]).is_dir()
        ]
    return frozenset(rel_path for rel_path, _ in entries)


def _function_gate_modules_and_search_paths_for_repo_root(
    repo_root: Path,
    rel_root: str = "",
) -> "tuple[List[str], List[str], frozenset]":
    """Build the module list, `search_paths`, AND resolved `rel_path`
    identity set to gate for one repo root FROM WHAT IS ACTUALLY IN THE
    WRITTEN PAYLOAD (§ brief "Build the module list from what is actually
    in the written payload, not a hardcoded list") — each
    `_FUNCTION_GATE_SEED_MODULES` entry is included only if its file
    genuinely exists under `repo_root` right now; a repo root that never
    published a given module (a `--target`-scoped single-row debug
    publish, or a row whose dest tree legitimately never ships
    `coordinator/bin/`) silently omits it from the gate rather than gating
    on a module the payload never shipped.

    `rel_root` (§ chunk C1 of docs/dispatch-briefs/2026-08-21-the-payload-
    proves-itself-before-it-overwrites-the-engine/C1.md) is `""` for a
    genuine repo root (the end-of-run caller, unchanged behavior) or a
    row's own `dest_subdir` (`_dest_prefix_for(target.dest_dir)`) when
    `repo_root` is actually a per-row STAGING dir rather than a repo root —
    a `coordinator_core` row's staging dir holds `data_root.py` at its own
    root, not `coordinator_core/data_root.py`, so each in-scope seed
    entry's `rel_path` (§ `_function_gate_in_scope_seed_entries`) has
    `rel_root` stripped to get the STAGED relative path, and that staged
    path is what is actually probed for presence and searched for import
    under `repo_root`.

    `module_name` is adjusted the SAME way for a DOTTED entry whose name is
    itself the dotted form of `rel_path` (`coordinator_core.data_root`,
    resolved against `repo_root` as a genuine package root via the `""`
    search path) — the same `rel_root` prefix, dotted, is stripped from
    the module name so the STAGED import target matches the STAGED file
    location (`coordinator_core.data_root` -> `data_root` when `rel_root`
    is `coordinator_core`, since the staged tree has no `coordinator_core/`
    directory of its own to import through). A BARE entry
    (`coordinator_registry`, `coordinator_data_root` — resolved via their
    own containing directory on `PYTHONPATH`, never dotted against the
    root) is untouched either way: its own `search_dir` is already
    computed from the staged `rel_path`, so no name rewrite is needed for
    it to keep resolving correctly.

    `search_paths` always includes `""` (resolves to `repo_root` itself in
    `run_function_gate`, § that function's `prepend` derivation) so a
    package-rooted dotted import resolves against the repo root, plus each
    present seed entry's own containing directory (`coordinator/bin/lib`
    for the bare two, relative to `rel_root` the same way the staged file
    path itself is).

    The returned `frozenset` is the resolved `rel_path` identity set (§
    `_function_gate_expected_seed_rel_paths_for_rel_root`) — the pre-swap
    gate compares this against the expected set for AC4, never the
    (possibly rewritten) `modules` list itself.
    """
    modules: "List[str]" = []
    search_paths: "set[str]" = {""}
    resolved_rel_paths: "set[str]" = set()
    prefix = f"{rel_root.rstrip('/')}/" if rel_root else ""
    dotted_prefix = f"{rel_root.rstrip('/').replace('/', '.')}." if rel_root else ""
    for rel_path, module_name in _function_gate_in_scope_seed_entries(rel_root):
        staged_rel_path = rel_path[len(prefix):] if prefix else rel_path
        if not (repo_root / staged_rel_path).is_file():
            continue
        # Review: code-reviewer — same fixed-3-entry invariant as
        # _function_gate_in_scope_seed_entries's rel_path prefix check above:
        # bare str.startswith on dotted_prefix relies on no accidental
        # module-name stem overlap across the hardcoded seed set.
        staged_module_name = (
            module_name[len(dotted_prefix):]
            if dotted_prefix and module_name.startswith(dotted_prefix)
            else module_name
        )
        modules.append(staged_module_name)
        resolved_rel_paths.add(rel_path)
        search_dir = str(PurePosixPath(staged_rel_path).parent)
        search_paths.add("" if search_dir == "." else search_dir)
    return modules, sorted(search_paths), frozenset(resolved_rel_paths)


#: Minimal, SYNTHETIC coordinator-registry manifest body for `_synthetic_
#: registry_manifest_overrides` below -- same shape
#: `test_gate_fires_hermetically_on_synthetic_manifest_fixture`'s own
#: `_minimal_manifest()` builds (`coordinator_core/percolate/tests/
#: test_function_gate.py`). Schema conformance of a REAL manifest is DoE-
#: claude's own contract, tested on their side (§ `docstring
#: dispatch_end_of_run_function_gate` below) -- this fixture only needs to be
#: shaped enough for `coordinator_registry`'s bootstrap to accept it and
#: import cleanly, not to be a realistic production manifest.
_SYNTHETIC_REGISTRY_MANIFEST_FIXTURE = {
    "docTypes": [
        {"type": "plan", "isSidecar": False},
        {"type": "review", "isSidecar": True, "suffix": "review"},
    ],
    "queueTypes": ["queue-delegate"],
    "identity": {
        "repoAliases": [{"registryKey": "repos.doe_claude", "shortname": "doe-claude"}],
        "centralReceiverIds": ["doe-claude-em"],
    },
}


@contextlib.contextmanager
def _synthetic_registry_manifest_overrides():
    """Stage a minimal, SYNTHETIC coordinator-registry manifest fixture and
    yield the `hermetic_gate_env(overrides=...)` mapping that anchors a
    resolvable plugin-install rung at it -- promoting the tested shape
    `test_gate_fires_hermetically_on_synthetic_manifest_fixture` builds by
    hand (`coordinator_core/percolate/tests/test_function_gate.py`) into
    this production gate, exactly as `hermetic_gate_env`'s own docstring
    names as the intended `overrides` consumer.

    NEVER points at a real installed plugin, the ambient dev-box install, or
    DoE-claude's own tree. `publish.py` BLOCKER-2 (§ `dispatch_end_of_run_
    function_gate`'s docstring, `hermetic_gate_env`'s own docstring)
    deliberately removed ambient `HOME`/`USERPROFILE`/`CLAUDE_HOME`
    passthrough because that let the gate evaluate the payload against the
    PUBLISHING BOX'S OWN coordinator-claude install rather than the payload
    alone -- green on a dev box that happens to have one, silently unproven
    for an OSS user who does not. Anchoring this rung at anything ambient
    would revert BLOCKER-2 with extra steps. The fixture staged here is
    synthetic and minimal on purpose, and is torn down when this context
    exits.

    `docs/install/agent-install-manifest.json` declares `coordinator-claude`
    as `direct_deps[0]` with `severity: "hard"` -- claude-klabauter's own published
    install contract already states a coordinator-claude install (which
    ships this manifest) is a hard prerequisite. Staging a resolvable
    manifest here asserts exactly that shipped contract: the gate proves the
    payload imports cleanly GIVEN a conformant manifest at the plugin root,
    not that one happens to be sitting on whichever box runs the publish.

    ENUMERATION (2026-08-10, klabauter-mirror gate closure) -- which OTHER
    plugin-install-provided data dirs the two end-of-run gates can demand at
    STARTUP, derived from code rather than from iterating live-run failures:

      - FUNCTION gate: imports exactly the three `_FUNCTION_GATE_SEED_
        MODULES` (`coordinator_registry`, `coordinator_data_root`,
        `coordinator_core.data_root`). All three resolve `data_root()`
        LAZILY, inside a function body, never at import time (see
        `coordinator_data_root.py`'s own "Import-time purity" negative-
        spec) -- so a bare import demands nothing beyond the manifest
        already staged above.

      - ENTRYPOINT gate: runs `--help` for every entry `enumerate_gate_
        entrypoints()` returns, which is BARE (extensionless) files under
        `coordinator/bin` and `coordinator/scripts` only -- `.py`-suffixed
        CLIs (e.g. `sync-cockpit-contract.py`, `verify-schema-registry-
        sync.py`, `fan-out-integrator.py`, `doctor-catalog-gen.py`, `gen-
        claude-doe-shim.py`) are explicitly out of that gate's scan scope
        (§ `enumerate_gate_entrypoints` docstring), so whatever data dirs
        THEY touch at startup is irrelevant here even though several of
        them also call `coordinator_data_root.data_root()`. A source sweep
        of all 72 bare entrypoints under those two scan roots (`grep` for
        `data_root`/`coordinator_data_root` across every one, verified
        2026-08-10) found exactly ONE that references it at all:
        `coordinator/bin/snippet-registry`, whose `_resolve_plugin_root()`
        calls `data_root("snippets")` unconditionally in `main()`, before
        any subcommand (including an unrecognized `--help`) is dispatched.
        No other bare entrypoint imports or calls it, directly or
        transitively -- the set is therefore CLOSED, not open-ended: exactly
        one additional dir, "snippets", beyond the manifest's own "schemas".

    PRINCIPLE: this fixture stages what the DECLARED HARD DEPENDENCY
    (coordinator-claude, `agent-install-manifest.json` `direct_deps[0]`)
    provides and what the SHIPPED, GATE-SCANNED entrypoints actually consume
    at process startup -- nothing more. `snippets/registry.toml` is staged
    with the minimal valid shape `coordinator_core.snippet_sync.registry.
    load_registry()` accepts (`schema_version = 1`, no `[snippet.*]` rows)
    -- enough for `snippet-registry` to resolve its data dir and parse the
    registry without crashing; it still exits 1 on `--help` (an
    unrecognized subcommand, printed via its own usage block) exactly like
    the six other CLIs the 2026-08-10 C6 sweep already classified this way,
    which is `_USAGE_NONZERO_ENTRYPOINTS`' concern, not this fixture's.
    """
    with tempfile.TemporaryDirectory(prefix="oss-gate-registry-fixture-") as fixture_root:
        fixture_root_path = Path(fixture_root)

        plugin_root = fixture_root_path / "plugin_root"

        # BOTH legitimate layouts are staged, at the SAME plugin_root -- not a
        # choice between them. `coordinator_data_root.data_root()`'s own
        # `_cdr_manifest_present()` (coordinator/bin/lib/coordinator_data_root.py)
        # and `coordinator_registry.py`'s import-time `_MANIFEST_PATH` bootstrap
        # (`_mp_candidate_manifest_path`) both already probe OSS-flat
        # (`<root>/schemas/...`) AND private DoE-repo (`<root>/coordinator/
        # schemas/...`) unconditionally, and `.doe-root` pointer semantics are
        # the DoE-claude REPO ROOT (a directory THAT HAS a `coordinator/`
        # subdir) -- so a conformant real install satisfies the private shape
        # at this same root, not merely the flat one. A caller like
        # `emit-artifact-shape-contract`'s `_resolve_coordinator_root()` that
        # hardcodes `doe_root() + "/coordinator"` unconditionally (never
        # routing through the dual-layout-aware `data_root()`/`_cdr_manifest_
        # present()` probe) only ever resolves the private shape -- staging
        # flat alone left it demanding a `<plugin_root>/coordinator/schemas`
        # directory this fixture never created. Mirroring both trees here
        # (identical content, two locations) costs nothing at fixture-build
        # time and matches what a real install actually presents rather than
        # picking whichever single layout the CURRENT failure set happens to
        # exercise.
        for _content_root in (plugin_root, plugin_root / "coordinator"):
            _schemas_dir = _content_root / "schemas"
            _schemas_dir.mkdir(parents=True)
            (_schemas_dir / "coordinator-registry.manifest.json").write_text(
                json.dumps(_SYNTHETIC_REGISTRY_MANIFEST_FIXTURE), encoding="utf-8", newline="\n"
            )

            # A minimal, valid *.yaml schema record -- `coordinator_core.
            # frontmatter.schema_validate.load_schemas()` (this dir's OTHER
            # reader, besides the manifest read above) enumerates every
            # `*.yaml`/`*.schema.json` file here and, given zero, raises its
            # own "SCHEMAS is empty -- refusing to emit an empty contract"
            # business failure (`coordinator_core/ops/emit_artifact_shape_
            # contract.py`) -- a real install always ships at least the
            # registered doc-type schemas the manifest's own `docTypes` names.
            # `schema: <name>` is the only field `load_schemas()` requires
            # (name defaults to the filename otherwise); no `required`/
            # `optional`/`applies_to` block is needed for the JSON-Schema
            # translator below it, which reads each via `.get(...)` and
            # tolerates absence.
            (_schemas_dir / "synthetic-fixture-doc.yaml").write_text(
                "schema: synthetic-fixture-doc\n", encoding="utf-8", newline="\n"
            )

            # § docstring ENUMERATION above -- the other data dir a shipped,
            # gate-scanned (bare) entrypoint demands at startup:
            # `coordinator/bin/snippet-registry`'s `_resolve_plugin_root()` ->
            # `data_root("snippets")`. A minimal, schema-valid `registry.toml`
            # (no snippet rows) is enough for `load_registry()` to accept it
            # without raising -- see `coordinator_core.snippet_sync.registry.
            # load_registry`'s `schema_version` check. Mirrored at both
            # layouts for the same reason the schemas dir is above -- `data_
            # root()` itself is dual-layout-aware and tries the private
            # candidate FIRST (§ that function's own docstring), so leaving
            # only the flat copy would silently rely on the private candidate
            # missing rather than proving both rungs resolvable.
            _snippets_dir = _content_root / "snippets"
            _snippets_dir.mkdir(parents=True)
            (_snippets_dir / "registry.toml").write_text("schema_version = 1\n", encoding="utf-8", newline="\n")

        settings_home = fixture_root_path / "settings_home"
        machine_local_dir = settings_home / "machine-local"
        machine_local_dir.mkdir(parents=True)
        (machine_local_dir / ".doe-root").write_text(str(plugin_root) + "\n", encoding="utf-8", newline="\n")

        yield {"COORDINATOR_SETTINGS_HOME": str(settings_home)}


def dispatch_end_of_run_function_gate(
    engine_ctx: PercolateEngineContext,
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
) -> bool:
    """FUNCTION gate (chunk C4B, wiring C4's `run_function_gate` into the
    driver — AC3): for each distinct destination repo root this
    invocation's rows resolve to, import the seed module set (§
    `_FUNCTION_GATE_SEED_MODULES`) that is actually present in the WRITTEN
    payload, in a hermetic subprocess whose environment carries none of
    the private registry keys or env vars, and whose HOME/USERPROFILE/
    CLAUDE_HOME are anchored to a fresh, isolated, empty temp directory
    rather than the real ones (`hermetic_gate_env`, C4/BLOCKER-2, same
    engine module — never hand-rolled here). A payload that cannot import
    its own entrypoint modules fails the publish.

    ALSO runs `engine_claude_klabauter.run_parse_sweep` (§ chunk C4C) over every `.py`
    file in the same repo root, BEFORE the seed-module import check, and
    independently of whether the seed set has anything present to gate
    (import-reachability and total-parse coverage are orthogonal — see
    `run_parse_sweep`'s own docstring for why neither leg subsumes the
    other). A repo root can fail on the parse sweep alone even when every
    seed module (if any are present) imports cleanly.

    Run ONCE per distinct destination repo root (same shape as
    `dispatch_end_of_run_identity_check` /
    `..._install_doc_payload_check`), after every row has synced — the
    gate needs the FULLY ASSEMBLED tree, same reason those two legs are
    end-of-run rather than per-row.

    SEVERITY — a deliberate departure from `dispatch_end_of_run_
    identity_check`/`..._install_doc_payload_check`'s advisory-under-
    `--target` split, and the judgement call this chunk's brief asks to be
    stated explicitly: **this leg is FAIL-HARD unconditionally, filtered
    or not.** Unlike those two legs, there is no cross-row "a sibling row
    hasn't synced yet" dependency for a single module's own importability
    — `_function_gate_modules_and_search_paths_for_repo_root` already
    scopes the gate down to modules the payload actually shipped, so
    `target_filtered` narrows WHICH modules are even considered (exactly
    like `dispatch_end_of_run_unscanned_published_check`'s own
    `target_filtered` docstring note), never whether a module that WAS
    shipped and does NOT import is excused. AC3 reads "the publish
    pipeline fails when the payload cannot import its own entrypoint
    modules" — an advisory-only gate here would reproduce the exact "a
    callable nobody enforces" gap this chunk exists to close (the leak
    gate's blind spot survived on advisory reporting alone; see this
    chunk's own brief). `target_filtered` is still accepted, for call-site
    symmetry with the other three legs and because a future caller may
    want it, but it does not change severity in this function's body —
    documented explicitly rather than silently unused.

    Returns True iff every repo root's present seed modules all imported
    cleanly; False iff any present module failed to import or the gate
    itself could not run. Never raises — same reporting contract as the
    other three end-of-run legs. Never called under `--dry-run` (same
    reason as the other three; see `dispatch_end_of_run_identity_check`'s
    docstring and `main`'s dry-run early return).

    WHAT THIS GATE ACTUALLY ASSERTS: the published payload imports cleanly
    GIVEN a conformant `coordinator-registry.manifest.json` at the plugin
    root, and nothing else from the ambient environment. It is narrower than
    "the payload works" -- manifest-SCHEMA conformance (are the fields
    right, do the doc types resolve, etc.) remains DoE-claude's own
    contract, tested on their side; this gate only proves importability
    given a manifest shaped enough for `coordinator_registry`'s bootstrap to
    accept.

    The "resolvable manifest" rung is a SYNTHETIC, minimal fixture staged
    per-call by `_synthetic_registry_manifest_overrides` and injected via
    `hermetic_gate_env`'s own `overrides` parameter -- the exact seam its
    docstring names as the intended consumer, and the same construction
    `test_gate_fires_hermetically_on_synthetic_manifest_fixture`
    (`coordinator_core/percolate/tests/test_function_gate.py`) builds by
    hand. It is deliberately NEVER the ambient dev-box install, a real
    installed plugin, or DoE-claude's own tree: `publish.py` BLOCKER-2
    stripped ambient `HOME`/`USERPROFILE`/`CLAUDE_HOME` passthrough
    precisely because that let this gate evaluate the payload against the
    PUBLISHING BOX'S OWN coordinator-claude install rather than the payload
    alone -- green on a dev box that happens to have one, silently unproven
    for an OSS user who does not. Anchoring the manifest rung at anything
    ambient reverts BLOCKER-2 with extra steps; do not "simplify" this into
    an ambient lookup. `docs/install/agent-install-manifest.json` names
    `coordinator-claude` as `direct_deps[0]` with `severity: "hard"`, so
    requiring a resolvable manifest here asserts exactly the shipped install
    contract, not something stricter or looser than it.
    """
    assert engine_ctx.engine_claude_klabauter is not None  # narrowed by caller (never called under dry-run)
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    ok = True
    for repo_root in repo_roots:
        if not repo_root.is_dir():
            continue

        # Parse sweep FIRST (§ C4C brief "the FUNCTION gate must parse the
        # payload, not just import three modules"): total, shallow coverage
        # of every .py file in the payload -- catches a broken module
        # nothing imports (run_function_gate's own blind spot, § its
        # complement docstring on engine_claude_klabauter.run_parse_sweep). Runs
        # regardless of whether the seed-module import check below has
        # anything to gate on for this repo root.
        #
        # Review: staff-eng (MINOR-4) -- wrapped in try/except so an
        # unguarded `root.rglob("*")` walk raising (Windows MAX_PATH,
        # junction loop, permission-denied directory) cannot escape this
        # function as a bare traceback, contradicting `run_parse_sweep`'s
        # own "Never raises" docstring promise -- the operator gets the
        # AC15 FATAL line instead, same as every other failure mode here.
        try:
            parse_result = engine_claude_klabauter.run_parse_sweep(repo_root)
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run function gate raised during parse sweep "
                f"for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        if not parse_result.ok:
            print(
                f"  Error: end-of-run function gate FAILED for {repo_root}: "
                f"{len(parse_result.failures)} of {parse_result.scanned} .py "
                f"file(s) in the written payload failed to parse:",
                file=sys.stderr,
            )
            for failure in parse_result.failures:
                lineno = failure.lineno if failure.lineno is not None else "?"
                print(f"    {failure.path}:{lineno}: {failure.message}", file=sys.stderr)
            ok = False

        modules, search_paths, _resolved_rel_paths = _function_gate_modules_and_search_paths_for_repo_root(repo_root)
        if not modules:
            continue

        try:
            # Review: staff-eng (BLOCKER-2) -- bare `oss_shaped_subprocess_
            # env()` carries HOME/USERPROFILE/CLAUDE_HOME through from the
            # real environment, so this gate evaluated the payload against
            # the PUBLISHING BOX'S OWN coordinator-claude install rather
            # than the payload alone (A/B-verified: production env passes,
            # the same call with those three keys pointed at an empty
            # directory fails with a manifest-not-found error). `hermetic_
            # gate_env` forces them onto a fresh, isolated, empty temp
            # directory per call instead, per the module's own "gate on a
            # fixture, not the ambient environment" design constraint.
            #
            # Director-of-Engineering ruling (option (a), scoped to the
            # manifest-import failure class only; see this function's own
            # docstring "WHAT THIS GATE ACTUALLY ASSERTS" section) -- give
            # the hermetic smoke-run a resolvable plugin-install rung, so a
            # bare engine mirror (which never ships DoE-claude's manifest by
            # design) does not fail this gate by construction on every
            # publish. `_synthetic_registry_manifest_overrides` stages a
            # SYNTHETIC fixture, never an ambient one (§ BLOCKER-2, same
            # docstring), and `hermetic_gate_env`'s `overrides` parameter is
            # applied last, so this rung wins over the isolated-home
            # defaults without reopening ambient leakage.
            with _synthetic_registry_manifest_overrides() as manifest_overrides:
                with engine_claude_klabauter.hermetic_gate_env(overrides=manifest_overrides) as env:
                    result = engine_claude_klabauter.run_function_gate(
                        repo_root,
                        modules,
                        env=env,
                        search_paths=search_paths,
                    )
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run function gate raised for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        if not result.ok:
            print(
                f"  Error: end-of-run function gate FAILED for {repo_root}: "
                f"module {result.failed_module!r} could not be imported in a "
                f"hermetic, OSS-shaped subprocess (modules gated: "
                f"{list(result.modules)!r}) — {result.error}\n{result.stderr}",
                file=sys.stderr,
            )
            ok = False

    return ok


def dispatch_preswap_function_gate(
    engine_ctx: PercolateEngineContext,
    target: "ResolvedTarget",
    staging_dir: Path,
    *,
    out: IO[str] = sys.stdout,
) -> bool:
    """PRE-SWAP FUNCTION gate (chunk C1,
    state/dispatch-briefs/2026-08-21-the-payload-proves-itself-before-it-
    overwrites-the-engine/C1.md): the same seed-module import check
    `dispatch_end_of_run_function_gate` runs END-OF-RUN, run PER-ROW
    against the STAGED tree in `process_target`, immediately before
    `_swap_publish_staging_into_dest` — a failure here refuses the swap for
    THIS row, before it ever overwrites the destination. Additive to the
    end-of-run leg, which remains the cross-root backstop (a mis-rooting
    bug in a future repo-root shape this leg does not cover).

    `staging_dir` is NOT a repo root — it is `target.dest_dir`'s own
    subtree in isolation (§ `_create_publish_staging_dir`), rooted at
    whatever `_dest_prefix_for(target.dest_dir)` (the row's `dest_subdir`)
    is beneath the real destination repo root. The `coordinator_core` row
    stages `data_root.py` at ITS OWN root, not at
    `coordinator_core/data_root.py` — feeding `staging_dir` through the
    end-of-run gate's repo-root-shaped probe unmodified misses all three
    `_FUNCTION_GATE_SEED_MODULES` entries (`modules == []`), silently
    degrading to parse-sweep-only on the one row that matters (§ this
    chunk's own brief for the concrete miss). `rel_root` (derived here via
    `_dest_prefix_for`) corrects both the seed-presence probe and the
    search-path derivation for that offset (§
    `_function_gate_modules_and_search_paths_for_repo_root`).

    AC4 — EXPECTED-SUBSET EQUALITY, never bare non-emptiness:
    `_function_gate_expected_seed_rel_paths_for_rel_root` derives which
    seed entries (by `rel_path` identity) THIS row's `rel_root` is even in
    scope for; asserting the resolved `rel_path` set against that expected
    set (not merely "resolved is non-empty") is what keeps the four rows
    that legitimately ship none of
    the three seed modules (`docs/reference`, `docs/install`, `bin`,
    `scripts`) green while still catching the `coordinator_core` row's own
    mis-rooting (an unconditional non-empty assertion would red every
    publish on the box; a bare `continue`-on-empty would silently pass a
    row whose probe missed for the wrong reason).

    A row whose staged payload is flat at `rel_root == ""` — no top-level
    `coordinator/`/`coordinator_core/` directory in `staging_dir` at all —
    is a SIXTH legitimately-empty case alongside the four `dest_subdir`-
    scoped ones: its destination can never contain any of the three seed
    entries there, however complete the row's own publish is (§
    `_function_gate_expected_seed_rel_paths_for_rel_root`'s own docstring,
    which reconciles against `staging_dir`'s OWN layout rather than
    `target.mode` — a `mode == "mirror"` row can land just as flat as a
    `mode == "flat-mirror"` one, via its own `source_map`/allowlist
    contribution). `staging_dir` is passed through for this row alone —
    it does not affect the `coordinator_core` row's own mis-rooting check
    above, which stays keyed on `rel_root` alone (`staging_dir` is a no-op
    for any nonempty `rel_root` call, § that function's own docstring).

    Preconditions the end-of-run caller gets for free via its own
    `not dry_run` narrowing, and this per-row caller must establish itself
    (§ chunk brief item 1): `engine_ctx.engine_claude_klabauter` is asserted
    non-`None` directly here — `process_target` only reaches this call
    inside its own `not dry_run and engine_ctx.engine_claude_klabauter is not None
    and engine_ctx.store is not None` branch (the same condition that
    creates `staging_dir` in the first place), so the assert below holds by
    construction for TODAY'S only caller. The `assert` is the actual safety
    net; this paragraph describes `process_target`'s current narrowing, not
    a property a future caller inherits for free.

    Returns True iff the resolved module set exactly equals the expected
    subset for this row's `rel_root` AND every resolved module (if any)
    imports cleanly in a hermetic, OSS-shaped subprocess; False otherwise.
    Never raises — same fail-closed reporting contract as the end-of-run
    leg (§ AC15)."""
    assert engine_ctx.engine_claude_klabauter is not None  # safety net: holds for process_target's current not-dry-run/engine-available branch, not guaranteed for a future caller
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter

    rel_root = _dest_prefix_for(target.dest_dir)
    modules, search_paths, resolved_rel_paths = _function_gate_modules_and_search_paths_for_repo_root(
        staging_dir, rel_root
    )
    expected_rel_paths = _function_gate_expected_seed_rel_paths_for_rel_root(rel_root, staging_dir=staging_dir)

    if resolved_rel_paths != expected_rel_paths:
        print(
            f"  Error: pre-swap function gate FAILED for {target.name}: resolved seed "
            f"module set {sorted(resolved_rel_paths)!r} does not equal the expected subset "
            f"{sorted(expected_rel_paths)!r} for dest_subdir {rel_root!r} — mis-rooted "
            "seed-presence probe.",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    if not modules:
        return True

    try:
        with _synthetic_registry_manifest_overrides() as manifest_overrides:
            with engine_claude_klabauter.hermetic_gate_env(overrides=manifest_overrides) as env:
                result = engine_claude_klabauter.run_function_gate(
                    staging_dir,
                    modules,
                    env=env,
                    search_paths=search_paths,
                )
    except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as end-of-run leg
        print(
            f"  Error: pre-swap function gate raised for {target.name}: {exc}",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    if not result.ok:
        print(
            f"  Error: pre-swap function gate FAILED for {target.name}: module "
            f"{result.failed_module!r} could not be imported in a hermetic, "
            f"OSS-shaped subprocess (modules gated: {list(result.modules)!r}) — "
            f"{result.error}\n{result.stderr}",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    return True


# § chunk C4 (state/dispatch-briefs/2026-08-26-payload-parity-asks-an-index-not-
# the-payload/C4.md, AC8) — the round's own token-index maintenance leg.
# MODULE-LEVEL, not closures inside `main`: AC8's three branches (an
# undetermined root, a refused row, a `PublishSwapPartial` root) are only
# assertable if the call they route through can be reached without driving a
# whole publish round, and `coordinator/bin/publish.py` maps to no test target
# in this plan's spine, so nothing else would have exercised them.


def _token_index_paths(root: "Path") -> "tuple[Path, Path]":
    from coordinator_core.ops.percolate_build_token_index import (  # noqa: PLC0415 - lazy, engine import
        _CURSOR_FILENAME,
        _INDEX_DIRNAME,
        _INDEX_FILENAME,
    )

    index_dir = root / _INDEX_DIRNAME
    return index_dir / _INDEX_FILENAME, index_dir / _CURSOR_FILENAME


def _invalidate_token_index(root: "Path") -> None:
    """The single "invalidate this root" call every AC8 branch routes through
    — deletes the index and its build cursor so the next round's round-entry
    check (§ C3) treats this root as cold and pays the full scan once, rather
    than trusting a stale-but-covered entry.

    Idempotent: a root with no index on disk is already in the state this
    call establishes, so invalidating twice, or invalidating a cold root, is
    a no-op rather than an error."""
    index_path, cursor_path = _token_index_paths(root)
    index_path.unlink(missing_ok=True)
    cursor_path.unlink(missing_ok=True)


def _token_index_action_for_root(
    root: "Path",
    *,
    invalidate_roots: "set[Path]",
    undetermined_roots: "set[Path]",
) -> str:
    """`"invalidate"` or `"update"` for one repo root, naming AC8's branch
    disposition in one place rather than spreading it across the manifest
    loop's control flow.

    `"invalidate"` for a root whose changed set is UNDETERMINED
    (`row_changed_files is None`) or that carries a
    `PublishSwapPartial(content_swapped=True)` row — in both cases a stamp
    that still reads fresh would be worse than no index at all. A REFUSED row
    never swapped, so it contributes nothing to either set and needs no
    branch of its own: `"update"` over a delta it is absent from leaves its
    files exactly as the index already had them."""
    if root in invalidate_roots or root in undetermined_roots:
        return "invalidate"
    return "update"


def _update_token_index_from_delta(
    root: "Path", changed: "set[Path]", removed: "set[Path]"
) -> None:
    """Fold THIS round's own already-recorded delta into an existing on-disk
    index. A root whose index was never built (cold — no file at
    `index_path`) is left alone: building it is the round-entry trigger's/C3's
    job, never this round's initiative (§ `token_index`'s own negative-spec)."""
    from coordinator_core.percolate.payload_parity import _TOKEN_RE  # noqa: PLC0415 - lazy, engine import
    from coordinator_core.percolate.token_index import (  # noqa: PLC0415
        FileStamp,
        SliceResult,
        apply_update,
        load_index,
        serialize_index,
    )
    from coordinator_core.wire_paths import rel_id  # noqa: PLC0415

    index_path, _cursor_path = _token_index_paths(root)
    if not index_path.is_file():
        return
    index = load_index(index_path)
    tokens_by_file: "dict[str, frozenset[str]]" = {}
    stamps: "dict[str, Any]" = {}
    # Review: coordinator:code-reviewer -- filter to `.py`, matching
    # `_iter_py_files_sorted`'s own scope, so an incremental fold can never
    # diverge from what a cold build over the same tree would ever produce.
    for dest_path in changed:
        if dest_path.suffix != ".py":
            continue
        rel = rel_id(dest_path, root)
        # Post-swap `os.stat` of the DEST path, taken here — after every row
        # for this root has already swapped (§ this function's call site in
        # `main`, after the row loop) — never a staging-side stat, and never
        # optimistic. A dest path missing or unreadable at stamp time drops
        # it from coverage rather than guessing (§ `token_index`'s
        # negative-spec).
        try:
            stat = dest_path.stat()
            blob = dest_path.read_bytes()
        except OSError:
            continue
        text = blob.decode("utf-8", errors="replace")
        tokens_by_file[rel] = frozenset(_TOKEN_RE.findall(text))
        stamps[rel] = FileStamp(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    removed_rel = {
        rel_id(dest_path, root) for dest_path in removed if dest_path.suffix == ".py"
    }
    slice_result = SliceResult(
        tokens_by_file=tokens_by_file,
        stamps=stamps,
        resume_after=None,
        files_visited=len(tokens_by_file),
        done=True,
    )
    apply_update(index, slice_result, removed=removed_rel)
    serialize_index(index, index_path)


def dispatch_preswap_payload_parity_gate(
    target: "ResolvedTarget",
    staging_dir: Path,
    changed_files: "frozenset[str]",
    *,
    token_index_path: "Optional[Path]" = None,
    out: IO[str] = sys.stdout,
) -> bool:
    """PRE-SWAP PAYLOAD-PARITY gate (chunk C2, state/dispatch-briefs/2026-08-
    21-the-payload-proves-itself-before-it-overwrites-the-engine/C2.md):
    binds every first-party call site in (a) this row's own changed files
    and (b) any other payload file whose token set intersects a signature-
    changed function name, against the STAGED callee's own signature --
    refuses the swap on an unbindable call (unexpected kwarg / missing
    required parameter / arity overflow), the 2026-08-21 outage shape
    (`equivalence_map=` surviving a dropped parameter on the callee 11
    minutes before the caller caught up).

    Lands in the SAME pre-swap slot `dispatch_preswap_function_gate`
    occupies (chunk C1), additive to it -- neither replaces the other, and
    both run against the fully-assembled `staging_dir` immediately before
    `_swap_publish_staging_into_dest`.

    `rel_root` (`_dest_prefix_for(target.dest_dir)`) is threaded through so
    this row's own module-prefix vocabulary matches what a genuine repo
    root would produce (§ `payload_parity.build_first_party_import_index`)
    -- the SAME row-shape correction C1 makes for the function gate; see
    that module's own docstring for the "SILENT GREEN" trap this closes.

    `changed_files` is `_report_published_diff`'s own `NEW:`/`UPDATE:`
    rel-path set (staging_dir-relative), reused rather than recomputed --
    see that function's docstring for why re-deriving it here would cost a
    second filesystem walk this gate does not need to pay for.

    `token_index_path` (chunk C5) points at the token index maintained for
    this row's REPO ROOT (`<repo_root>/.percolate/token-index.bin`, § C5
    defect fix -- the writer, `_update_token_index_from_delta`, always keys
    and locates the index at `_manifest_root`, a repo root, never a row's
    own `dest_dir`); the prescreen seeks into it instead of reading every
    payload file. `None` -- an absent, unreadable, or not-yet-built index --
    degrades to the full scan and today's answer rather than to "no
    candidates" (§ `payload_parity :: _files_referencing_needles`, AC5).
    `token_index_root` is threaded alongside it so the reader and writer
    agree on the SAME key space (repo-root-relative) rather than the reader
    stripping `rel_root` back down to a `dest_dir`-relative key the writer
    never produced.

    Never raises -- fail-closed reporting only, same contract as
    `dispatch_preswap_function_gate`."""
    _bootstrap_engine()
    rel_root = _dest_prefix_for(target.dest_dir)
    token_index_root = _dest_repo_root(target.dest_dir)
    try:
        report = payload_parity.payload_parity_report(
            target.dest_dir,
            staging_dir,
            rel_root=rel_root,
            changed_files=changed_files,
            token_index_path=token_index_path,
            token_index_root=token_index_root,
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed, same as the function gate
        print(f"  Error: payload parity gate raised for {target.name}: {exc}", file=sys.stderr)
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    if payload_parity.abstain_share_exceeds_floor(report):
        total = report.checked_calls + report.abstained_calls
        print(
            f"  Warning: payload parity gate for {target.name}: {report.abstained_calls} of "
            f"{total} resolvable call site(s) abstained ({report.abstain_share:.0%}) — this "
            "run proves less than usual.",
            file=sys.stderr,
        )

    if not report.ok:
        for finding in report.violations:
            print(
                f"  Error: payload parity gate FAILED for {target.name}: "
                f"{finding.call_file}:{finding.lineno} calling {finding.callee!r} — {finding.message}",
                file=sys.stderr,
            )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    return True


# § chunk C3 -- per-subprocess timeout for one `--help` entrypoint spawn,
# and the aggregate wall-clock ceiling across every entrypoint gated for one
# repo root. A per-subprocess timeout alone bounds nothing: ~65 processes
# each finishing just under their own timeout is still an unbounded publish
# (§ this chunk's own brief, "the load-bearing half of AC4"). Sized against
# the machine load norm (`docs/wiki/machine-load-norm.md` -- 50-70 concurrent
# LLM sessions is the AVERAGE, not the peak; a slow op here is expected, not
# hung), not against an idle-box measurement -- generous enough that a
# genuinely loaded box does not spuriously red a publish, tight enough that
# a real hang (an entrypoint that blocks on stdin, e.g.) still gets caught
# well inside a human's patience for a publish run.
_ENTRYPOINT_GATE_PER_SUBPROCESS_TIMEOUT_SECS = 30.0
_ENTRYPOINT_GATE_AGGREGATE_BUDGET_SECS = 600.0

# § chunk C2 AC3 -- a timeout is not a startup failure, so it cannot flip
# `result.ok` to False (§ `run_entrypoint_gate`'s `timed_out` field). But a
# sweep where EVERY entrypoint timed out must not read as a silent, boring
# green: that is not "this box was busy", it is "this run proved nothing".
# 0.25 (one in four) is picked against the machine load norm (50-70
# concurrent LLM sessions is the AVERAGE, not the peak, § `docs/wiki/
# machine-load-norm.md`) -- a handful of stragglers on a loaded box is
# expected and must not warn on every publish, but a quarter or more of a
# repo's entrypoints going dark in one sweep is past "this box is busy"
# and into "this result is not trustworthy enough to call proof of
# anything". Any nonzero `timed_out` count is ALWAYS printed (§ AC3,
# "non-suppressibly") regardless of whether this floor is crossed --
# this constant only gates the escalation to an unproven-payload warning.
_ENTRYPOINT_GATE_TIMEOUT_SHARE_WARN_FLOOR = 0.25

# § chunk C5, AC5/AC11 -- `--changed-only` opt-in. Same rationale as C4's own
# `_CHANGED_ONLY_INDEX_ROOTS` "fail toward selecting": non-`.py` files an
# entrypoint may depend on at RUNTIME (a JSON/YAML registry, a snippet, a
# template) are read via data-loading, never `import`, so `derive_changed_
# entrypoints`'s closure walk -- which only ever queues `.py` files -- can
# never visit one, and a change to one can therefore never appear in
# `hit_changed` for ANY entrypoint, no matter which one actually consumes it.
# Named explicitly rather than silently assumed covered: when the changed
# set for a repo root contains a path with one of these suffixes, this leg
# widens that repo root's sweep back to FULL (subset=None) rather than
# narrowing on a graph that structurally cannot prove such a file is safe to
# ignore for every entrypoint at once.
_CHANGED_ONLY_UNMODELED_SUFFIXES: "tuple[str, ...]" = (
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
)


class _AlwaysExceptSelf:
    """A `__contains__`-only stand-in for `changed_set` (§ `_entrypoint_
    closure_reaches_any`'s own `rel_posix in changed_set` checks) that
    reports every path as "changed" EXCEPT the entrypoint's own -- used only
    to probe closure SHAPE, never real change data (§ `_compute_always_
    swept_entrypoints`).

    With this stand-in, `_entrypoint_closure_reaches_any` returns True iff
    the BFS visits at least one file other than the entrypoint itself, or
    could not resolve some file's imports statically (`force_selected`,
    independent of `changed_set` altogether). Both outcomes mean SOME
    changed-set, in principle, could select this entrypoint -- so returning
    False from that call is the only way to learn "no changed-set ever
    could", which is exactly the always-swept-floor membership test.
    """

    __slots__ = ("_self_rel",)

    def __init__(self, self_rel: str) -> None:
        self._self_rel = self_rel

    def __contains__(self, item: object) -> bool:
        return item != self._self_rel


def _compute_always_swept_entrypoints(
    engine_claude_klabauter: ClaudeKlabauterPercolate,
    repo_root: Path,
    entrypoints: "Sequence[str]",
) -> "tuple[str, ...]":
    """The always-swept floor (§ chunk C5 task item 2): every entrypoint
    whose OWN transitive first-party import closure is empty (reaches no
    file besides itself, and every file it did visit resolved cleanly) --
    unreachable by any import edge, so `derive_changed_entrypoints` can never
    select it from a changed set that does not name the entrypoint's own
    file. These must be swept every run regardless of `subset`, or a
    changed-only run silently stops proving they still start.

    Derived AT RUNTIME from C4's OWN closure computation
    (`_build_first_party_import_index` + `_entrypoint_closure_reaches_any`,
    both reached via `engine_claude_klabauter.percolate_engine_module` since neither is
    a public seam engine.py exports, and engine.py is C4-committed, not ours
    to extend) -- never a stored list or count (§ chunk C5 task item 2: "The
    plan measured 13 of 71 today... but that is an observation of today's
    tree, not a threshold").

    `_AlwaysExceptSelf` supplies a `changed_set` that reports every path as
    changed except the entrypoint's own -- so `_entrypoint_closure_reaches_
    any` returning False here means "this entrypoint's closure never reaches
    anywhere a change could ever be observed", the always-swept condition.
    """
    engine_module = engine_claude_klabauter.percolate_engine_module
    build_index = engine_module._build_first_party_import_index  # noqa: SLF001 - see docstring
    reaches_any = engine_module._entrypoint_closure_reaches_any  # noqa: SLF001 - see docstring
    normalize = engine_module._normalize_repo_relative  # noqa: SLF001 - see docstring

    index = build_index(repo_root)

    always_swept: "list[str]" = []
    for rel in entrypoints:
        rel_norm = normalize(rel)
        entrypoint_path = repo_root / rel
        if not reaches_any(entrypoint_path, repo_root, index, _AlwaysExceptSelf(rel_norm)):
            always_swept.append(rel)
    return tuple(always_swept)


def dispatch_end_of_run_entrypoint_gate(
    engine_ctx: PercolateEngineContext,
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
    changed_files_by_repo_root: "Optional[dict[Path, Optional[set[Path]]]]" = None,
    changed_only: bool = False,
) -> bool:
    """ENTRYPOINT gate (chunk C3, wiring C2's `run_entrypoint_gate` into the
    driver): for each distinct destination repo root this invocation's rows
    resolve to, EXECUTE every shipped bare entrypoint (§ `enumerate_gate_
    entrypoints`) with `--help` under a hermetic, `mktcache`-shaped
    subprocess environment (`mktcache_gate_env` -- the real Claude Code
    marketplace-install home shape, never the bare/ambient one; § chunk C2
    brief and this module's own `dispatch_end_of_run_function_gate`
    docstring for why the ambient environment must never reach a gate
    subprocess).

    This is a DIFFERENT, complementary check from `dispatch_end_of_run_
    function_gate` above: that leg proves three seed modules IMPORT; this
    leg proves each shipped entrypoint actually STARTS when invoked as a
    process, the defect class `run_entrypoint_gate`'s own module-level
    comment names (a broken join, or a `__main__`-guarded code path, neither
    reachable from a bare `importlib.import_module`). Neither leg subsumes
    the other -- both run, unconditionally (§ C3's remit-extension brief,
    "do not delete or disable `run_function_gate`... both legs run").

    Dispatches under this chunk's derived worker cap (`engine_claude_klabauter.
    derive_worker_cap()`, this repo's real two-term `min(physical_cores/2,
    usable_RAM_GB*1024/150MB)` formula, § CLAUDE.md) and aggregate wall-clock
    budget (`_ENTRYPOINT_GATE_AGGREGATE_BUDGET_SECS`) -- both threaded
    straight into `run_entrypoint_gate`'s own `max_workers`/`aggregate_
    budget` kwargs, the seam C2 left for exactly this call.

    Run ONCE per distinct destination repo root, after every row has synced
    -- same "needs the fully assembled tree" reasoning as the other
    end-of-run legs (§ `dispatch_end_of_run_function_gate`'s own docstring).

    TIMEOUTS (§ chunk C2 AC3) are reported SEPARATELY from `result.failures`
    and never flip `ok` on their own -- `run_entrypoint_gate`'s `timed_out`
    field distinguishes "this box was busy" from "this CLI is broken" at
    classification time. This leg still prints the timeout count
    unconditionally (never suppressible) and escalates to an explicit
    unproven-payload warning when the timeout share crosses
    `_ENTRYPOINT_GATE_TIMEOUT_SHARE_WARN_FLOOR`, or on ANY timeout for an
    unfiltered (`target_filtered=False`) release-shaped run -- a sweep
    where every entrypoint times out must never read as a quiet green.

    SEVERITY -- FAIL-HARD unconditionally, filtered or not, same judgement
    call as `dispatch_end_of_run_function_gate` for the same reason: a
    non-starting entrypoint that WAS shipped in this row's payload has no
    cross-row "sibling hasn't synced yet" excuse. `target_filtered` is
    accepted for call-site symmetry only and does not change severity here.

    Returns True iff every repo root's gated entrypoints all started cleanly
    (or were on the waiver/usage-nonzero lists, § `run_entrypoint_gate`'s own
    three-way classification); False iff any failed to start, or the gate
    itself could not run. Never raises -- same reporting contract as the
    other end-of-run legs. Never called under `--dry-run`.

    `changed_only` (§ chunk C5, AC11): this function's own default stays
    False (`subset=None`, the full sweep every pre-existing call site got
    before this parameter existed) — it is the neutral primitive default,
    not a policy choice. The POLICY choice lives at the CLI layer: PM
    ruling, 2026-08-15, the entrypoint gate runs --changed-only or --delta,
    never a full sweep, so `publish.py`'s own `--changed-only` CLI flag now
    defaults ON and threads `True` here on a default invocation; `--full-
    sweep` is the CLI's opt-out. When True, `changed_files_by_repo_root`
    (§ docs/plans/2026-08-16-percolate-round-timing-and-changed-only.md
    chunk C4 -- this run's REAL changed-set, sourced from the sync layer's
    own copy/update decisions unioned with the transform sweep's actual
    rewrites, § engine.py `PhaseResult.changed_files`; deliberately NOT
    `visited_files_by_repo_root`, a read-set that made this gate collapse
    to a full sweep on essentially every round -- see that plan's Problem
    statement) is fed through `derive_changed_entrypoints` (chunk C4 of the
    2026-08-10 plan) to compute a subset, unioned with `_compute_always_
    swept_entrypoints`'s always-swept floor so an entrypoint no changed-set
    could ever select still gets scanned every run. If any changed path
    carries a suffix in `_CHANGED_ONLY_UNMODELED_SUFFIXES`, that repo
    root's subset is widened back to the full sweep instead (§ that
    constant's own docstring) -- a change to an untracked-by-the-graph
    dependency must never narrow the sweep. `changed_files_by_repo_root=
    None` with `changed_only=True` falls back to a full sweep for every
    repo root (nothing to derive a subset from); a repo root PRESENT in the
    dict but mapped to `None` (§ that dict's own construction -- a row
    whose changed-set could not be determined this run) falls back to a
    full sweep for THAT repo root only, same fail-wide reasoning.
    """
    assert engine_ctx.engine_claude_klabauter is not None  # narrowed by caller (never called under dry-run)
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    ok = True
    for repo_root in repo_roots:
        if not repo_root.is_dir():
            continue

        entrypoints = engine_claude_klabauter.enumerate_gate_entrypoints(repo_root)
        if not entrypoints:
            continue

        max_workers = engine_claude_klabauter.derive_worker_cap()

        subset: "Optional[Sequence[str]]" = None
        if changed_only:
            # § chunk C4 (docs/plans/2026-08-16-percolate-round-timing-and-
            # changed-only.md) -- a repo root absent from the dict, OR the
            # dict itself `None`, OR present but mapped to `None` (this run's
            # changed-set for that root could not be determined, § the
            # caller's own dict-construction comment) all fall back to the
            # full sweep here -- three distinct "undeterminable" shapes, one
            # fallback, per the docstring above.
            repo_root_changed: "Optional[set[Path]]"
            if changed_files_by_repo_root is None:
                repo_root_changed = None
            else:
                repo_root_changed = changed_files_by_repo_root.get(repo_root, set())

            changed_paths: "list[str]" = []
            unmodeled_hit = False
            if repo_root_changed is not None:
                for changed_path in repo_root_changed:
                    try:
                        rel = changed_path.relative_to(repo_root).as_posix()
                    except ValueError:
                        continue  # outside repo_root -- cannot be a repo-relative changed path
                    changed_paths.append(rel)
                    if Path(rel).suffix in _CHANGED_ONLY_UNMODELED_SUFFIXES:
                        unmodeled_hit = True

            # An engine that predates `derive_changed_entrypoints` cannot narrow
            # anything -- fail WIDE (full sweep), never narrow. A published mirror
            # can be an older engine than the one driving this round, so this is
            # version skew, not a test-fixture concession: raising here would abort
            # a legitimate publish, and defaulting to a narrow subset would ship an
            # unswept entrypoint.
            _derive = getattr(engine_claude_klabauter, "derive_changed_entrypoints", None)
            if repo_root_changed is None or unmodeled_hit or _derive is None:
                subset = None  # full sweep fallback -- see docstring
            else:
                selected = _derive(
                    changed_paths, repo_root, entrypoints=entrypoints
                )
                always_swept = _compute_always_swept_entrypoints(engine_claude_klabauter, repo_root, entrypoints)
                subset = tuple(sorted(set(selected) | set(always_swept)))

        try:
            # Director-of-Engineering ruling, same rung as `dispatch_end_of_
            # run_function_gate` (§ that function's own docstring "WHAT THIS
            # GATE ACTUALLY ASSERTS" section) -- a bare engine mirror never
            # ships DoE-claude's `coordinator-registry.manifest.json` by
            # design, so every shipped entrypoint that imports `coordinator_
            # registry` fails this gate by construction with the same
            # `FileNotFoundError` class the function gate hit (§ state/
            # audits/2026-08-10-klabauter-gate-failure-classes.md, class 2).
            # Reuses `_synthetic_registry_manifest_overrides` outright rather
            # than a second, parallel fixture helper -- `mktcache_gate_env`'s
            # own `overrides` kwarg is applied LAST over its `mktcache`-
            # shaped HOME (§ that function's own docstring), the identical
            # seam `hermetic_gate_env` documents, so the synthetic manifest
            # rung wins here exactly as it does for the function gate.
            with _synthetic_registry_manifest_overrides() as manifest_overrides:
                with engine_claude_klabauter.mktcache_gate_env(overrides=manifest_overrides) as env:
                    result = engine_claude_klabauter.run_entrypoint_gate(
                        repo_root,
                        entrypoints,
                        env=env,
                        timeout=_ENTRYPOINT_GATE_PER_SUBPROCESS_TIMEOUT_SECS,
                        max_workers=max_workers,
                        aggregate_budget=_ENTRYPOINT_GATE_AGGREGATE_BUDGET_SECS,
                        subset=subset,
                    )
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run entrypoint gate raised for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        # § C1 (docs/plans/2026-08-16-percolate-round-timing-and-changed-
        # only.md) — `result.scanned` was already computed here, but was
        # printed only on a failure or timeout, never on a clean run. That
        # number is the single number that decides whether `--changed-only`
        # is narrowing anything at runtime, so it is reported unconditionally
        # now, alongside the full entrypoint population this repo root
        # shipped. Purely additive — does not participate in `ok`.
        print(
            f"  [timing] entrypoint gate for {repo_root}: scanned "
            f"{result.scanned}/{len(entrypoints)} entrypoint(s)"
            + (" (--changed-only subset)" if subset is not None else " (full sweep)"),
            file=sys.stdout,
        )

        if not result.ok:
            print(
                f"  Error: end-of-run entrypoint gate FAILED for {repo_root}: "
                f"{len(result.failures)} of {result.scanned} entrypoint(s) did "
                f"not start cleanly:",
                file=sys.stderr,
            )
            for failure in result.failures:
                rc = failure.returncode if failure.returncode is not None else "?"
                print(f"    {failure.entrypoint} (rc={rc}): {failure.message}", file=sys.stderr)
            ok = False

        # § AC3 -- reported unconditionally whenever nonzero, never folded
        # into the `result.ok`-gated block above: a timeout alone must not
        # flip `ok`, but that is not license to go quiet about it either.
        if result.timed_out:
            print(
                f"  Note: end-of-run entrypoint gate could not be determined "
                f"under load for {repo_root}: {len(result.timed_out)} of "
                f"{result.scanned} entrypoint(s) timed out (not counted as "
                f"non-starting):",
                file=sys.stderr,
            )
            for rel in result.timed_out:
                print(f"    {rel}", file=sys.stderr)

            timeout_share = len(result.timed_out) / result.scanned if result.scanned else 0.0
            # NEGATIVE SPEC -- AC3's second arm ("or ANY timeout on a
            # release-shaped run") is deliberately NOT implemented here, and
            # `target_filtered=False` is NOT the proxy for it. There is no
            # release publish kind to key on: this driver's modes are
            # `mirror` and `flat-mirror` only, and minting the missing
            # user-visible contract is named Out of scope by the plan that
            # authored this AC (§ docs/plans/2026-08-10-entrypoint-gate-
            # launcher-and-changed-only.md). Using "unfiltered" as a stand-in
            # inverts the AC's intent rather than approximating it: an
            # unfiltered sweep of this repo's full entrypoint population
            # routinely draws a straggler or two on a box whose stated norm
            # is 50-70 concurrent LLM sessions (the same load that produced
            # the 13/13/14 failure-count spread this chunk exists because
            # of), so ANY-timeout-when-unfiltered would stamp UNPROVEN
            # PAYLOAD on substantially every full publish -- a warning that
            # always fires is one nobody reads, which is the same
            # cheap-because-it-is-not-really-checking failure the plan's
            # Anti-scope forbids on the coverage side. Wire this arm when a
            # real release-publish kind exists to name; until then the share
            # floor carries the AC alone.
            if timeout_share >= _ENTRYPOINT_GATE_TIMEOUT_SHARE_WARN_FLOOR:
                print(
                    f"  Warning: entrypoint gate result for {repo_root} is an "
                    f"UNPROVEN PAYLOAD -- {len(result.timed_out)}/{result.scanned} "
                    f"({timeout_share:.0%}) entrypoints timed out under load and "
                    f"were never actually exercised. A green gate here does not "
                    f"mean these entrypoints start.",
                    file=sys.stderr,
                )

    return ok


def dispatch_end_of_run_functional_identifier_output_drift_check(
    engine_ctx: PercolateEngineContext,
    row_sections: "List[tuple]",
    *,
    target_filtered: bool,
) -> bool:
    """Output functional-identifier drift gate — wires
    `find_functional_identifier_output_drift_in_tree`
    (`coordinator_core/percolate/store.py`) into the end-of-run gate sequence
    (Review: staff-eng MAJOR-2, `state/review-findings/2026-08-08-codename-
    free-partitioned/slice-D-drift-store.md`, deferred until the concurrent
    drift-store repair landed). Before this leg, nothing called that
    function outside its own tests/docstrings — a scrub that renamed a wire
    identifier shipped exactly as before, silently.

    Run PER ROW (`row_sections`, the same `(target, section)` accumulator
    `dispatch_end_of_run_unscanned_published_check` consumes), never deduped
    by destination repo root like the other three legs — `resolved_section`
    and `source_dir` are per-row properties, so there is no shared repo-root
    key to dedup comparisons on; two rows sharing a destination repo root can
    still have distinct sources and distinct resolved sections.

    For each row, diffs `target.source_dir` against `target.dest_dir` with
    `resolved_section=section` supplied — omitting it makes the check see
    the raw, unfiltered pre-C10 pair stream (§ that function's own
    docstring). `dest_publish_time` is deliberately never supplied: that
    branch forks one `git log` per file (~1600 files in `coordinator_core`
    alone) and is what killed two prior measurement attempts on this
    machine's shared, heavily-loaded tree; with `resolved_section` supplied
    and no cutoff, the walk spawns zero subprocesses (measured directly by
    the sidecar review).

    By the time this end-of-run leg runs (after every row has synced and
    swapped), `target.dest_dir` IS the freshly published payload this run
    just wrote, not a stale pre-run snapshot — same "read the staged payload
    it is about to write, not the stale destination" requirement the other
    end-of-run legs already satisfy by running after the full row loop.

    The ratchet baseline (`functional-identifier-output-drift-baseline.txt`)
    is loaded ONCE, up front, and is currently, deliberately, EMPTY — empty
    means "detect everything," never "gate disabled" (no "empty means skip"
    short-circuit exists here or should be added; the baseline identity is
    the bare `(source_token, published_token)` pair, mirroring
    `_check_functional_identifier_output_not_drifted`'s own ratchet check).
    A pair present in the baseline is grandfathered; one that is not fails
    this leg.

    SEVERITY — FAIL-HARD unconditionally, same judgement call as
    `dispatch_end_of_run_function_gate` (`target_filtered` accepted for
    call-site symmetry only; a row's own source-vs-dest comparison has no
    cross-row "sibling hasn't synced yet" dependency to legitimately degrade
    under `--target`).

    Returns True iff every row's comparison found no un-baselined drift;
    False otherwise. Never raises — same reporting contract as the other
    end-of-run legs. Never called under `--dry-run` (same reason as the
    other legs).
    """
    assert engine_ctx.engine_claude_klabauter is not None  # narrowed by caller (never called under dry-run)
    engine_claude_klabauter = engine_ctx.engine_claude_klabauter
    baseline = engine_claude_klabauter.load_functional_identifier_output_drift_baseline()
    ok = True
    for target, section in row_sections:
        if not target.source_dir.is_dir() or not target.dest_dir.is_dir():
            continue
        try:
            drift = engine_claude_klabauter.find_functional_identifier_output_drift_in_tree(
                target.source_dir,
                target.dest_dir,
                resolved_section=section,
            )
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run functional-identifier output-drift check raised for "
                f"{target.name} ({target.dest_dir}): {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        # Identity is the bare (source_token, published_token) pair — same
        # projection `_drift_baseline_identity` applies in store.py today.
        unbaselined = [row for row in drift if (row[1], row[2]) not in baseline]
        if unbaselined:
            print(
                f"  Error: end-of-run functional-identifier output-drift check FAILED for "
                f"{target.name} ({target.dest_dir}): {len(unbaselined)} un-baselined "
                f"drifted token(s):",
                file=sys.stderr,
            )
            for rel_path, source_token, published_token in unbaselined:
                published_repr = published_token if published_token is not None else "<vanished>"
                print(f"    {rel_path}: {source_token!r} -> {published_repr!r}", file=sys.stderr)
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


_SOURCE_ARGV_PARITY_BASELINE_PATH = (
    _REPO_ROOT / "coordinator_core" / "tests" / "engine_cli_argv_parity_baseline.json"
)


def _load_source_argv_parity_baseline_keys() -> "set[tuple] | None":
    """Load C2's committed baseline (`engine_cli_argv_parity_baseline.json`)
    from the SOURCE repo — THIS checkout, `_REPO_ROOT`, never the
    destination mirror tree a gate call is assessing. `.percolate-ignore`
    carries a `*test_*.py` glob and the baseline sits under
    `coordinator_core/tests/`, so it is not guaranteed to exist inside a
    published mirror — reading it from the source side is the only read
    that is certain to find it.

    Returns the same per-token key shape
    `test_engine_cli_argv_parity.py::_load_baseline_keys` uses
    (`("unaccepted"|"undeclared_required", module, directive_id, cli,
    token)`), or `None` if the file is missing or unreadable/malformed —
    the caller MUST treat `None` as a fail-hard condition, never as an
    empty baseline. A pairing recorded in this baseline is a KNOWN,
    pre-existing defect this plan did not undertake to fix — filed
    separately where one exists (see this repo's `state/bug-backlog/`) —
    not an endorsement that it is fine to ship.
    """
    try:
        doc = json.loads(_SOURCE_ARGV_PARITY_BASELINE_PATH.read_text(encoding="utf-8"))
        keys: "set[tuple]" = set()
        for entry in doc["entries"]:
            base = (entry["module"], entry["directive_id"], entry["cli"])
            for token in entry.get("unaccepted", []):
                keys.add(("unaccepted", *base, token))
            for token in entry.get("undeclared_required", []):
                keys.add(("undeclared_required", *base, token))
        return keys
    except Exception:  # noqa: BLE001 - any read/parse failure is fail-hard, not permissive
        return None


def dispatch_end_of_run_argv_parity_gate(
    repo_roots: "List[Path]",
    *,
    target_filtered: bool,
) -> bool:
    """Run `directive_cli_arity.argv_parity_report` ONCE per distinct
    destination repo root touched by this `main()` invocation, after every
    row has synced — END-OF-RUN ONLY, same shape as
    `dispatch_end_of_run_unscanned_published_check` /
    `dispatch_end_of_run_function_gate`
    (docs/plans/2026-08-15-bind-the-klabauter-publish-rows-into-a-parity-
    group.md, chunk C4, AC4/AC6).

    The report runs against the ASSEMBLED DESTINATION tree — the mirror as
    a consumer will actually execute it, `repo_root/coordinator_core` paired
    against `repo_root/coordinator/bin` — never against this repo. The
    mirror's layout preserves both subtrees unchanged from source, so
    `resolve_bin_script` resolves against the destination root with no path
    rewriting (verified non-issue, recorded per this chunk's own brief so a
    future reader does not have to rediscover it).

    BASELINE-RELATIVE, same subset semantics as C2's
    `test_engine_cli_argv_parity.py`: the gate fails ONLY on an
    `unaccepted`/`undeclared_required` token that is NOT already present in
    the committed baseline (`_load_source_argv_parity_baseline_keys`), i.e.
    NEW skew introduced since that baseline was pinned — never on the
    pre-existing red set the baseline enumerates. Both this gate and C2's
    test consume the same oracle over the same corpus, so they share the
    same reasoning the plan's own § Anti-scope gives for AC2: enumerate a
    pre-existing defect in the baseline rather than gate on it being empty.
    One genuine pre-existing skew survives in this repo as of authoring
    time (`merge_assemble` d4 -> `merge-gate-and-pr pr-body`, missing
    required `--ship-verdict`/`--release-notes`; filed separately,
    `state/bug-backlog/2026-08-15-merge-assemble-d4-invokes-merge-gate-and-
    0de925b03e8d.yaml`, NOT this gate's to fix) — a gate with the OLD
    empty-baseline semantics would fail every publish round on that one
    known defect, which is a gate operators learn to ignore. A pairing
    listed in the baseline is a KNOWN defect, not an endorsed one.

    If the baseline cannot be loaded (missing, unreadable, malformed —
    `_load_source_argv_parity_baseline_keys` returns `None`), this gate
    FAILS with that reason stated, for every repo root, before comparing
    anything — a gate that cannot find its baseline and silently passes is
    worse than no gate at all.

    A pairing failing on EITHER `unaccepted` (an emitted flag the target
    parser does not declare) OR `undeclared_required` (a declared-required
    flag/subcommand the emitter does not emit) is a candidate finding — the
    second direction is exactly the hazard the klabauter parser-before-
    emitter reorder (§ `_assert_klabauter_parity_group_ordering`) exists to
    guard against for non-additive parser changes, so a gate blind to it
    could not detect what that reorder was built to catch. `unresolved`
    pairings are never treated as failures nor as clean passes — they are
    outside what static AST reading could prove for this round and are
    silently excluded from the verdict, matching C1's `argv_parity_report`
    contract (`unresolved` is never `clean`, but this gate has no stronger
    claim to make about a pairing it cannot read) and matching C2's own
    baseline, which never keys an `unresolved` pairing by token.

    SEVERITY — FAIL-HARD UNCONDITIONALLY, not degraded under `--target`,
    unlike `dispatch_end_of_run_identity_check` /
    `..._install_doc_payload_check`'s advisory-under-`--target` split. A
    prior-art check across this module's own end-of-run legs found no
    universal rule either way: some carry "advisory under --target"
    language (the two named above), others (`dispatch_end_of_run_function_
    gate`, `dispatch_end_of_run_entrypoint_gate`) do not — the choice is
    case-by-case per gate, not governed by settled doctrine, and THIS
    sentence is the only place a future reader can learn why THIS gate
    chose fail-hard. The reason: a `--target` subset publish is precisely
    how a partial mirror gets constructed — "a sibling row hasn't synced
    yet, so the destination looks skewed" is the exact condition this gate
    exists to detect, never an excuse to suppress detecting it. Degrading
    it under `--target` would blind the gate on the one invocation shape
    most likely to produce the skew it is built to catch. The baseline
    relaxation above is a DIFFERENT axis (which skew counts at all) and
    does not weaken this one (whether `--target` softens a real finding —
    it never does).

    Never short-circuits on failure and is never short-circuited by a
    sibling leg's failure — `main()` calls every end-of-run leg
    unconditionally (2026-08-14 aggregate-instead-of-abort fix) so one round
    surfaces every defect class instead of one at a time.

    HAZARD — false positive on operator-local mirror edits: this gate reads
    the destination WORKING TREE, which this plan's own § Anti-scope
    records as carrying ~28 uncommitted modifications under
    `coordinator_core/` today, unrelated to this run's publish.
    `2026-08-04-publish-from-a-committed-ref.md` holds the SOURCE side of a
    publish still (reads a committed ref, not the live source tree) — it
    says nothing about the DESTINATION working tree, which this gate reads
    as-is. A pairing can therefore fail on a file this round never
    published, reading as a false FATAL at exit 2 on an otherwise-clean
    round. To make that diagnosable rather than re-discovered, every
    reported pairing's `module` path is tagged, in the printed failure, as
    either `published-by-this-round` (present under one of `repo_roots`'
    corresponding row's known allowlisted surface for this run) or
    `destination-only` (present in the destination tree but not attributable
    to anything this invocation just wrote) — see `_argv_parity_pairing_origin`.

    Returns True iff every repo root's resolvable pairings carry no NEW
    skew beyond the baseline; False iff any repo root has a new
    `unaccepted`/`undeclared_required` finding, the report itself could not
    be produced, the baseline itself could not be loaded, or a repo root is
    not a directory. Never raises — same reporting contract as the other
    end-of-run legs. Never called under `--dry-run`: `main()`'s dry-run
    early return covers every end-of-run leg identically, and a preview run
    mutates no destination for this gate to meaningfully assess.

    A `repo_root` that is not a directory FAILS this gate rather than being
    silently skipped: every `repo_root` passed in is a distinct destination
    this round is expected to have assembled, so a missing/non-directory
    root means the round did not actually land what it claims to have
    landed there (e.g. a race with a concurrent process on this box) — the
    exact permissive-degradation shape this gate's baseline-load path
    already refuses (see above).
    """
    _bootstrap_engine()
    baseline_keys = _load_source_argv_parity_baseline_keys()
    if baseline_keys is None:
        print(
            "  Error: end-of-run argv-parity gate could not load its source-repo "
            f"baseline ({_SOURCE_ARGV_PARITY_BASELINE_PATH}) -- failing hard rather "
            "than degrading to permissive.",
            file=sys.stderr,
        )
        return False

    ok = True
    # Pass 1: pure computation, no git spawn anywhere in this loop body —
    # collect every repo_root's failing pairings into `failing_by_root`
    # first, so the origin-lookup spawn (pass 2, below) is issued from a
    # single call site outside any loop over `repo_roots`, instead of once
    # per root from inside this loop (docs/plans/2026-08-19-burn-down-the-
    # amplification-hitlist.md C5-2: the previous shape still called a
    # spawning helper once per `repo_root` from directly inside this loop,
    # which is itself the per-item-call-inside-a-qualifying-loop shape
    # `test_no_unbatched_per_item_git_spawn.py` flags, one level up from
    # the per-pairing amplification C5 already closed within one root).
    failing_by_root: "dict[Path, list]" = {}
    for repo_root in repo_roots:
        if not repo_root.is_dir():
            print(
                f"  Error: end-of-run argv-parity gate expected a destination repo "
                f"root at {repo_root} but it is not a directory -- failing hard "
                "rather than silently skipping an unassembled destination.",
                file=sys.stderr,
            )
            ok = False
            continue
        try:
            report = directive_cli_arity.argv_parity_report(repo_root)
        except Exception as exc:  # noqa: BLE001 - AC15 fail-closed path, same as any phase raise
            print(
                f"  Error: end-of-run argv-parity gate raised for {repo_root}: {exc}",
                file=sys.stderr,
            )
            ok = False
            continue

        failing = []
        for pairing in report.pairings:
            if pairing.unresolved:
                continue
            base = (pairing.module, pairing.directive_id, pairing.cli)
            new_unaccepted = sorted(
                token
                for token in pairing.unaccepted
                if ("unaccepted", *base, token) not in baseline_keys
            )
            new_undeclared_required = sorted(
                token
                for token in pairing.undeclared_required
                if ("undeclared_required", *base, token) not in baseline_keys
            )
            if new_unaccepted or new_undeclared_required:
                failing.append((pairing, new_unaccepted, new_undeclared_required))
        if failing:
            ok = False
            failing_by_root[repo_root] = failing

    if not failing_by_root:
        return ok

    # Pass 2: ONE call, outside any loop over `repo_roots`, resolving every
    # failing pairing's origin across every root that had failures.
    # `_argv_parity_pairing_origin_batch_by_root` still issues one `git
    # status` spawn per DISTINCT root internally — there is no git
    # primitive that spans multiple `-C` roots in a single invocation, so
    # that per-root spawn count is the structural floor, same as
    # `_git_ls_tree_entries_files`'s own per-root call in
    # that helper. What this hoist removes is this
    # function's OWN per-root call to a spawning helper sitting directly in
    # a loop it controls; the unavoidable per-root fan-out now lives
    # entirely inside the batch helper, which is the SAME single call site
    # regardless of how many roots are in `failing_by_root`.
    origin_by_root = _argv_parity_pairing_origin_batch_by_root(
        {
            repo_root: [pairing.module for pairing, _, _ in failing]
            for repo_root, failing in failing_by_root.items()
        }
    )

    for repo_root, failing in failing_by_root.items():
        origin_by_module = origin_by_root.get(repo_root, {})
        lines = []
        for pairing, new_unaccepted, new_undeclared_required in failing:
            origin = origin_by_module.get(pairing.module, "unknown-origin")
            if new_unaccepted:
                lines.append(
                    f"    {pairing.module} ({origin}) -> {pairing.cli!r}: emits "
                    f"unaccepted flag(s) {new_unaccepted!r} not in the source-repo baseline"
                )
            if new_undeclared_required:
                lines.append(
                    f"    {pairing.module} ({origin}) -> {pairing.cli!r}: does not "
                    f"emit declared-required {new_undeclared_required!r} not in the "
                    "source-repo baseline"
                )
        print(
            f"  Error: end-of-run argv-parity gate FAILED for {repo_root}: "
            f"{len(failing)} engine-module -> CLI pairing(s) skewed in the "
            "published mirror beyond the committed baseline "
            "(emitter/parser argv contract broken):\n"
            + "\n".join(lines),
            file=sys.stderr,
        )

    return ok


_ASSEMBLED_MIRROR_GATE_DECLARATIONS_PATH = _REPO_ROOT / "setup" / "publish-allowlist-declarations.yaml"
"""Same file the allowlist `deny`/`include_root` declarations already live
in (§ that file's own module docstring) — this gate's exemption ledger is a
second, independently-keyed top-level section of it
(`assembled_mirror_gate_exemptions`), not a new file: one declared-input
home for publish-time acceptance decisions, matching the parent plan's own
framing that a deny-a-module/deny-its-tests convention already lived in
this file as unenforced prose before this gate existed to check it."""


def _load_assembled_mirror_gate_exemptions(
    path: "Optional[Path]" = None,
) -> "dict[str, str]":
    """Read the declared-exemption ledger for `dispatch_end_of_run_
    assembled_mirror_gate`: `{name: reason}`, keyed by a PUBLISH TARGET row
    name (any row contributing to a failing repo root — see that gate's own
    docstring for why a repo root, not a row, is what the gate itself
    checks). Missing file, missing key, or a malformed entry degrades to
    `{}` (no declared exemptions) rather than raising -- an unreadable
    ledger must never silently exempt a row; it must fall through to the
    gate's own fail-closed refusal instead, the same asymmetry `import_
    closure.py`'s own `_unguarded_import_nodes` documents for itself.

    Shape, per entry: `{name: <str>, reason: <str, non-empty>}`. A row
    named more than once keeps its LAST reason (last-write-wins, same as a
    human editing a list by hand would expect) rather than raising on a
    duplicate — this is a declared-debt ledger, not a schema-validated
    contract.
    """
    target_path = path or _ASSEMBLED_MIRROR_GATE_DECLARATIONS_PATH
    if not target_path.is_file():
        return {}
    try:
        import yaml  # noqa: PLC0415 - lazy, this call site is the only user of yaml in this scope

        with target_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001 - unreadable/malformed ledger must not exempt anything
        return {}

    entries = raw.get("assembled_mirror_gate_exemptions") or []
    if not isinstance(entries, list):
        return {}

    exemptions: "dict[str, str]" = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        reason = entry.get("reason")
        if isinstance(name, str) and name and isinstance(reason, str) and reason:
            exemptions[name] = reason
    return exemptions


def _drop_ratified_test_denials(coverage, rows):
    """Filter the coverage leg's `missing` set against each row's own `!`
    allowlist denials -- the exemption wiring `assembled_mirror_gate`
    explicitly leaves to this module.

    That gate is MECHANISM ONLY and says so in its own module docstring: it
    "does not itself read `setup/publish-allowlist-declarations.yaml` or any
    exemption ledger -- that wiring is `coordinator/bin/publish.py`'s job".
    Until now nothing here did it, so a test DELIBERATELY denied in field 7 of
    `setup/publish-targets.portable` came back as an unexplained WARN every
    round, indistinguishable from an accidental payload gap.

    Worked example, the entry that exposed this: `!ops/tests/
    test_sizing_spike_verdict.py` is a dated, reasoned denial (2026-08-14,
    dc3eb5cb9) -- the test imports `coordinator_core.plan_assemble.predicates`
    at module level, `plan_assemble` is not on this row's published surface,
    and shipping the test would drag a whole predicate subsystem into the
    mirror to satisfy one cross-check. Its subject module ships unexcluded, so
    the gate correctly saw "module shipped, test did not" and warned -- on a
    decision already ratified in the file it could not read.

    A denial is matched by BASENAME, not full path: the gate reports subject
    paths relative to the assembled tree while denials are written relative to
    a row's own source dir, so the two never share a prefix to compare on.
    Only the `test_<subject stem>.py` name is derived, so a denial can never
    silence a subject other than the one it names.
    """
    denied: "set[str]" = set()
    for row in rows:
        for entry in (getattr(row, "allowlist", "") or "").split(","):
            entry = entry.strip()
            if entry.startswith("!"):
                denied.add(PurePosixPath(entry[1:]).name)
    if not denied:
        return coverage
    kept = tuple(
        path
        for path in coverage.missing
        if f"test_{PurePosixPath(path).stem}.py" not in denied
    )
    return replace(coverage, missing=kept)


def _declared_repo_roots_carrying_coordinator_core() -> "tuple[set[Path], set[Path]]":
    """Return `(engine_roots, all_declared_roots)`: `engine_roots` is every
    destination repo root whose DECLARED scope — the UNFILTERED target row
    set, never the current invocation's possibly `--target`-filtered
    subset — includes a row sourced from `coordinator_core`; `all_declared_
    roots` is every destination repo root ANY declared row resolves to,
    regardless of source. This is the caller-side discriminator `assembled_
    mirror_gate.run_assembled_mirror_gate`'s `coordinator_core_in_declared_
    scope` argument needs (see that module's own "The third verdict"
    docstring section): it is MECHANISM ONLY and cannot read `setup/
    publish-targets.portable` itself, so this function reads it here, in
    the wiring layer, once per end-of-run dispatch.

    The second set exists so the caller can tell "declared, and known not
    to carry the engine" (eligible for NOT-APPLICABLE) apart from "not a
    recognised declared destination at all" (a repo_root this function has
    no opinion on — e.g. a synthetic scratch tree in a test, or any future
    caller of the gate with a destination this ledger has never heard of).
    Only the former is NOT-APPLICABLE; the latter falls back to the SAME
    safe default `run_assembled_mirror_gate` itself uses when the caller
    omits `coordinator_core_in_declared_scope` entirely (`True` — keep
    refusing) — an unrecognised destination must never be read as
    "declared out of scope" merely because it never appeared in the
    declared row set.

    Reuses the exact unfiltered-load shape already established at this
    file's own `_required_pathspec_for` (`load_targets(setup_dir,
    target_filter="", err=io.StringIO())`) — `err=io.StringIO()` is
    load-bearing there and here alike: `main()`'s own `load_targets` call
    already printed shadow-collision diagnostics to stderr once this run,
    and an unfiltered re-resolution would otherwise reprint them verbatim.

    Deliberately does NOT swallow `TargetsError` the way `_required_
    pathspec_for` does — that site's empty-list fallback is safe there
    (no rows just narrows a pathspec, a widening). It would be catastrophic
    here: an empty list from a swallowed load failure reads as "coordinator_
    core is not in this destination's declared scope" -> NOT-APPLICABLE ->
    a failure to load the targets file waiving the gate on itself, the same
    fail-open shape as the exemption bug this whole change exists to close.
    A `TargetsError` here is INCOMPLETE (no claim could be determined), so
    it is left to propagate; the caller catches it and reports the round as
    unable to determine declared scope rather than reading absence as
    not-applicable.

    Rows come back FIRST-TIER-WINS on a name collision (`load_targets`'s
    own resolution order) — "every row registered against a dest" here
    means every row SURVIVING shadowing; a row shadowed by an earlier tier
    is not in the set this function reads, and is never consulted."""
    _bootstrap_engine()
    percolate_root, _rung = _resolve_percolate_root_and_rung()
    setup_dir = percolate_root / "setup"
    rows = load_targets(setup_dir, target_filter="", err=io.StringIO())

    engine_roots: "set[Path]" = set()
    all_declared_roots: "set[Path]" = set()
    for row in rows:
        try:
            target = parse_target_row(row)
        except TargetsError:
            continue
        repo_root = _dest_repo_root(target.dest_dir) or target.dest_dir
        all_declared_roots.add(repo_root)
        if target.source_dir.name == "coordinator_core":
            engine_roots.add(repo_root)
    return engine_roots, all_declared_roots


def dispatch_end_of_run_assembled_mirror_gate(
    repo_roots: "List[Path]",
    *,
    rows_by_repo_root: "dict[Path, List[ResolvedTarget]]",
    target_filtered: bool,
    out: IO[str] = sys.stdout,
) -> bool:
    """END-OF-RUN leg (docs/plans/2026-08-28-a-dropped-module-must-not-
    leave-its-test-behind.md, chunk C3): wires C2's `run_assembled_mirror_
    gate` (`coordinator/lib/percolate/assembled_mirror_gate.py`) into the
    driver, once per distinct destination repo root, over the SAME
    `deduped_roots` / `rows_by_repo_root` shape every sibling end-of-run leg
    in this module already uses (`dispatch_end_of_run_argv_parity_gate`,
    `dispatch_end_of_run_identity_check`, `dispatch_end_of_run_function_
    gate`) — see this file's own C4 (docs/plans/2026-08-15-bind-the-
    klabauter-publish-rows-into-a-parity-group.md) precedent for why a
    per-mirror question is answered once per assembled repo root rather
    than once per row.

    WIRING POSITION — chosen over the chunk body's literal text, recorded
    here per the EM ruling requiring the choice named in the commit
    message: the chunk body says "call it from `run_pre_sync_gates`, in
    the same position as `assert_allowlist_applied`". That position is
    PRE-SYNC, on a SINGLE row's restricted source tree — the EM ruling
    (2026-08-28, this chunk's brief) already forecloses gating pre-
    transform bytes as reproducing the exact adjacent-question defect this
    plan exists to kill, and requires either (a) materializing the content-
    transform sweep over a copy of the restricted tree at that same
    pre-sync position, or (b) — if the sweep is not callable as a function
    over an arbitrary tree — falling back to wiring the gate at the
    destination after sync but before the row is finalized/pushed.

    (a) is not available: the content-transform sweep is `engine_claude_klabauter.
    run_percolate(..., phase="post_rsync", ...)`, a JSON-RPC dispatch
    against a resolved `percolate-store.yaml` section, `dest_prefix`, and
    `sync_changed_paths` — not a standalone function over an arbitrary
    directory. It is also inherently PER-ROW: each row's own restricted
    tree is a fragment of the assembled mirror (`staging_dir` is "NOT a
    repo root -- it is `target.dest_dir`'s own subtree in isolation", §
    `dispatch_preswap_function_gate`'s own docstring), so even a
    successfully materialized per-row copy could not answer the per-MIRROR
    question C2 exists to ask — the same structural gap the parent plan's
    Problem section names as the reason C1's per-row closure gate missed
    every orphan: "a per-row gate cannot answer a per-mirror question
    however much it is widened."

    (b) is what this function implements, using the SAME "destination
    after sync, before the row is finalized/pushed" seam this module
    already built for exactly this shape: `deduped_roots` / `rows_by_
    repo_root`, the destination working tree AFTER every row has synced,
    checked here as one of the "four/five legs [that] always run" before
    `main()` decides whether to report the round clean — publishing (git
    add/commit/push of the destination) is a LATER, separate step this
    driver does not itself perform, so a refusal here still costs
    finalization, never merely a log line after the fact.

    EXEMPTIONS — `dispatch_end_of_run_assembled_mirror_gate` itself never
    reads the exemption ledger; its caller resolves `{name: reason}` via
    `_load_assembled_mirror_gate_exemptions` and passes it in as `out`-
    directed context is not the shape needed here, so lookups happen right
    below: for a FAILING `repo_root`, this function checks whether ANY row
    named in `rows_by_repo_root[repo_root]` (§ same dict every sibling leg
    already receives) has a declared exemption entry. A repo root can be
    reached by more than one publish target row (docs/reference,
    coordinator_core, coordinator/bin, ... all sharing one destination
    checkout) — declaring the exemption against any ONE of them is
    sufficient, since the exemption is debt against the ASSEMBLED tree,
    not against a particular row's contribution to it. A match WARNS
    (prints the declared reason, does not fail this repo root); no match
    is the FATAL post-condition the chunk body specifies -- "like `assert_
    allowlist_applied`'s: no override flag" -- surfaced here as `ok=False`
    for that repo root, same reporting contract (never raises) as every
    other end-of-run leg in this module.

    Never called under `--dry-run`, same as `dispatch_end_of_run_argv_
    parity_gate`: a preview run mutates no destination for this gate to
    meaningfully collect against. `target_filtered` is accepted for call-
    site symmetry with the other end-of-run legs (same signature shape);
    this gate is FAIL-HARD unconditionally, same choice and same reasoning
    as `dispatch_end_of_run_argv_parity_gate`'s own docstring: a `--target`
    subset publish is exactly the invocation shape most likely to leave the
    assembled tree skewed, never an excuse to stop checking it.

    Returns True iff every repo root's collection either passes cleanly or
    is covered by a declared exemption; False iff any repo root's
    collection errors/times out/finds an unexpected shape with no matching
    exemption, or `repo_root` is not a directory. Never raises."""
    _bootstrap_engine()
    exemptions = _load_assembled_mirror_gate_exemptions()

    # Declared-scope lookup (§ `_declared_repo_roots_carrying_coordinator_
    # core`'s own docstring): a `TargetsError` here means declared scope
    # could NOT be determined for any repo_root this round -- that is an
    # INCOMPLETE-shaped failure, never grounds to read absence as NOT-
    # APPLICABLE. `declared=None` is the "could not determine" sentinel;
    # every repo_root then falls through to `run_assembled_mirror_gate`'s
    # own default (`coordinator_core_in_declared_scope=True`), which can
    # never produce `not_applicable=True` -- a missing coordinator_core/
    # directory keeps refusing via the pre-existing `isolation_unverified`
    # path exactly as it did before this leg existed. A repo_root absent
    # from BOTH returned sets (never declared at all -- e.g. a scratch
    # tree in a test, or any future caller with an unrecognised
    # destination) gets the same safe default, never read as "declared out
    # of scope" by mere absence.
    declared: "Optional[tuple[set[Path], set[Path]]]"
    try:
        declared = _declared_repo_roots_carrying_coordinator_core()
    except TargetsError as exc:
        declared = None
        print(
            "  Error: end-of-run assembled-mirror gate could not resolve the "
            "declared target row set to determine coordinator_core scope -- "
            f"{exc.message}. Proceeding with the safe default (every "
            "destination treated as if coordinator_core IS in its declared "
            "scope), so a missing coordinator_core/ directory still refuses "
            "rather than being read as not-applicable.",
            file=sys.stderr,
        )

    ok = True
    for repo_root in repo_roots:
        if not repo_root.is_dir():
            print(
                "  Error: end-of-run assembled-mirror gate expected a destination "
                f"repo root at {repo_root} but it is not a directory -- failing "
                "hard rather than silently skipping an unassembled destination.",
                file=sys.stderr,
            )
            ok = False
            continue

        if declared is None:
            coordinator_core_in_declared_scope = True
        else:
            engine_roots, all_declared_roots = declared
            coordinator_core_in_declared_scope = (
                True if repo_root not in all_declared_roots else repo_root in engine_roots
            )
        result = run_assembled_mirror_gate(
            repo_root,
            coordinator_core_in_declared_scope=coordinator_core_in_declared_scope,
        )
        if result.not_applicable:
            # Gate does not refuse; the round proceeds. Never reaches the
            # coverage leg / passed / is_load_indeterminate / exemption
            # branches below -- there is no claim about this tree for any
            # of them to act on (see `MirrorCollectionResult.not_
            # applicable`'s own docstring for why this must be read before
            # `passed`/`is_incomplete`).
            print(
                f"  assembled-mirror-gate: NOT APPLICABLE — {repo_root} does not "
                "declare coordinator_core in scope and its tree carries none; "
                "this gate has nothing to say about this destination.",
                file=out,
            )
            continue
        # C6's inverse pass, on the same assembled tree the gate just walked:
        # a shipped subject whose tests stayed home. WARN only — plenty of
        # modules legitimately have no test, and a hard gate here would be
        # un-landable. Reported before the pass/refuse branch so the count
        # and its denominator survive a refusing round too, which is when
        # the delta between runs is most worth reading.
        # Source roots: every row's own source_dir that contributes to this
        # assembled repo_root (a destination can be fed by more than one row,
        # per this function's own docstring above) — the ground truth for
        # "did this subject's test exist at all" that keeps a never-had-a-
        # test module out of the WARN (see find_modules_missing_tests).
        #
        # Code review (2026-08-30, P2): `rows_by_repo_root.get(repo_root, [])`
        # can legitimately be empty for a `repo_root` this function still
        # walks (e.g. reached only via a row keyed under a different dict
        # entry). `source_roots or [repo_root]` used to fall back to
        # comparing the assembled mirror against ITSELF — silently
        # reinstating the exact source-vs-mirror conflation this gate's own
        # docstring (and `find_modules_missing_tests`'s) says it exists to
        # kill, with nothing in the printed line distinguishing a real
        # comparison from a self-comparison. A leg that cannot compute its
        # denominator abstains out loud instead: no source rows means no
        # ground truth for "did this subject's test exist at all", so the
        # coverage leg is skipped for this repo root and says why, rather
        # than emitting a WARN count it cannot stand behind.
        contributing_rows = rows_by_repo_root.get(repo_root, [])
        source_roots = [row.source_dir for row in contributing_rows]
        if source_roots:
            coverage = find_modules_missing_tests(repo_root, source_roots)
            # Ratified `!` denials are not payload gaps. See
            # `_drop_ratified_test_denials` -- the gate is mechanism-only and
            # delegates exemption-awareness here by name.
            coverage = _drop_ratified_test_denials(coverage, contributing_rows)
            print(format_test_coverage_warning(coverage), file=out)
        else:
            print(
                f"  assembled-mirror-gate coverage leg: SKIPPED for {repo_root} — "
                "no source row is keyed to this repo root, so there is no source "
                "tree to compare shipped modules against (never a self-comparison).",
                file=out,
            )
        if result.passed:
            print(
                f"  assembled-mirror-gate: OK — {repo_root} collected "
                f"{result.collected_count} test(s) cleanly ({result.elapsed_s:.2f}s).",
                file=out,
            )
            continue

        row_names = [row.name for row in rows_by_repo_root.get(repo_root, [])]

        if result.is_load_indeterminate:
            # A LOAD-INDETERMINATE result (a timeout, and every further
            # no-verdict cause `is_incomplete` grows) carries no claim
            # about the tree at all -- see `MirrorCollectionResult.
            # is_load_indeterminate`'s own docstring. The exemption ledger
            # waives a KNOWN, REPRODUCIBLE tree property; it has nothing to
            # waive here, so the lookup is skipped entirely rather than
            # letting a load-driven timeout on an exempted row pass through
            # this branch as declared content debt.
            #
            # The predicate is deliberately NOT `is_incomplete`: that one
            # also covers `isolation_unverified`, which is a deterministic
            # function of the destination tree's contents rather than of
            # the box, and is precisely the case the single live ledger
            # entry was declared to cover. Gating here on `is_incomplete`
            # made that entry unreachable and shut the DoE ->
            # coordinator-claude publish lane
            # (cross-repo/inbox/2026-08-31-doe-claude-em-mirror-gate-
            # completeness-reclosed-the-oss-lane.md).
            print(
                f"  Error: end-of-run assembled-mirror gate did not complete for "
                f"{repo_root} -- no declared exemption applies because this "
                "result carries no claim about the tree for an exemption to "
                f"cover ({_ASSEMBLED_MIRROR_GATE_DECLARATIONS_PATH} was not "
                "consulted).",
                file=sys.stderr,
            )
            print(format_assembled_mirror_gate_refusal(result), file=sys.stderr)
            ok = False
            continue

        exempted_reason = next((exemptions[name] for name in row_names if name in exemptions), None)
        if exempted_reason is not None:
            print(
                f"  Warning: assembled-mirror-gate REFUSED for {repo_root} but a "
                f"declared exemption covers it -- {exempted_reason}",
                file=out,
            )
            print(format_assembled_mirror_gate_refusal(result), file=out)
            continue

        print(
            f"  Error: end-of-run assembled-mirror gate FAILED for {repo_root} -- "
            "no declared exemption in "
            f"{_ASSEMBLED_MIRROR_GATE_DECLARATIONS_PATH} covers any of this root's "
            f"rows ({row_names!r}).",
            file=sys.stderr,
        )
        print(format_assembled_mirror_gate_refusal(result), file=sys.stderr)
        ok = False

    return ok


def _argv_parity_pairing_origin(repo_root: Path, rel_module: str) -> str:
    """Best-effort tag for a failing pairing's `module` path, distinguishing
    a file this run's git-tracked source content is expected to have
    published (`published-by-this-round`) from one that is present only in
    the destination working tree's own local state
    (`destination-only`) — the diagnosability aid this gate's own docstring
    HAZARD section names. Never raises; an inconclusive read reports
    `unknown-origin` rather than guessing.
    """
    module_path = repo_root / Path(rel_module)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--", rel_module],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:  # noqa: BLE001 - diagnostic aid only, never fatal
        return "unknown-origin"
    if result.returncode != 0:
        return "unknown-origin"
    if result.stdout.strip():
        return "destination-only (locally modified in the mirror working tree)"
    if module_path.exists():
        return "published-by-this-round"
    return "unknown-origin"


def _porcelain_touched_paths(stdout_bytes: bytes) -> "set[str]":
    """Extracts every path `git status --porcelain -z` reports as touched —
    both sides of a rename/copy record as well as the ordinary `XY path`
    form — used by `_argv_parity_pairing_origin_batch` to attribute a single
    multi-pathspec `git status` call's output back to the individual
    rel_module path(s) that produced it.

    Takes the raw NUL-terminated `-z` byte stream, not the `\\n`-terminated
    default text format: with `-z`, git status never C-quotes a path
    containing non-ASCII/control characters (that quoting only applies to
    the human-readable, newline-terminated form), so an exact-string match
    against the plain `rel_module` string can't silently miss an entry the
    way it could against quoted `\\n`-delimited output. `-z` renames/copies
    are two consecutive NUL-terminated fields — new path, then old path —
    with no ` -> ` separator, unlike the human-readable form.
    """
    paths: "set[str]" = set()
    fields = stdout_bytes.split(b"\0")
    i = 0
    n = len(fields)
    while i < n:
        entry = fields[i]
        i += 1
        if not entry:
            continue
        if len(entry) < 4:
            continue
        xy = entry[:2]
        path = entry[3:].decode("utf-8", errors="surrogateescape")
        paths.add(path)
        if b"R" in xy or b"C" in xy:
            # Rename/copy: the next NUL-terminated field is the old path,
            # not a fresh `XY path` record.
            if i < n and fields[i]:
                paths.add(fields[i].decode("utf-8", errors="surrogateescape"))
                i += 1
    return paths


def _argv_parity_pairing_origin_batch(
    repo_root: Path, rel_modules: "list[str]"
) -> "dict[str, str]":
    """Batched sibling of `_argv_parity_pairing_origin` — issues ONE `git
    -C <repo_root> status --porcelain -z -- <rel_module1> <rel_module2> ...`
    spawn covering every failing pairing's `module` path for this
    `repo_root`, instead of one spawn per pairing
    (docs/plans/2026-08-19-burn-down-the-amplification-hitlist.md C5).
    Every rel_module here shares the same `repo_root` (the outer loop
    variable at the call site), so — unlike `_git_head`'s per-row callers,
    which each name a DIFFERENT repo root and so cannot share a spawn —
    this is exactly the pathspec-shaped batching `_git_ls_tree_entries_files`
    already applies one level up (multiple entries, one shared `-C` root).

    Preserves `_argv_parity_pairing_origin`'s per-entry verdict exactly on
    the success path: each `rel_module` is independently classified by
    whether IT (not some other batched entry) appears in the porcelain
    output (`_porcelain_touched_paths`), falling back to
    `module_path.exists()` exactly as the per-item version does.

    On a batch-level spawn failure or non-zero exit, this falls back to
    calling `_argv_parity_pairing_origin` once per `rel_module` rather than
    mapping the whole set to `"unknown-origin"` — review finding amp-s1 #3:
    a single flaky/timed-out batched spawn previously blinded every pairing
    in the batch, even ones a working per-item call would still have
    resolved. This is diagnostic text for an already-failing gate, spawned
    only on the rare failure path, so it does not reintroduce the
    per-pairing spawn amplification the batching exists to remove in the
    common case. Returns `{}` for an empty `rel_modules`.
    """
    if not rel_modules:
        return {}
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "-z", "--", *rel_modules],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:  # noqa: BLE001 - diagnostic aid only, never fatal
        return {rel_module: _argv_parity_pairing_origin(repo_root, rel_module) for rel_module in rel_modules}
    if result.returncode != 0:
        return {rel_module: _argv_parity_pairing_origin(repo_root, rel_module) for rel_module in rel_modules}

    touched = _porcelain_touched_paths(result.stdout)
    origins: "dict[str, str]" = {}
    for rel_module in rel_modules:
        if rel_module in touched:
            origins[rel_module] = "destination-only (locally modified in the mirror working tree)"
        elif (repo_root / Path(rel_module)).exists():
            origins[rel_module] = "published-by-this-round"
        else:
            origins[rel_module] = "unknown-origin"
    return origins


def _argv_parity_pairing_origin_batch_by_root(
    rel_modules_by_root: "dict[Path, list[str]]",
) -> "dict[Path, dict[str, str]]":
    """Multi-root sibling of `_argv_parity_pairing_origin_batch`, called
    exactly ONCE by `dispatch_end_of_run_argv_parity_gate` regardless of how
    many roots have failing pairings — the call site that function's own
    loop over `repo_roots` used to hold directly. A `git status` process is
    still spawned once per DISTINCT root in `rel_modules_by_root` (no git
    invocation can span multiple `-C` roots at once, the same structural
    floor `_git_ls_tree_entries_files`'s own per-root call in
    that helper accepts), but that per-root fan-out
    is now entirely internal to this one function rather than driven by a
    loop the caller controls. Returns `{}` for an empty mapping.
    """
    return {
        repo_root: _argv_parity_pairing_origin_batch(repo_root, rel_modules)
        for repo_root, rel_modules in rel_modules_by_root.items()
    }


_UNSCANNED_EXCEPTIONS_PATH = Path(__file__).resolve().parent / "percolate-published-unscanned-exceptions.yaml"
# `.git`/`.fleet-env` are destination-repo plumbing / a dest-local virtualenv,
# never touched by any row's sync — a STRUCTURAL exclusion from
# dispatch_end_of_run_unscanned_published_check's "published" set, not a ratified
# content exception. See that function's own docstring for the full rationale.
# Sourced from `coordinator_core.percolate.surface.STRUCTURAL_NEVER_PUBLISHED_
# PREFIXES` — the single shared tuple `guards._walk_for_guard` and
# `engine.run_parse_sweep`/`run_content_transform_sweep` also derive their own
# copies from, so a name added there cannot drift out of sync with this
# full-repo-walk leg. Resolved lazily inside `_is_structurally_never_published`
# (via `_import_percolate_surface_module`, the same engine-root-already-on-
# sys.path idiom every other percolate import in this file uses) rather than at
# module-import time, because the engine root is not yet resolved when this module
# is first imported.
# `__pycache__/` is a LOCALLY-GENERATED build artifact, not something any
# row's sync ever copies into the destination (verified:
# `coordinator/lib/percolate/publish_sync.py` contains zero `__pycache__`/
# `.pyc` references, same as the `.git` rationale above) — anything that
# subsequently RUNS Python inside the destination clone (a pytest run, a
# stray `python -m` invocation) recreates `__pycache__/*.pyc` there on its
# own, with no row ever having "published" it. First measured live: a real
# `claude-klabauter-publish-repo-toplevel` run reported 499 such entries,
# every one `coordinator_core/**/__pycache__/*.pyc` — pure noise that drowns
# a real finding, not a content decision, so (like `.git`) it is a
# STRUCTURAL exclusion at the mechanism level, never a per-file ratified
# exception (which would mean one entry per generated `.pyc` filename
# forever, on every Python version bump, the exact two-tables-rot shape this
# whole workstream exists to close). Detection itself lives in
# `percolate.publish_sync._is_structural_build_artifact` — shared with that
# module's own orphan-sweep guard, see `_is_structurally_never_published`
# below for how this function delegates to it.


def _is_structurally_never_published(path: Path, repo_root: Path) -> bool:
    """True iff `path` (a file under `repo_root`) is excluded from the
    `published` set at the mechanism level — `.git/*` plumbing, a dest-local
    `.fleet-env/*` virtualenv, `__pycache__/*` build-artifact directories, or a
    stray `*.pyc`/`*.pyo` outside one (the rare pre-`__pycache__`-layout shape,
    still bytecode a row never publishes). Kept as one predicate so both
    `published`-set comprehensions in
    `dispatch_end_of_run_unscanned_published_check` stay in lockstep rather
    than drifting via copy-paste.

    `__pycache__`/`.pyc`/`.pyo` detection delegates to `percolate.publish_sync
    ._is_structural_build_artifact` — the SAME predicate the orphan-sweep /
    top-level-presence guard in that module now uses, so the two guards
    cannot silently disagree about what counts as a locally-generated build
    artifact.

    `.git`/`.fleet-env` stay local to this function rather than folding into
    `_is_structural_build_artifact`: `_is_structurally_never_published` walks a
    WHOLE repo tree (including `.git/` and a dest-local `.fleet-env/`) that
    `publish_sync.py` has no equivalent for — that module's callers only ever
    see already-restricted rel_path strings with every dot-prefixed top-level
    directory (`.git`, `.fleet-env` alike) already filtered out upstream
    (`_sync_mirror_top_level_files`'s `not p.name.startswith(".")`, the
    orphan-sweep's own `non_dot_dst` filter — see that module's own comment on
    this split), so a `.fleet-env` name reaching `_is_structural_build_
    artifact` there would be dead code, never a live input. Sourced from
    `coordinator_core.percolate.surface.STRUCTURAL_NEVER_PUBLISHED_PREFIXES`
    (§ module comment above) rather than a local literal, so this leg cannot
    silently diverge from `guards._walk_for_guard`/`engine.run_parse_sweep`'s
    own copies of the same tuple.

    PUBLISH-STAGING LEFTOVERS ARE STRUCTURAL HERE TOO, via the same
    `surface.PUBLISH_STAGING_DIR_RE` SSOT the content-transform sweep prunes
    on. This was the FIFTH consumer of that predicate and the last to get it:
    while `iter_surface_files` still walked into staging directories, their
    files landed in BOTH the `published` set and the `visited` set and the
    subtraction came out empty, so the asymmetry was invisible. The moment the
    sweep began pruning them, `published` still listed them and `visited` no
    longer did -- and every file under a stray `.prior` staging directory
    reported as published-but-unscanned. The bytes never ship either way; a
    directory the sweep is not allowed to enter cannot be held against it for
    not having been entered.

    Matched against DIRECTORY segments only, never the basename: a *file*
    named `x-publish-staging-y.py` is real shipped payload, the same
    distinction `store.py` and `engine.run_parse_sweep` already draw."""
    _bootstrap_engine()
    surface_module = _import_percolate_surface_module()
    structural_prefixes = surface_module.STRUCTURAL_NEVER_PUBLISHED_PREFIXES
    parts = path.relative_to(repo_root).parts
    if any(surface_module.PUBLISH_STAGING_DIR_RE.search(part) for part in parts[:-1]):
        return True
    # Routed through `matches_exclude_prefix` rather than a hand-rolled membership
    # test: that helper is the tuple's own match algorithm (the three other call
    # sites already use it), and since 2026-08-20 the tuple carries one entry --
    # `.fleet-env.gen-*` -- whose segment is unbounded and which a bare `in` test
    # therefore silently fails to match. Full path, not the parent only: unlike
    # `engine.run_parse_sweep`, this walk never admits a file BY basename, so a
    # nested file named exactly `.git`/`.fleet-env` is plumbing here too.
    if surface_module.matches_exclude_prefix("/".join(parts), list(structural_prefixes)):
        return True
    return _is_structural_build_artifact("/".join(parts))


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
    called, `_import_claude_klabauter_percolate()` has already resolved the engine root
    onto `sys.path`, so this is a plain import, not a second
    spec_from_file_location dance. Kept as its own function (rather than a
    bare inline import at the call site) so the import failure path has one
    named place to raise from, matching this file's other `_import_*`
    helpers."""
    import coordinator_core.percolate.surface as _surface_module

    return _surface_module


def _import_percolate_rewrite_basename_module():
    """Import `coordinator_core.percolate.rewrite_basename` — same idiom as
    `_import_percolate_surface_module` (the engine root is already on
    `sys.path` by the time this is called). Needed by `process_target` to
    read a mirror-mode row's rename-generation ledger BEFORE dispatching
    sync, so a directory this pass's rename is about to reproduce can be
    exempted from `sync_mirror`'s orphan-deletion (§ that function's own
    `renamed_dir_names` docstring; state/audits/2026-08-05-first-full-
    payload-identity-findings.md Group E)."""
    import coordinator_core.percolate.rewrite_basename as _rewrite_basename_module

    return _rewrite_basename_module


def _import_percolate_store_resolve_target():
    """Import `coordinator_core.percolate.store.resolve_target` directly —
    same engine-root-already-on-sys.path idiom as
    `_import_percolate_rewrite_basename_module`. `process_target`'s
    `renamed_dir_names` block (§ that block's own comment) needs the row's
    STATIC `basename_rename` section, which is a pure function of `store` +
    `target.name` with no dependency on a live `ClaudeKlabauterPercolate` instance —
    calling the module-level function directly (rather than
    `engine_ctx.engine_claude_klabauter.resolve_target`) keeps that block usable even
    when `engine_claude_klabauter` is a minimal double that only stands in for "is
    not None" (§ dry-run callers that never dispatch a real engine phase)
    and has no `resolve_target` method of its own."""
    import coordinator_core.percolate.store as _store_module

    return _store_module.resolve_target


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

    `_is_structurally_never_published` (`.git/*`, `__pycache__/*`,
    stray `*.pyc`/`*.pyo`) is excluded from the
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
                if p.is_file() and not _is_structurally_never_published(p, repo_root)
            }
        else:
            published = {
                p
                for p in repo_root.rglob("*")
                if p.is_file() and not _is_structurally_never_published(p, repo_root)
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
    (`cc_invoke.resolve_engine_root` -> `coordinator_core.percolate.
    runtime_root.coordinator_percolate_runtime_root`) the bash original
    invoked via a `python3 -c` subprocess — here it is a direct in-process
    call since this driver is already Python. `resolve_engine_root()` adds a
    self-location walk-up rung (from this file's own location) ahead of the
    settings-home pointer / machine-local registry rungs, so this call no
    longer depends on the registry having been populated on this machine.

    Fallback order on ANY native-resolver failure (missing cc_invoke.py,
    an unresolvable engine root, missing coordinator_core.percolate.runtime_root
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
         native-resolver failure (missing cc_invoke, an unresolvable
         engine root) — a case rung 1's in-process pointer rung structurally
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

            module.ensure_engine_on_path(__file__)

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
    """Best-effort `<engine root>/coordinator/bin`, or None if unresolvable.

    Uses the same `cc_invoke.ensure_engine_on_path()` seam as
    `_import_claude_klabauter_percolate`, so it honours the self-location / registry /
    pointer resolution chain rather than guessing a sibling-directory layout.
    `ensure_engine_on_path` is itself best-effort (returns None rather than
    raising on failure), matching this function's own degrade posture:
    it backs an optional lookup rung, and an unresolvable engine root should
    degrade to the caller's own diagnostic rather than crash target
    resolution.
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
        claude_klabauter_root = module.ensure_engine_on_path(__file__)
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
    # Resolved through the same engine-root seam the rest of this module uses, so it
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
    _bootstrap_engine()
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
    _bootstrap_engine()
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


# ---------------------------------------------------------------------------
# Publish provenance record — docs/plans/2026-08-19-the-published-engine-
# says-what-it-was-published-from.md (C1). `_round_pin_source_sha` already
# resolves and prints the round-pinned sha per contributing git toplevel;
# nothing durable survives the round, so no consumer can later answer "which
# revision of claude-klabauter is actually running in the published build?" (the
# DR-326 stale-dispatch incident this plan documents). This record is that
# durable answer — machine-local, written once at round end, read-only for
# every consumer (the C2 doctor probe).
# ---------------------------------------------------------------------------
def _publish_provenance_record_path() -> Path:
    """Machine-local publish-provenance record location: settings-home
    `machine-local/publish-provenance.json`, beside `.claude-klabauter-root`
    (Anti-scope 2 — never in the published tree; every consumer of this
    record is on this box). Mirrors `_machine_local_percolate_identity_path`'s
    env-var precedence: `COORDINATOR_SETTINGS_HOME` wins if set, else a path
    relative to `CLAUDE_HOME`, else a path relative to the platform home
    directory."""
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or str(Path.home()), ".coordinator-claude-settings"
    )
    return Path(settings_home) / "machine-local" / "publish-provenance.json"


def write_publish_provenance_record(
    *,
    succeeded_row_names: "List[str]",
    failed_row_names: "List[str]",
    skipped_row_names: "List[str]",
    rows_by_name: "dict[str, ResolvedTarget]",
    round_pinned_shas: "dict[str, str]",
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> None:
    """Persist, per row, whether it published and — for rows that did — the
    git toplevel(s) it published from and the sha `_round_pin_source_sha`
    pinned for each (AC1). A row in `failed_row_names` or `skipped_row_names`
    is recorded with `"published": false` and NO sha (Anti-scope 3, AC2) —
    never folded into a round-wide claim; the record must never assert the
    mirror carries code a specific row's own outcome contradicts.

    MERGES FORWARD; DOES NOT DESCRIBE ONE ROUND. Rebuilding `rows` from this
    round's names alone made a row the round did not reach VANISH, which is
    indistinguishable from a row that has never published — so a mirror
    falling arbitrarily far behind source raised nothing anywhere. Found
    2026-08-26: DoE's OSS mirror sat ~3h behind `c67e4984d` while the live
    record listed only the nine `claude-klabauter-*` rows of the last round,
    with no `coordinator-claude` entry at all; the lag had to be found by
    hand-diffing two mirrors (doe-claude-em, same finding independently).
    Rows this round reached are overwritten; rows it did not are carried
    forward verbatim, so a stored sha always answers "published from what,
    last time it published". `rows_in_last_round` names which rows the most
    recent round actually reached, so carried-forward stays distinguishable
    from just-published without reading two files.

    A row that FAILED or was SKIPPED this round keeps `"published": false`
    and no sha of its own, exactly as before — but its prior success, if any,
    is preserved under `last_published` rather than erased. Anti-scope 3
    forbids asserting a sha for THIS round's outcome; it does not require
    forgetting that the row ever published, and forgetting is what made the
    lag invisible.

    Does not touch `write_delta_record`/`_delta_state_path`/
    `delta_row_unchanged`/`_delta_row_source_sha` (Anti-scope 1) — this is a
    wholly separate, always-attempted record, not a repurposing of the delta
    optimization cache.

    Failure posture (plan body, "Failure posture"): any exception writing
    this record is caught here and warned to `err`; the round's own exit
    code is untouched by design — the round publishing correctly matters
    more than this record, and a missing/stale record is read by the C2
    probe as "unknown", which is honest (AC5)."""
    _bootstrap_engine()
    try:
        now = datetime.now(timezone.utc).isoformat()
        # Prior rows are the starting state, not a fresh dict — see the
        # merge-forward paragraph above. An unreadable or absent record
        # degrades to "no prior rows" rather than failing the write: the
        # round's own outcome must still be recorded.
        prior_rows: "dict[str, Any]" = {}
        try:
            prior_raw = json.loads(
                _publish_provenance_record_path().read_text(encoding="utf-8")
            )
            if isinstance(prior_raw, dict) and isinstance(prior_raw.get("rows"), dict):
                prior_rows = prior_raw["rows"]
        except (OSError, ValueError):
            prior_rows = {}

        def _carried_last_published(name: str) -> "dict[str, Any]":
            """The row's last SUCCESSFUL publish, carried across a round that
            did not publish it. Reads either shape: an entry written before
            this merge-forward change holds its sha inline; one written after
            already carries a `last_published` block."""
            prior = prior_rows.get(name)
            if not isinstance(prior, dict):
                return {}
            if prior.get("published") and prior.get("toplevels"):
                return {
                    "last_published": {
                        "at": prior.get("published_at"),
                        "toplevels": prior["toplevels"],
                    }
                }
            carried = prior.get("last_published")
            return {"last_published": carried} if isinstance(carried, dict) else {}

        rows: "dict[str, Any]" = dict(prior_rows)
        for name in succeeded_row_names:
            target = rows_by_name.get(name)
            toplevels: "dict[str, str]" = {}
            if target is not None:
                for root in _contributing_roots(target):
                    # `repo_root.show_toplevel` WALKS ONLY and never spawns, on
                    # any path (38ada515b) — a `_git_rev_parse_detailed` here is
                    # O(rows x roots) git spawns on the round-end path, which the
                    # amplification collector reads as a per-item spawn in a
                    # qualifying loop. Per-root degrade is deliberate: one
                    # unresolvable root must not cost the others their sha, which
                    # is the property a naive batch would trade away.
                    toplevel_stdout = _resolve_show_toplevel(str(root))
                    if toplevel_stdout is None:
                        continue
                    toplevel_key = str(Path(toplevel_stdout))
                    sha = round_pinned_shas.get(toplevel_key)
                    if sha is not None:
                        toplevels[toplevel_key] = sha
            # A succeeded row whose toplevel(s) could not be resolved back to
            # a pinned sha (should not happen — the round-start pre-pin pass
            # already walked every contributing root — but honesty over
            # optimism per AC5) is recorded as not-published rather than
            # asserting a sha it cannot back up.
            rows[name] = (
                {"published": True, "toplevels": toplevels, "published_at": now}
                if toplevels
                else {"published": False, "last_attempt_at": now, **_carried_last_published(name)}
            )
        for name in list(failed_row_names) + list(skipped_row_names):
            rows[name] = {
                "published": False,
                "last_attempt_at": now,
                **_carried_last_published(name),
            }

        record = {
            "completed_at": now,
            "rows": rows,
            "rows_in_last_round": sorted(
                set(succeeded_row_names) | set(failed_row_names) | set(skipped_row_names)
            ),
        }
        record_path = _publish_provenance_record_path()
        record_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = record_path.with_name(record_path.name + f".tmp-{os.getpid()}")
        tmp_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp_path, record_path)
    except Exception as exc:  # noqa: BLE001 - never gate the round on this write
        print(
            f"[publish.py] WARNING: could not write publish provenance record ({exc}); "
            "a doctor probe reading it will report 'unknown' rather than 'current'.",
            file=err,
        )


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
    if not (norm_dest == live_root or norm_dest.startswith(live_root + os.sep)):
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
        # No repo-wide `marketplace.json` exists in this tree at all (verified
        # by a full-tree search, not inferred from this one row) — every row
        # takes this branch, every run. Said explicitly here rather than left
        # as a silent True, so this reads as "inapplicable to this target"
        # and not as "checked, no regression found."
        print(f"  Version-regression gate: N/A for {name} — no marketplace.json present.", file=out)
        return True

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
        # Same repo-wide absence as `check_marketplace_version_regression`
        # above — no row in this tree ships a `.claude-plugin/marketplace.json`,
        # so this branch is taken every row, every run. Stated explicitly so
        # it reads as "not applicable to this target," not as a pass.
        print(f"  Version-consistency gate: N/A for {name} — no .claude-plugin/marketplace.json present.", file=out)
        return True

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
    _bootstrap_engine()
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


#: Memoized `_field7_declaration_check` result for this process — one publish
#: round is one process, and the validator reads the same two files whichever
#: row asks, so running it once keeps this gate at the two `git ls-files`
#: spawns the validator itself costs rather than two per row.
_FIELD7_DECLARATION_CHECK: "Optional[tuple[bool, str, Optional[frozenset]]]" = None


def _load_allowlist_generator():
    """Load `publish-allowlist-generate.py` by path — its filename carries
    hyphens and is not an importable module name, the same reason
    `coordinator/tests/test_publish_allowlist_generate.py` loads it this way."""
    generator_path = Path(__file__).resolve().parent / "publish-allowlist-generate.py"
    spec = importlib.util.spec_from_file_location(
        "_publish_allowlist_generate", generator_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _field7_declaration_check() -> "tuple[bool, str, Optional[frozenset]]":
    """Run `publish-allowlist-generate.py --check` in-process, once per round,
    and return `(ok, message, generator_owned_row_names)`.

    WHY THIS EXISTS. `publish-allowlist-generate.py` derives field 7 of the two
    `claude-klabauter*` rows from `setup/publish-allowlist-declarations.yaml`.
    When it refuses — a stale (no-longer-tracked) `deny` entry, a missing AC9
    contract root, a directory-granular name denied or untracked — it writes
    nothing and field 7 keeps its last good value. Every gate downstream then reads a
    CSV that is internally consistent, importable, and no longer what the
    declarations imply, and the round publishes green. That happened three
    times on 2026-09-01, and `--check` had been red at HEAD since 2026-08-28
    with an open backlog row naming it, because nothing between a red `--check`
    and a published mirror stopped the mirror
    (`state/bug-backlog/2026-08-28-the-publish-path-never-runs-the-validator-
    that-declares-its-allowlist-valid.yaml`, whose negative spec forbids
    closing this by adding `--check` to yet another test — three already
    existed and all three were red).

    This is the production caller that validator never had, and it is the same
    promotion `find_import_closure_violations` got on 2026-08-13 after two
    broken mirror rounds shipped past a detector that lived only inside a test
    file. See `run_pre_sync_gates` for the wiring.

    WHY RE-DERIVATION RATHER THAN A STAMP. Field 7 could have carried the tree
    state it was generated from, so a stale one reads as stale. That is a
    second artifact needing its own freshness guarantee — the defect wearing a
    hat. Re-deriving at publish time has no cached half that can itself go
    stale, and it compares CONTENT rather than asking which file is older: a
    field 7 can be NEWER than its sources and still wrong, because the
    generator that would have changed it never ran to completion. The stamp
    axis cannot close that, and for this artifact it cannot even be declared —
    `setup/publish-targets.portable` is `#`-commented pipe-delimited text with
    no `.json` key and no `---` frontmatter, so `compute_pair_staleness`
    short-circuits UNSTAMPED before it reaches `sources`
    (measured by claude-klabauter-a8, 2026-09-01).

    Fail-closed on its own failure to run: if the validator cannot be loaded or
    raises, the third element is None, meaning "row scope unknown — refuse
    every allowlisted row". A gate that cannot say which rows it governs must
    not silently govern none, and this driver aborts rather than degrades
    everywhere else it cannot complete a check (see the module docstring's
    AC15 fail-closed paragraph). This is NOT the DR-402 case: that decision
    governs a session-hot-path guard whose engine is unreachable, and its
    § "What this does NOT license" is explicit that its allow rung is for a
    guard that could not run, never a publish path granting itself a bypass."""
    global _FIELD7_DECLARATION_CHECK
    if _FIELD7_DECLARATION_CHECK is not None:
        return _FIELD7_DECLARATION_CHECK

    try:
        module = _load_allowlist_generator()
        owned = frozenset(row_name for row_name, _src in module._ROWS)
    except Exception as exc:
        _FIELD7_DECLARATION_CHECK = (
            False,
            f"the field-7 declaration validator could not be loaded: {exc}",
            None,
        )
        return _FIELD7_DECLARATION_CHECK

    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured), contextlib.redirect_stdout(io.StringIO()):
            rc = module.main(["--check"])
    except Exception as exc:
        _FIELD7_DECLARATION_CHECK = (
            False,
            f"the field-7 declaration validator raised: {exc}",
            owned,
        )
        return _FIELD7_DECLARATION_CHECK

    _FIELD7_DECLARATION_CHECK = (rc == 0, captured.getvalue().strip(), owned)
    return _FIELD7_DECLARATION_CHECK


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
    round_pinned_shas: "Optional[dict[str, str]]" = None,
    out: IO[str] = sys.stdout,
    err: IO[str] = sys.stderr,
) -> GateResult:
    """Runs the per-target GATES `setup/publish.sh` runs between "source path
    validated" and "sync dispatched", in the same order as the
    bash original: live-install-clobber, version-regression,
    version-consistency, machine-slug warn. (The identity-file owner+mode
    check is NOT run here — it runs once at driver startup, see `main` —
    `identity_file_exists`/`identity` are its already-computed results,
    threaded through for the machine-slug warn.)

    Before any gate reads source bytes, every contributing root
    (docs/plans/2026-08-04-publish-from-a-committed-ref.md C1b) is
    materialized from its committed ref via `_git_materialize_ref` — pinned to
    the round-wide sha in `round_pinned_shas` (§ `_round_pin_source_sha`) rather
    than a fresh per-call `HEAD` resolution, so every row in this round
    reads the same commit for a shared toplevel even if HEAD moves mid-round. `GateResult.source_dir`
    is UNCONDITIONALLY the shadow of `target.source_dir` from that point on —
    never the target's raw resolved `source_dir` — so even a row with no
    declared allowlist (which never enters the branch below) publishes from a
    committed ref, not the live tree. `check_marketplace_version_regression`
    and `check_version_consistency` run AFTER materialization for the same
    reason: they read raw source directly, so reading the live tree there
    could ship a version regression past the gate that exists to stop it.
    A dirty source tree is NOT a gate of any kind here and never slows a
    publish down: the bytes always come from the committed ref, so
    uncommitted peer edits can neither leak into the published output nor
    refuse the row. When an allowlist IS declared, `build_allowlisted_source` narrows the
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
    _bootstrap_engine()
    # `round_pinned_shas` defaults to a fresh, call-scoped dict when the
    # caller supplies none (e.g. a test exercising this function in
    # isolation) — degrades to "pin once per THIS call" rather than "pin
    # once per round", since there is no round to share across without a
    # caller-supplied dict. The production call site (`main`) always passes
    # its own round-wide dict, which is what actually closes the mid-round
    # HEAD-drift window this pin exists for.
    if round_pinned_shas is None:
        round_pinned_shas = {}

    if not check_live_install_clobber(target.dest_dir, target.name, dry_run=dry_run, out=out, err=err):
        return GateResult(proceed=False, source_dir=target.source_dir)

    contributing_roots = _contributing_roots(target)

    # Materialize every contributing root from a committed ref (docs/plans/
    # 2026-08-04-publish-from-a-committed-ref.md C1b) BEFORE any gate reads
    # source bytes. `shadow` maps every real contributing
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
    # root.
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
    # Per-root pinned sha, kept so the engine build stamp below names the SAME
    # sha this round already pinned and printed as provenance, rather than
    # re-deriving one that could differ if the tip moved mid-round.
    root_shas: "dict[Path, str]" = {}
    try:
        for root in contributing_roots:
            # Round-pinned sha (docs/plans/2026-08-04-publish-from-a-committed-
            # ref.md C1b amendment) — resolved ONCE per (round, toplevel) via
            # `round_pinned_shas`, never a fresh per-call `HEAD` read, so this
            # sha is IDENTICAL to whatever `main`'s round-start pass (or an
            # earlier row's late pin) already recorded. `late=True`: any pin
            # happening here is by definition after round start.
            sha = _round_pin_source_sha(root, round_pinned_shas, out=out, late=True)
            shadow[root] = _git_materialize_ref(root, ref=sha)
            root_shas[root] = sha
            print(f"  Provenance: {root} shipped from {sha}", file=out)
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

    # These gates read raw source directly (docs/plans/2026-08-04-publish-
    # from-a-committed-ref.md C1b), so they run AFTER materialization.
    # Reading `target.source_dir` here, before
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

        # Field-7 declaration gate (§ `_field7_declaration_check`): refuse a row
        # whose field 7 is no longer what `setup/publish-allowlist-
        # declarations.yaml` derives, or whose derivation cannot be computed at
        # all. Fail-closed, no override env var — the same discipline as
        # `assert_allowlist_applied` and `find_import_closure_violations` below,
        # and for the same reason: a stale allowlist has no legitimate "publish
        # anyway" case, because the row ships a set nobody declared.
        #
        # Runs FIRST inside this branch, before `build_allowlisted_source`: the
        # check reads only `target.allowlist` and the two declaration files, so
        # a row refused here never builds a restricted tree there is then
        # nothing to clean up.
        _field7_block_start = time.perf_counter()
        try:
            decl_ok, decl_message, decl_rows = _field7_declaration_check()
            if not decl_ok and (decl_rows is None or target.name in decl_rows):
                print(
                    f"  Error: {target.name}'s field-7 allowlist is not what "
                    f"setup/publish-allowlist-declarations.yaml derives — the "
                    f"declaration validator is RED, so this row would publish a set "
                    f"nobody declared:",
                    file=err,
                )
                for line in (decl_message or "(the validator reported no detail)").splitlines():
                    print(f"    {line}", file=err)
                print(
                    "  Remedy: run coordinator/bin/publish-allowlist-generate.py "
                    "(without --check) and commit the regenerated field 7, or fix "
                    "the declaration it names.",
                    file=err,
                )
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))
        finally:
            print(
                f"  [timing] {target.name}: run_pre_sync_gates: field7_declaration_check: "
                f"{time.perf_counter() - _field7_block_start:.3f}s",
                file=out,
            )

        source_map_dict = _parse_source_map(target.source_map)
        shadow_source_map = {entry: shadow[root] for entry, root in source_map_dict.items()}
        _allowlist_block_start = time.perf_counter()
        try:
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
        finally:
            print(
                f"  [timing] {target.name}: run_pre_sync_gates: allowlist "
                f"(build_allowlisted_source + check_working_data_paths): "
                f"{time.perf_counter() - _allowlist_block_start:.3f}s",
                file=out,
            )

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

        # Import-closure gate (2026-08-13, docs/plans/2026-08-13-the-publish-
        # round-fails-closed-on-an-imp.md): runs LAST, on the actual
        # restricted tree that will publish — this is the production caller
        # `find_import_closure_violations` previously had none of; two
        # broken mirror rounds shipped past a red detector because this
        # check lived only inside a test file. Fail-closed, no override env
        # var — the closure defect it catches (a published module dead on
        # import) has no legitimate "publish anyway" case.
        # Scoped to rows whose restricted tree IS the `coordinator_core`
        # package, because that is the only shape the detector's central
        # question — "does this name resolve INSIDE this tree" — is
        # meaningful for. Every other allowlisted row publishes a `bin/` or
        # `lib/` tree whose files legitimately import `coordinator_core`
        # names that resolve from the SEPARATELY published package row, not
        # from within their own tree; running the gate over those trees
        # reports every such import as unresolved (measured 2026-08-13: 372
        # on `claude-klabauter-coordinator-bin`, 18 on the two lib rows, 4 on
        # `-scripts`, all false) and fails the whole round closed. Widening
        # this to non-package rows needs a cross-row resolver that knows
        # which OTHER row carries `coordinator_core`, which this gate
        # deliberately does not have.
        closure_examined, closure_violations = (
            find_import_closure_violations(restricted_tmp_src)
            if target.source_dir.name == _CLOSURE_PACKAGE_NAME
            else (0, [])
        )
        if target.source_dir.name == _CLOSURE_PACKAGE_NAME:
            # Report the denominator, always, including on the clean path:
            # "0 violations over 0 files examined" and "0 over 2131" are the
            # same output without it, so a gate that silently examined
            # nothing reads exactly like a gate that passed.
            print(
                f"  Import-closure gate: {len(closure_violations)} violation(s) "
                f"over {closure_examined} file(s) examined.",
                file=out,
            )
        if closure_violations:
            print(
                f"  Error: {len(closure_violations)} import-closure violation(s) in "
                f"{target.name}'s restricted publish tree — a published module "
                "imports a coordinator_core top-level name the restricted tree "
                "does not contain:",
                file=err,
            )
            for rel, entry in closure_violations:
                print(f"    {rel}: {entry}", file=err)
            print(
                "  Remedy: either allowlist the missing entry in this row's field 7, "
                "or the importing module should not be publishing this import.",
                file=err,
            )
            shutil.rmtree(restricted_tmp_src, ignore_errors=True)
            print("", file=out)
            return GateResult(proceed=False, source_dir=target.source_dir, shadow_roots=tuple(shadow_toplevels))

        # Engine build stamp — written into the restricted tree LAST, after
        # every gate above has passed, so a refused round never ships one.
        #
        # Not dot-prefixed: `_sync_mirror_top_level_files` skips dotfiles, so a
        # dot-named stamp is built and then silently dropped.
        #
        # WHY IT EXISTS: the warm engine's generation token is embedded in its
        # pipe name, and keyed on the git ref it rotated every ~32s on a shared
        # branch (measured 2026-08-18) because any of 50-70 sessions committing
        # anything moved the ref. Each rotation stranded the resident server, so
        # warm served 0/6 with the feature correctly wired. A published tree
        # carrying this stamp rotates its generation when a publish ships new
        # engine code and at no other time — see
        # `coordinator_core.warm.skew.compute_client_token`.
        #
        # THAT LAST SENTENCE WAS ASPIRATIONAL UNTIL 2026-08-21, and the writer
        # here, not the reader in skew.py, was the half breaking it: this row's
        # `root_shas[target.source_dir]` is round-pinned raw toplevel HEAD
        # (`_round_pin_source_sha`), which moves on every commit to the shared
        # branch, not only an engine-touching one — so every round rewrote the
        # stamp regardless of content and the token rotated every ~9min publish
        # cycle right back to the coarseness this stamp exists to remove.
        # Measured: 55%/33% of warm generations exited skew/superseded at
        # medians of ~7min/~2.5min against a 15min idle deadline. Fixed by
        # `_scoped_engine_stamp_sha` below, which is now what makes the promise
        # true, not this comment.
        #
        # Scoped by the SAME predicate as the closure gate above: only the row
        # whose restricted tree IS the `coordinator_core` package. Every other
        # row publishes a `bin/`/`lib/` tree that is not an engine root, and a
        # stamp there would name a generation nothing reads.
        #
        # Written here rather than committed into the source tree because a
        # LIVE WORKING TREE must NOT carry a stamp: its engine code changes
        # between publishes, and a stamp would pin the generation while the code
        # moved. Absent-stamp is the working tree's correct state, not an
        # oversight.
        if target.source_dir.name == _CLOSURE_PACKAGE_NAME:
            round_pinned_sha = root_shas.get(target.source_dir, "unpinned")
            stamp_sha = _scoped_engine_stamp_sha(target.source_dir, round_pinned_sha, out=out)
            stamp_path = Path(restricted_tmp_src) / _ENGINE_STAMP_FILENAME
            stamp_path.write_text(f"sha:{stamp_sha}\n", encoding="utf-8", newline="\n")
            print(f"  Engine build stamp: {_ENGINE_STAMP_FILENAME} = sha:{stamp_sha}", file=out)

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
    """Content-aware copy-needed check. Returns True (needs copy) when dst
    is missing, or bytes differ from src. Returns False whenever dst exists
    and bytes match — regardless of mtime.

    Deliberately drops the former mtime-newer-than-dst trigger (the bash
    `files_differ` port this used to mirror): source rows are materialized
    from a committed ref via `git archive` + extraction (§
    `_extract_git_archive`), so every source file's mtime is the
    extraction timestamp — always "now", always newer than any prior
    destination file, regardless of whether the underlying bytes actually
    changed. That made every publish of a materialized row log a wall of
    `UPDATE:` lines (and perform a needless `shutil.copy2`) even when the
    destination's tracked git diff was empty — see task brief "Deliverable
    3 — honest change reporting". A caller that skips this check entirely
    (dst exists, bytes identical) must not print/count a change and must
    not write — that contract now holds unconditionally, which is also
    what makes `--delta`'s destination-drift detection (§ `_git_is_clean`)
    sound: a byte-identical destination is provably unchanged."""
    if not src.is_file():
        return True
    if not dst.is_file():
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
# Round timing (docs/plans/2026-08-16-percolate-round-timing-and-changed-
# only.md, chunk C1) — nothing has ever timed a percolate round; every cost
# claim before this chunk was structural inference from a code read, not
# measurement. `_time_phase` wraps one `dispatch_*` call or one
# `process_target`-owned phase in a `perf_counter` span and appends
# `(row_label, phase_label, elapsed_seconds)` to `sink` when one is supplied
# — `sink=None` (the default; every pre-existing call site that does not
# thread one through) costs one `perf_counter()` pair and nothing else, per
# this chunk's "cheap and unconditional-safe" constraint. `row_label` is
# `"<round>"` for a phase that runs once per invocation rather than once per
# publish row (the end-of-run gates in `main()`).
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _time_phase(
    sink: "Optional[List[tuple[str, str, float, float]]]",
    row_label: str,
    phase_label: str,
):
    start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        yield
    finally:
        if sink is not None:
            sink.append((
                row_label,
                phase_label,
                time.perf_counter() - start,
                time.process_time() - cpu_start,
            ))


def _print_round_timing_summary(
    timings: "List[tuple[str, str, float, float]]",
    wall_start: float,
    *,
    out: IO[str] = sys.stdout,
) -> None:
    """End-of-round summary (§ C1 AC2) — printed on the round's existing
    stdout channel, never a separate file/channel. Reports an explicit
    unattributed remainder (wall time minus the sum of the recorded spans)
    rather than letting spans that do not add up pass silently — per this
    chunk's brief, a breakdown that quietly loses time is worse than no
    breakdown at all, because it will be believed. Line shape (`  [timing]
    ...`) deliberately avoids `NEW:`/`UPDATE:`/`DELETE:`/`REMOVE:`/`RENAME:`/
    `  --- ... ---`/`Target:` — the tokens `percolate-round.py`'s
    `_extract_change_lines`/`_split_stdout_by_row_dest`/
    `_build_commit_pathspec` parse out of this same stream (verified by
    reading those functions, not by inspection alone).

    EVERY SPAN CARRIES BOTH UNITS, and they answer different questions.
    DR-344 gates on process time; wall clock on this box measures peer load
    (50-70 concurrent sessions is the design condition), so a leg convicted on
    wall clock is a leg convicted of somebody else's work. Wall clock bounds
    process time from above and never from below -- use it to EXCLUDE a leg,
    never to convict one. Emitting only wall clock is what let a 417s round be
    sized against numbers that could not gate anything
    (§ docs/plans/2026-08-23-a-percolate-round-costs-417s-for-25s-of-work.md).

    `cpu` IS THIS DRIVER PROCESS'S OWN CPU AND EXCLUDES SUBPROCESS CPU
    ENTIRELY. `time.process_time()` does not count children, and
    `os.times().children_*` is always 0.0 on Windows, so there is no cheap
    in-process way to fold them in (§ coordinator_core/benchmarks/
    process_time.py, which uses a Windows job object precisely because of
    this). A leg that mostly SPAWNS therefore reports a small `cpu` and a
    large `wall` -- that gap is the spawn-amplification signal, not a
    measurement error, and it is read that way. For a whole-tree figure that
    does include children, run the round itself under
    `batched_process_time_ms`.
    """
    print("  [timing] per-phase elapsed:", file=out)
    for row_label, phase_label, elapsed, cpu in timings:
        print(
            f"  [timing]   {row_label}: {phase_label}: "
            f"{elapsed:.3f}s wall / {cpu:.3f}s cpu (driver only, excludes subprocesses)",
            file=out,
        )
    attributed = sum(elapsed for _, _, elapsed, _ in timings)
    attributed_cpu = sum(cpu for _, _, _, cpu in timings)
    wall_elapsed = time.perf_counter() - wall_start
    unattributed = wall_elapsed - attributed
    print(
        f"  [timing] round wall time: {wall_elapsed:.3f}s; "
        f"attributed: {attributed:.3f}s; unattributed: {unattributed:.3f}s",
        file=out,
    )
    print(
        f"  [timing] round driver cpu: {time.process_time():.3f}s; "
        f"attributed to phases: {attributed_cpu:.3f}s "
        "(subprocess cpu is in neither -- see this function's docstring)",
        file=out,
    )


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
            if text.startswith("\r\n", consumed_end):
                consumed_end += 2
            elif consumed_end < len(text) and text[consumed_end] == "\n":
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


def _engine_reference_suffix(module_path: Path) -> str:
    """The one field a contract refusal is missing when an OVERRIDE won the
    seam: which module the reader should diff the offending one against.

    Empty when `module_path` IS the engine module -- naming the same path
    twice is noise, and the register rule is one fact once. `check_publish_
    sync_contract` is provenance-blind by design (§ `_resolve_publish_sync_
    module_path`); this suffix does not reintroduce provenance into the
    CHECK, it only tells the reader where the interface it failed is
    declared. Asked for by doe-claude-em 2026-08-26, after an AC15 refusal
    whose kwarg name and rung made the diagnosis fast and whose missing
    reference path made the fix slower than it needed to be.
    """
    if module_path == _ENGINE_PUBLISH_SYNC_PATH:
        return ""
    return f" Expected (engine): {_ENGINE_PUBLISH_SYNC_PATH}."


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
    modes_in_run: Optional[frozenset[str]] = None,
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

    `modes_in_run` (AMENDED 2026-08-10) narrows WHICH descriptors are
    checked to the wire names this run's rows actually dispatch — see the
    loop's own comment for why the table-wide form was an over-reach that
    took a peer repo's publish down over a mode it never uses. `None` (the
    default) preserves the original check-every-mode behaviour for callers
    that have no row set to hand in. It never weakens a check that DOES
    run: a mode present in the run is validated exactly as before, all four
    parts.

    Raises `PublishSyncContractError` naming: (1) `module_path`, (2) the
    missing symbol/parameter, (3) `rung_label` (from C1's
    `coordinator_percolate_runtime_root_explained()`, threaded through by the
    caller) — the three facts whose absence made the original incident's raw
    `TypeError` unreadable.
    """
    _bootstrap_engine()
    for descriptor in PUBLISH_MODES:
        # Keyed on "has an entry point", not `is_mirror_like` (AC7):
        # `repo-cut` is NOT mirror-like but DOES have its own entry point
        # (`sync_repo_cut`) that must be bind-checked here just like
        # `sync_mirror`/`sync_flat_mirror` — an `is_mirror_like`-keyed guard
        # would leave it permanently unchecked, the exact fail-open AC7
        # exists to close. `manifest` (`entry_point=None`) is still skipped,
        # unchanged.
        if descriptor.entry_point is None:
            continue
        # AMENDED 2026-08-10 — narrow the gate from "every mode in the table"
        # to "every mode THIS RUN's rows actually dispatch". AC7's concern was
        # that an `is_mirror_like`-keyed guard leaves `repo-cut` permanently
        # unchecked; a run-scoped guard still checks it in full whenever a
        # `repo-cut` row is present, so AC7's intent survives intact while its
        # over-reach does not. That over-reach was live: DoE-claude's percolate
        # root carries its own `setup/publish_sync.py` override (§
        # `_resolve_publish_sync_module_path`) predating `sync_repo_cut`, and
        # the table-wide loop refused all five of their mirror rows over an
        # entry point none of those rows would ever call — a total outage of a
        # peer's publish caused by a mode they do not use. `modes_in_run=None`
        # keeps the original check-everything behaviour for callers (and
        # tests) that do not know the run's rows.
        if modes_in_run is not None and descriptor.wire_name not in modes_in_run:
            continue
        symbol = descriptor.entry_point
        # Per-descriptor bind contract (AC7): each entry point is bound
        # against ITS OWN declared `bind_kwargs`, never a dict shared across
        # every entry point — `sync_mirror` and `sync_flat_mirror` diverge on
        # `renamed_dir_names` (state/audits/2026-08-05-first-full-payload-
        # identity-findings.md Group E), and a global bind would abort every
        # publish run the instant one mode's entry point can't bind against it.
        mirror_kwargs = descriptor.bind_kwargs

        fn = getattr(publish_sync_module, symbol, None)
        if fn is None:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"does not define {symbol!r} — dispatch_mirror_like cannot call it. "
                "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
                + _engine_reference_suffix(module_path)
            )

        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError) as exc:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"defines {symbol!r} but its signature could not be inspected: {exc}. "
                "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
                + _engine_reference_suffix(module_path)
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
                + _engine_reference_suffix(module_path)
            )

        try:
            sig.bind_partial(**mirror_kwargs)
        except TypeError as exc:
            raise PublishSyncContractError(
                f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
                f"defines {symbol!r} but its signature does not accept the mirror-dispatch "
                f"keyword arguments {sorted(mirror_kwargs)}: {exc}. Refusing to dispatch "
                "any mirror/flat-mirror target (AC15 fail-closed)."
                + _engine_reference_suffix(module_path)
            ) from exc

    load_ignore_fn = getattr(publish_sync_module, "load_ignore", None)
    if load_ignore_fn is None:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            "does not define 'load_ignore' — dispatch_mirror_like cannot call it. "
            "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
            + _engine_reference_suffix(module_path)
        )

    try:
        load_ignore_sig = inspect.signature(load_ignore_fn)
    except (TypeError, ValueError) as exc:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            f"defines 'load_ignore' but its signature could not be inspected: {exc}. "
            "Refusing to dispatch any mirror/flat-mirror target (AC15 fail-closed)."
            + _engine_reference_suffix(module_path)
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
            + _engine_reference_suffix(module_path)
        )

    try:
        load_ignore_sig.bind_partial(None)
    except TypeError as exc:
        raise PublishSyncContractError(
            f"[publish.py] FATAL: {module_path} (resolved via rung {rung_label!r}) "
            "defines 'load_ignore' but its signature does not accept a single "
            f"path-or-None argument: {exc}. Refusing to dispatch any mirror/flat-mirror "
            "target (AC15 fail-closed)."
            + _engine_reference_suffix(module_path)
        ) from exc


class MirrorDispatchModeError(RuntimeError):
    """Raised by `dispatch_mirror_like` when `target.mode` has no
    entry point on `PUBLISH_MODES` — either the mode is unknown to the table,
    or its descriptor declares `entry_point=None` (a non-mirror-like mode
    routed in here by mistake). Closes a prior unconditional `else:
    sync_flat_mirror(...)` fail-open: any mode reaching this function that
    was not literally `"mirror"` used to be silently flat-mirrored instead of
    erroring. `process_target`'s outer gate (site 1) keys on `target.mode in
    mirror_like_wire_names()` (an `is_mirror_like`-derived set) — a DIFFERENT
    predicate from this function's own `entry_point`-keyed guard below. The
    two are not redundant: a descriptor with `is_mirror_like=True` but
    `entry_point=None` (e.g. a placeholder/scaffolded mode) passes the outer
    gate and reaches here, where THIS raise is the only thing that catches
    it. Editing `mirror_like_wire_names()` alone does not change what this
    function accepts or rejects."""


def dispatch_mirror_like(
    publish_sync_module,
    target: ResolvedTarget,
    effective_source_dir: Path,
    totals: RunTotals,
    *,
    dry_run: bool,
    renamed_dir_names: "frozenset[str] | None" = None,
    out: IO[str] = sys.stdout,
    changed_sink: "Optional[set[str]]" = None,
    sweep_top_level_orphans: bool = False,
    renamed_file_names: "frozenset[str] | None" = None,
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
    2026-08-05-first-full-payload-identity-findings.md Group E).

    `changed_sink` (optional, § docs/plans/2026-08-16-percolate-round-
    timing-and-changed-only.md chunk C4): when supplied, it is passed to
    `sync_fn` as its `changed_paths` param and the sync engine populates it
    directly from each real `_needs_copy` copy decision, in the same
    `dst_dir`-relative posix id shape `dispatch_percolate_post_rsync`'s
    `visited_files`/`changed_files` already use. `REMOVE:` deletions are
    excluded there — a deletion is not new content for the entrypoint gate's
    closure walk to re-scan.

    This signal is NOT derived from `sync_fn`'s printed output. It was, and a
    scrape cannot express "I do not know": a format change silently yields an
    empty set, and empty means "skip the sweep" to the consumer, so the failure
    landed on the narrow side and shipped an unswept entrypoint. The
    undeterminable case belongs to the caller, which passes `None` and gets a
    full sweep. `None` here (the default, every pre-existing call site) is a
    no-op. `sync_fn`'s stdout is untouched either way.

    `sweep_top_level_orphans` (default False, forwarded to `sync_mirror` ONLY --
    § `PublishModeDescriptor.accepts_sweep_top_level_orphans`; `sync_flat_mirror`
    has always swept its top-level files and takes no flag) authorizes deleting
    destination top-level FILES the source no longer has. The caller decides,
    and must decide from the row's REAL `dest_dir`, never from the `sync_target`
    this function receives: `process_target` rewrites that to the staging tree
    (`sync_target = replace(target, dest_dir=staging_dir)`), and a staging tree's
    path shape says nothing about whether the row lands at a mirror repo's root
    or in a subdirectory the row owns outright. Deriving it here would read the
    staging path and get the answer wrong in the direction that deletes."""
    _bootstrap_engine()
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

    mode_descriptor = descriptor_for(target.mode)
    if mode_descriptor is None or not mode_descriptor.entry_point:
        raise MirrorDispatchModeError(
            f"[publish.py] FATAL: mode {target.mode!r} has no dispatch_mirror_like "
            "entry point on PUBLISH_MODES — refusing to silently substitute "
            "sync_flat_mirror or any other mirror-like sync engine."
        )

    sync_fn = getattr(publish_sync_module, mode_descriptor.entry_point)
    if mode_descriptor.accepts_renamed_dir_names:
        mirror_kwargs = {**mirror_kwargs, "renamed_dir_names": renamed_dir_names}
    if getattr(mode_descriptor, "accepts_sweep_top_level_orphans", False):
        mirror_kwargs = {
            **mirror_kwargs,
            "sweep_top_level_orphans": sweep_top_level_orphans,
            "renamed_file_names": renamed_file_names,
        }
    # The changed-set comes from the sync engine's own copy decisions, never
    # from re-parsing what it printed. A scrape degrades to an EMPTY set when
    # the output format moves, and empty reads downstream as "nothing changed,
    # skip the sweep" — failing narrow, which ships an unswept entrypoint. The
    # undeterminable case must reach the consumer as None so it falls back to a
    # full sweep: failing wide costs minutes, failing narrow costs correctness.
    if changed_sink is None:
        synced, removed = sync_fn(
            effective_source_dir, target.dest_dir, ignore_matcher, dry_run, **mirror_kwargs
        )
    else:
        synced, removed = sync_fn(
            effective_source_dir,
            target.dest_dir,
            ignore_matcher,
            dry_run,
            changed_paths=changed_sink,
            **mirror_kwargs,
        )

    totals.synced += synced
    totals.deleted += removed
    print("", file=out)
    print(f"  Synced: {synced} file(s), Removed: {removed} file(s)", file=out)


# ---------------------------------------------------------------------------
# Last-sync marker — port of setup/publish.sh (Phase 5).
# ---------------------------------------------------------------------------
def _is_git_repo(path: Path) -> bool:
    _bootstrap_engine()
    if (path / ".git").is_dir():
        return True
    return _resolve_git_dir(cwd=str(path)) is not None


def _source_sha_suffix() -> str:
    """The mirror-currency stamp appended to every percolate commit subject.

    WHY THIS EXISTS. A percolate commit subject named the paths it carried
    and the rows that produced them, but never the SOURCE commit those bytes
    were cut from — so neither party to the publish seam could tell whether a
    given mirror was current. A consumer executing the mirror could only
    answer "does my fix live here?" by grepping engine source for the fix's
    own text (project-rag-ue-addon-em, 2026-08-31: a fix committed here at
    `40abe011d` stayed live as a crash for a mirror consumer, and the only
    available currency check was a hand-rolled grep for `if parsed.tzinfo is
    None`). With the source sha in the subject, `git -C <mirror> log -1`
    answers it, and `git -C <source> merge-base --is-ancestor <fix> <stamp>`
    answers it exactly.

    Degrades to `""` rather than raising or blocking a publish: `head_sha`
    returns `None` on an unborn/detached-nothing HEAD, and a commit subject
    without the stamp is strictly what this function's absence produced.
    Zero-spawn by construction (`head_sha` reads `HEAD`/`packed-refs`
    directly) — this runs once per destination repo on the publish hot path.

    NOT what `_commit_published_dests` uses (§ `_pinned_source_sha_suffix`
    below): this reads `HEAD` fresh at call time, which is exactly the race
    `_round_pin_source_sha` exists to close (a peer commit landing mid-run
    between round-start pinning and this end-of-run commit would stamp a
    SHA the round never actually published from). Kept as the shared
    formatter shape the test suite pins identity against
    (`test_round_leg_stamps_the_same_shape`) and as the CLI-standalone
    fallback for a caller with no `round_pinned_shas` in hand.
    """
    _bootstrap_engine()
    from coordinator_core.git.git_state import head_sha  # noqa: PLC0415

    sha = head_sha(_REPO_ROOT)
    return f" [source {sha[:12]}]" if sha else ""


def _pinned_source_sha_suffix(round_pinned_shas: "dict[str, str]") -> str:
    """The mirror-currency stamp `_commit_published_dests` actually uses:
    the round's PINNED source sha (`_round_pin_source_sha`), never a fresh
    `HEAD` read.

    `_source_sha_suffix()` above reads `HEAD` at call time, which is the
    exact defect `_round_pin_source_sha` was written to close — a row
    processed later in a multi-target run could see a peer's commit land
    mid-run (docs/plans/2026-08-04-publish-from-a-committed-ref.md: four
    distinct SHAs observed across one round). `_commit_published_dests`
    runs at the very END of the run, after every row, so it is the site
    furthest from round-start and most exposed to that drift — stamping it
    with `_round_pin_source_sha`'s cached value keeps the subject naming
    the SAME sha the run actually published bytes from.

    Degrades to `""` on the identical failure modes `_source_sha_suffix`
    degrades on (`GitMaterializeError` — not inside a git work tree, or
    `HEAD` unresolvable) — a commit subject without the stamp, never a
    blocked publish.
    """
    try:
        sha = _round_pin_source_sha(_REPO_ROOT, round_pinned_shas, late=True)
    except GitMaterializeError:
        return ""
    return f" [source {sha[:12]}]" if sha else ""


def _git_head(path: Path) -> str:
    """Native (non-spawning) resolution of `git -C <path> rev-parse HEAD` —
    replaces a prior `subprocess.run` that made this a per-item spawn at
    every call site iterating over rows/repos
    (`docs/plans/2026-08-19-burn-down-the-amplification-hitlist.md` C5).
    Unlike `_argv_parity_pairing_origin`/`_git_ls_tree_entries_files` (which
    batch several entries into ONE spawn against a SHARED `-C <root>`), this
    function's callers each pass a DIFFERENT repo root per call (one row's
    `target.dest_dir` per invocation), so there is no shared `git` argv to
    fold multiple calls into — the only way to collapse the per-item spawn
    is to stop spawning at all. `coordinator_core.git.git_dir` exists for
    exactly this shape (its own docstring: "must stay cheap and
    Windows-safe... a cold subprocess per call is exactly the shape
    CLAUDE.md's Runtime conventions calls break-class") and already handles
    the worktree/submodule `.git`-is-a-file indirection this function must
    not silently mishandle.

    Resolves HEAD by reading `<gitdir>/HEAD` directly:
      - A detached HEAD (`<sha>`, no `ref: ` prefix) is returned as-is.
      - A symbolic HEAD (`ref: refs/heads/<branch>`) is resolved against
        the repo's COMMON dir (never the private per-worktree gitdir —
        refs live in the common dir) as a loose ref file first, falling
        back to a `packed-refs` scan if no loose ref file exists (an
        unpacked-but-referenced branch is the exceptional case, not the
        rule, so the loose-file read is tried first).

    Returns `""` on ANY resolution failure — missing `.git`, empty/
    unparseable `HEAD`, a detached-HEAD line that isn't a validly-shaped
    sha (review finding amp-s1 #6: a corrupt `HEAD` file is neither a
    `ref:` pointer nor a real object id, and `git rev-parse HEAD` fails
    closed on it -- returning the garbage text verbatim would be a
    fail-open divergence from that replaced path even though no CURRENT
    caller depends on the value being sha-shaped), a `ref:` pointer with no
    loose file and no matching `packed-refs` entry, or any `OSError`
    reading these files — the exact same fail-closed shape the replaced
    `subprocess.run` path had for a non-zero/missing-git exit, never a
    raise.
    """
    _bootstrap_engine()
    try:
        gitdir = _native_resolve_git_dir(path)
        head_text = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not head_text:
        return ""
    if not head_text.startswith("ref:"):
        # Detached HEAD: only a validly-shaped sha (40-hex sha1 or 64-hex
        # sha256) is trusted verbatim -- anything else is a corrupt HEAD
        # file, failed closed rather than returned as if it were a sha.
        if re.fullmatch(r"[0-9a-fA-F]{40}", head_text) or re.fullmatch(r"[0-9a-fA-F]{64}", head_text):
            return head_text
        return ""

    ref = head_text[len("ref:"):].strip()
    if not ref:
        return ""

    try:
        common_dir = _native_resolve_git_common_dir(path)
    except OSError:
        return ""

    try:
        loose = (common_dir / ref).read_text(encoding="utf-8").strip()
        if loose:
            return loose
    except OSError:
        pass

    try:
        packed = (common_dir / "packed-refs").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in packed.splitlines():
        if not line or line[0] in "#^":
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1].strip() == ref:
            return parts[0].strip()
    return ""


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


@dataclass(frozen=True)
class _GitRevParseResult:
    """Full outcome of a `git rev-parse` invocation — `_git_rev_parse`'s
    `Optional[str]` collapses failure to a bare `None`, discarding exactly
    the `returncode`/`stderr` a caller needs to tell "definitely not a git
    work tree" (`returncode == 128` with `not a git repository` in
    `stderr`) apart from a transient failure (lock contention, a path that
    momentarily does not exist, `git` unavailable). `oserror` carries the
    `OSError` message when the subprocess could not even be spawned."""

    stdout: Optional[str]
    returncode: Optional[int]
    stderr: str
    oserror: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.stdout is not None

    @property
    def not_a_work_tree(self) -> bool:
        """True only for the one failure shape that actually establishes
        "not inside a git work tree": `rev-parse --show-toplevel` (or any
        rev-parse call) exiting 128 with git's own `not a git repository`
        text. Every other failure — lock contention, OSError, any other
        non-zero exit — is a transient/unknown failure, not a structural
        claim about the path."""
        return self.returncode == 128 and "not a git repository" in self.stderr.lower()

    def describe_failure(self) -> str:
        """One line stating what actually happened, for callers that must
        report failure without asserting a repo-shape defect they have not
        established."""
        if self.oserror is not None:
            return f"git could not be run: {self.oserror}"
        return f"git rev-parse exited {self.returncode}: {self.stderr.strip() or '<no stderr>'}"


def _git_rev_parse_detailed(path: Path, *args: str) -> _GitRevParseResult:
    """Runs `git -C <path> rev-parse <args>` and returns the full outcome
    (stdout, returncode, stderr) rather than collapsing failure to `None`
    — the detail `_git_rev_parse` discards. Never raises; an `OSError`
    (e.g. `git` not on `PATH`) is captured into `.oserror` instead."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return _GitRevParseResult(stdout=None, returncode=None, stderr="", oserror=str(exc))
    if result.returncode != 0:
        return _GitRevParseResult(stdout=None, returncode=result.returncode, stderr=result.stderr)
    return _GitRevParseResult(stdout=result.stdout.strip(), returncode=0, stderr=result.stderr)


def _git_capture(path: Path, *args: str) -> Optional[str]:
    """Runs `git -C <path> <args>` and returns stripped stdout, or `None` on
    any non-zero exit or `OSError` — the general-command sibling of
    `_git_rev_parse`, which hard-codes its subcommand. `None` is "the call
    failed", never "the call returned nothing": an empty result is `""`."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_rev_parse(path: Path, *args: str) -> Optional[str]:
    """Runs `git -C <path> rev-parse <args>` and returns stripped stdout, or
    `None` on any non-zero exit or `OSError` (e.g. `git` not on `PATH`) —
    never raises, so callers decide how to fail. Callers that need to tell
    a transient failure apart from a genuine non-work-tree should use
    `_git_rev_parse_detailed` instead; this wrapper exists for callers that
    only ever wanted the happy-path string (§ call sites in `run_pre_sync_
    gates` and `_git_materialize_ref`'s provenance print, which already
    treat `None` as `'unknown'`/`''` rather than raising)."""
    return _git_rev_parse_detailed(path, *args).stdout


_MATERIALIZED_REF_CACHE: "dict[tuple[str, str], Path]" = {}
_REQUIRED_PATHSPEC_CACHE: "dict[tuple[str, str], tuple[str, ...]]" = {}
_TRACKED_PATHS_AT_SHA_CACHE: "dict[tuple[str, str], set]" = {}


def _tracked_paths_at_sha(toplevel: Path, sha: str) -> "set":
    """Every path `git` tracks at `sha` under `toplevel`, toplevel-relative
    and POSIX-separated — ONE `git ls-tree` spawn per (toplevel, sha),
    cached for the process lifetime (§ `_required_pathspec_for_toplevel`:
    this repo counts process spawns, not wall clock, so this must never be
    called once per contributing root / inject src).

    Used to gate pathspec coverage against the tree actually being
    archived (Review: code-reviewer — pathspec coverage previously gated
    on `.is_dir()`/`.exists()` against the LIVE working tree, not `sha`;
    a root/src tracked at `sha` but absent from the working tree at
    compute time was silently dropped from the pathspec with no error).
    Empty set (not a raise) on a failed `git ls-tree` — callers fall back
    to filesystem-only gating exactly as before this fix, never worse."""
    key = (str(toplevel), sha)
    cached = _TRACKED_PATHS_AT_SHA_CACHE.get(key)
    if cached is not None:
        return cached
    result = subprocess.run(
        ["git", "-C", str(toplevel), "ls-tree", "-r", "--name-only", sha],
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    paths: "set" = set(result.stdout.splitlines()) if result.returncode == 0 else set()
    _TRACKED_PATHS_AT_SHA_CACHE[key] = paths
    return paths


def _path_tracked_at_sha(path: Path, toplevel: Path, tracked: "set") -> bool:
    """`True` when `path` (file or directory) is tracked at the sha
    `tracked` was computed for — an exact match against `tracked` for a
    file, or a directory whose contents any tracked path is nested under.
    `False` (never raises) when `path` doesn't resolve under `toplevel` at
    all, matching `_relative_pathspec_entry`'s own toplevel-relative
    contract."""
    try:
        rel = path.resolve().relative_to(toplevel.resolve()).as_posix()
    except ValueError:
        return False
    if rel in tracked:
        return True
    prefix = rel + "/"
    return any(p.startswith(prefix) for p in tracked)


def _relative_pathspec_entry(path: Path, toplevel: Path) -> Optional[str]:
    """`path` expressed as a `:(literal)`-guarded, toplevel-relative,
    POSIX-separated `git archive` pathspec entry, or `None` when `path`
    does not resolve under `toplevel` at all — a genuinely different git
    toplevel, not this pathspec's business (§ C5 dispatch brief: "an
    inject src in a different git toplevel gets its own cache entry as it
    does today")."""
    try:
        rel = path.resolve().relative_to(toplevel.resolve())
    except ValueError:
        return None
    rel_posix = rel.as_posix()
    if rel_posix in ("", "."):
        return ":(literal)."
    return f":(literal){rel_posix}"


def _all_inject_srcs_resolved(setup_dir: Path, percolate_root: Path) -> "List[str]":
    """Every store-declared inject `src`, with `<coordinator-content-root>`/
    `<claude-klabauter-content-root>` placeholders resolved exactly as
    `_resolve_inject_src_placeholders` resolves them for a live dispatch —
    read directly off `percolate-store.yaml`'s own `targets: */inject: []`
    shape, not through `engine_claude_klabauter.resolve_target`'s inheritance pass:
    every declared inject entry today (both of them — the vendored
    `cockpit-contract/LICENSE` and the `.github` CI-harness tree) is a leaf
    list with no `extends`-driven rewrite of `src` to replay. If that stops
    being true, this must route through the engine instead of drifting
    from it.
    """
    import yaml

    store_path = locate_percolate_store(setup_dir)
    if not store_path.is_file():
        return []
    with store_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    targets_section = raw.get("targets") if isinstance(raw, dict) else None
    if not isinstance(targets_section, dict):
        return []
    content_root = str(percolate_root / "coordinator")
    claude_klabauter_content_root = str(_REPO_ROOT)
    srcs: "List[str]" = []
    for section in targets_section.values():
        if not isinstance(section, dict):
            continue
        for entry in section.get("inject") or []:
            if not isinstance(entry, dict):
                continue
            src = entry.get("src", "")
            if not src:
                continue
            if _COORDINATOR_CONTENT_ROOT_PLACEHOLDER in src:
                src = str(Path(src.replace(_COORDINATOR_CONTENT_ROOT_PLACEHOLDER, content_root)))
            if _CLAUDE_KLABAUTER_CONTENT_ROOT_PLACEHOLDER in src:
                src = str(Path(src.replace(_CLAUDE_KLABAUTER_CONTENT_ROOT_PLACEHOLDER, claude_klabauter_content_root)))
            srcs.append(src)
    return srcs


def _required_pathspec_for_toplevel(
    toplevel: Path, sha: Optional[str] = None
) -> "tuple[str, ...]":
    """The `git archive` pathspec `_extract_git_archive` scopes its
    extraction to, for `toplevel` — the UNION of (a) every contributing
    root `setup/publish-targets.portable` declares, REGARDLESS of this
    run's `--target` filter (the shared `_MATERIALIZED_REF_CACHE` shadow
    this toplevel+sha extracts to may still be read by a LATER row
    processed in the same run whose own root this pathspec must already
    cover — there is no second extraction to add it late), (b) every
    resolved store-declared inject `src` (§ `_all_inject_srcs_resolved`)
    that resolves under this toplevel — the shared-shadow hazard C5's
    dispatch brief names explicitly: a naive contributing-roots-only
    pathspec would silently drop inject's files from the shadow the SAME
    cache entry serves — and (c) `.percolate-ignore`, named EXPLICITLY per
    contributing root that actually carries one (never a blanket toplevel
    entry: `git archive` raises `fatal: pathspec ... did not match any
    files` for ANY single unmatched pathspec entry, even mixed with
    entries that do match, measured directly against this repo's own
    HEAD — so an ignore-file entry is only added when
    `(root / ".percolate-ignore").is_file()` is true, mirroring the
    `effective_source_dir / ".percolate-ignore"` existence check
    `dispatch_mirror_like` already applies).

    Cached per toplevel for the process lifetime — the same lifetime
    `_MATERIALIZED_REF_CACHE` itself uses — computed once, on the first
    (cache-MISS) extraction for that toplevel.

    A `toplevel` other than THIS repo's own (`_REPO_ROOT`) is not scoped at
    all — an empty tuple, meaning `_extract_git_archive` falls through to
    its pre-C5 full-tree behavior unchanged. Every contributing root and
    every store-declared inject `src` this repo's own configuration names
    resolves under `_REPO_ROOT` (§ `_git_materialize_ref`'s own docstring:
    "every contributing root... is a subdirectory of this repo's own
    single git toplevel"), so a DIFFERENT toplevel — a sibling checkout, or
    a throwaway repo a lower-level test builds directly to exercise
    `_extract_git_archive` in isolation (e.g.
    `test_publish_git_archive_eol_regimes.py`) — has no declared coverage
    to compute here in the first place; scoping it is "not this pathspec's
    business" (dispatch brief).

    Raises `GitMaterializeError` (fail-loud, never a silent full-tree
    fallback) when `toplevel` IS `_REPO_ROOT` and the computed pathspec is
    still empty: that is a real coverage bug, not an out-of-scope
    toplevel — nothing this run's declared configuration contributes
    resolves under this repo's own toplevel at all, which means archiving
    it here would either produce a useless empty shadow or (per the
    measured `git archive` behavior above) hard-fail inside
    `_extract_git_archive` anyway with a less legible error.

    `sha` (Review: code-reviewer — coverage must gate on the tree actually
    being archived, not the live working tree at compute time; a root or
    inject src tracked at `sha` but deleted/not-yet-materialized on disk
    was previously dropped from the pathspec with no error) defaults to
    this toplevel's current `HEAD` when omitted, so a root/src absent from
    the working tree but still tracked at `sha` is included regardless.
    Coverage against `sha` costs exactly ONE extra `git ls-tree` spawn per
    (toplevel, sha) — never one per contributing root or inject src (§
    `_tracked_paths_at_sha`).
    """
    _bootstrap_engine()
    resolved_sha = sha if sha is not None else (_git_rev_parse(toplevel, "HEAD") or "HEAD")
    key = (str(toplevel), resolved_sha)
    cached = _REQUIRED_PATHSPEC_CACHE.get(key)
    if cached is not None:
        return cached

    if toplevel.resolve() != _REPO_ROOT.resolve():
        _REQUIRED_PATHSPEC_CACHE[key] = ()
        return ()

    percolate_root, _rung = _resolve_percolate_root_and_rung()
    setup_dir = percolate_root / "setup"

    tracked = _tracked_paths_at_sha(toplevel, resolved_sha)
    entries: "set[str]" = set()

    try:
        # `err=io.StringIO()` (Review: code-reviewer): `main()`'s own
        # `load_targets` call already prints shadow-collision diagnostics
        # to `sys.stderr` once per run; this pathspec-scoping call re-runs
        # the same 4-tier resolution and would otherwise print the exact
        # same diagnostics a second time on the first archive extraction.
        rows = load_targets(setup_dir, target_filter="", err=io.StringIO())
    except TargetsError:
        rows = []
    for row in rows:
        try:
            row_target = parse_target_row(row)
        except TargetsError:
            continue
        for root in _contributing_roots(row_target):
            root_tracked = _path_tracked_at_sha(root, toplevel, tracked)
            if root.is_dir():
                root_toplevel = _git_rev_parse(root, "--show-toplevel")
                if root_toplevel is None or Path(root_toplevel).resolve() != toplevel.resolve():
                    continue
            elif not root_tracked:
                continue
            root_entry = _relative_pathspec_entry(root, toplevel)
            if root_entry is None:
                continue
            entries.add(root_entry)
            ignore_file = root / ".percolate-ignore"
            if ignore_file.is_file():
                ignore_entry = _relative_pathspec_entry(ignore_file, toplevel)
                if ignore_entry is not None:
                    entries.add(ignore_entry)

    for src in _all_inject_srcs_resolved(setup_dir, percolate_root):
        src_path = Path(src)
        if not src_path.is_absolute():
            continue
        src_tracked = _path_tracked_at_sha(src_path, toplevel, tracked)
        if src_path.exists():
            src_toplevel = _git_rev_parse(
                src_path if src_path.is_dir() else src_path.parent, "--show-toplevel"
            )
            if src_toplevel is None or Path(src_toplevel).resolve() != toplevel.resolve():
                continue
        elif not src_tracked:
            continue
        src_entry = _relative_pathspec_entry(src_path, toplevel)
        if src_entry is not None:
            entries.add(src_entry)

    result = tuple(sorted(entries))
    if not result:
        raise GitMaterializeError(
            f"no contributing root or resolved inject src resolves under git toplevel "
            f"{toplevel} — refusing to archive it with an empty pathspec rather than "
            "silently falling back to a full-tree extraction"
        )
    _REQUIRED_PATHSPEC_CACHE[key] = result
    return result


def _extract_git_archive(toplevel: Path, sha: str) -> Path:
    """`git archive <sha>` of `toplevel`, scoped to the pathspec
    `_required_pathspec_for_toplevel` computes — the union of every
    contributing root `setup/publish-targets.portable` names, every
    resolved inject `src` under this toplevel, and each covered root's own
    `.percolate-ignore` (named explicitly; § `_required_pathspec_for_toplevel`
    docstring) — to a temp file, unpacked with `tarfile.extractall(filter=...)`.

    Pathspec-scoped is now the whole point (docs/plans/2026-08-21-the-
    payload-proves-itself-before-it-overwrites-the-engine.md C5): full-tree
    extraction pulled 31,213 files / 413MB to publish 5,055 files / 86.6MB,
    ~17,667 of the difference from `state/` alone, never published by any
    row. `.percolate-ignore` dropping out of a single-source shadow root and
    silently widening the publish set — the failure class the OLD
    (unconditionally-full-tree) version of this docstring refused scoping
    over — is answered by naming every covered root's ignore file
    explicitly in the pathspec rather than by refusing to scope at all;
    narrowing WHICH of the archived files a given row actually publishes
    remains `build_allowlisted_source`'s job, unchanged.

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

    `-c core.autocrlf=false -c core.eol=lf`: on a Windows host with the
    invoking repo's eol config in play, a bare `git archive` applies the
    `text=auto` smudge and materializes CRLF for a file whose blob is LF. The
    mirror's `core.autocrlf` is `false`, so nothing normalizes it back at the
    destination, and a round would write whole-file line-ending flips across
    every published text file. Invisible on macOS/Linux, silent on Windows.

    Both flags are load-bearing, each in a DIFFERENT `.gitattributes` regime —
    do not strip either as redundant:

    - Path with **no `text` attribute** (e.g. this repo's vendored
      `cockpit-contract/LICENSE`): conversion is driven by `core.autocrlf`
      alone, so `autocrlf=false` disables it and `eol=lf` is the no-op.
      Measured, 3021-byte LF blob: bare 3082/61 CRLF; `eol=lf` alone 3082/61;
      `autocrlf=false` alone 3021/0; both 3021/0.
    - Path with explicit **`text=auto`** (DoE-claude sets `* text=auto`
      repo-wide, covering `coordinator/dist/publish-repo-toplevel/`): the
      ATTRIBUTE drives conversion and the target ending comes from `core.eol`,
      which defaults to `native` = CRLF on Windows. There `autocrlf=false`
      changes nothing and `eol=lf` is the load-bearing flag. Measured by
      doe-claude-em, 12290-byte LF blob: bare 12514/224 CRLF; both 12290/0.

    Only the pair is correct across both regimes. A regression pin must cover
    one path of each kind — a pin over attribute-free paths alone stays green
    if `eol=lf` is later dropped.
    """
    pathspec = _required_pathspec_for_toplevel(toplevel, sha)
    shadow_dir = Path(tempfile.mkdtemp(prefix="claude-klabauter-publish-materialize-"))
    fd, archive_path_str = tempfile.mkstemp(prefix="claude-klabauter-publish-archive-", suffix=".tar")
    os.close(fd)
    archive_path = Path(archive_path_str)
    try:
        try:
            _git_archive_start = time.perf_counter()
            try:
                _archive_cmd = [
                    "git",
                    "-C",
                    str(toplevel),
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "archive",
                    "--format=tar",
                    "-o",
                    str(archive_path),
                    sha,
                ]
                if pathspec:
                    _archive_cmd += ["--", *pathspec]
                result = subprocess.run(
                    _archive_cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                print(
                    f"  [timing] _extract_git_archive: git archive: "
                    f"{time.perf_counter() - _git_archive_start:.3f}s ({toplevel}, {sha})",
                    file=sys.stdout,
                )
            if result.returncode != 0:
                raise GitMaterializeError(
                    f"git archive {sha!r} failed for {toplevel} (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
            _extractall_start = time.perf_counter()
            try:
                with tarfile.open(archive_path) as archive:
                    archive.extractall(path=shadow_dir, filter="tar")
            finally:
                print(
                    f"  [timing] _extract_git_archive: extractall: "
                    f"{time.perf_counter() - _extractall_start:.3f}s ({shadow_dir})",
                    file=sys.stdout,
                )
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


def _round_pin_source_sha(
    root: Path,
    pinned_shas: "dict[str, str]",
    *,
    out: IO[str] = sys.stdout,
    late: bool = False,
) -> str:
    """Resolves the committed HEAD sha for the git toplevel containing
    `root` ONCE per round and caches it in `pinned_shas` (keyed by toplevel
    path string) — the fix for a measured defect where `_git_materialize_ref`
    resolved `ref="HEAD"` freshly on every call, so a row processed later in
    a round could pick up a peer's commit that landed mid-round (four
    distinct SHAs observed across one round's `[timing]` log, docs/plans/
    2026-08-04-publish-from-a-committed-ref.md's own promise of "a publish
    round is a snapshot of one commit" broken in practice on a
    50-70-concurrent-session box). Every contributing root sharing one
    toplevel therefore reuses the SAME cached sha, not just the same
    `_git_materialize_ref` cache entry.

    Raises `GitMaterializeError` under the same two conditions
    `_git_materialize_ref` itself raises for (`root` not inside a git work
    tree, or `HEAD` unresolvable there) so callers can route the failure
    through their existing per-row skip handling — this function never
    silently falls back to an unpinned read.

    `late=True` marks a pin resolved during per-row processing rather than
    `main`'s round-start pre-pinning pass — a contributing root main's pass
    did not walk (e.g. `--target` admitted only a subset, or a row's
    `source_map` names a root no earlier row shared). Decision: pin it on
    first sight rather than silently resolving a fresh, unrecorded HEAD or
    hard-failing the round for a case the round-start pass simply never
    saw. The `late=True` print makes that late pin visible in the
    provenance log instead of reading identically to a round-start pin."""
    toplevel_result = _git_rev_parse_detailed(root, "--show-toplevel")
    if toplevel_result.stdout is None:
        if toplevel_result.not_a_work_tree:
            raise GitMaterializeError(f"{root} is not inside a git work tree — cannot pin a round source sha")
        raise GitMaterializeError(
            f"could not determine the git toplevel for {root} — cannot pin a round source sha "
            f"({toplevel_result.describe_failure()})"
        )
    toplevel = Path(toplevel_result.stdout)
    key = str(toplevel)
    cached = pinned_shas.get(key)
    if cached is not None:
        return cached

    sha_result = _git_rev_parse_detailed(toplevel, "HEAD")
    if sha_result.stdout is None:
        raise GitMaterializeError(
            f"could not resolve HEAD to a commit for {toplevel} — cannot pin a round source sha "
            f"({sha_result.describe_failure()})"
        )
    sha = sha_result.stdout
    pinned_shas[key] = sha
    label = "Round source (pinned late)" if late else "Round source pinned"
    print(f"  {label}: {toplevel} @ {sha}", file=out)
    return sha


def _scoped_engine_stamp_sha(root: Path, pinned_sha: str, *, out: IO[str] = sys.stdout) -> str:
    """The value actually written into the engine build stamp: the most
    recent commit AT OR BEFORE `pinned_sha` (the round's pinned content sha,
    `_round_pin_source_sha`'s return) that touches `_ENGINE_TOUCHING_PATHS`
    -- never `pinned_sha` itself.

    WHY: `pinned_sha` is round-pinned raw toplevel HEAD (docs/plans/
    2026-08-04-publish-from-a-committed-ref.md C1b) and moves on EVERY
    commit to the shared branch -- a doc, a `state/` artifact, any of
    50-70 concurrent sessions' unrelated work -- not only an engine-code
    commit. Writing it into the stamp verbatim (this function's predecessor)
    made `coordinator_core.warm.skew.compute_client_token` rotate on every
    publish round regardless of content, exactly the coarseness that
    function's own docstring claims is fixed ("changes when a publish ships
    new engine code, and at no other time") -- a promise the WRITER, not
    the reader, was breaking. Measured 2026-08-21: 55%/33% of warm
    generations exited `skew`/`superseded` at medians of ~7min/~2.5min
    against a 15min idle deadline, tracking the ~9min publish cadence
    (`docs/decisions/DR-335-publish-lag-is-surfaced-not-shortened.md`)
    almost exactly. Scoping to the last engine-touching ancestor makes the
    promise true: two rounds whose pins differ but share the same last
    engine-touching ancestor now write the IDENTICAL stamp, so the token
    does not rotate and a healthy warm server survives a round that ships
    it nothing new.

    SOUNDNESS -- never a false negative, i.e. never fails to rotate on a
    round that DID ship an engine change. `git log -1 <pinned_sha> --
    <paths>` walks `pinned_sha`'s own ancestry (never anything outside it)
    and returns the newest commit in that ancestry touching `paths` -- if
    engine code changed in any commit reachable from `pinned_sha`
    (`pinned_sha` itself included), that commit or a later one in the same
    ancestry is what this returns; it can therefore never return a sha
    OLDER than the true last engine change reachable from this round's
    pin. Same reasoning `publish_lag`'s own pathspec-scoped `git log`/
    `git rev-list` calls (`coordinator_core/warm/skew.py`) already rely on
    for merges -- git's ordinary history simplification finds the commit
    that actually introduced the difference. A revert is treated as an
    ordinary content-changing commit (it touches the paths), which is
    correct: the running server's source differs from a reverted state
    exactly as much as from any other edit, so eviction is still warranted.
    A first-ever publish has at least one commit touching `coordinator_core/`
    reachable from any HEAD -- this row IS that directory -- so the "no
    ancestor ever touched the paths" branch below should be unreachable in
    practice; it is handled defensively regardless, never asserted away.

    FALLBACK, never a silent no-stamp: any git failure (non-zero exit,
    `OSError`, or empty output because no ancestor touched the paths)
    returns `pinned_sha` UNSCOPED -- today's prior behaviour. That is
    always SAFE, never a false negative: it can only make the stamp rotate
    on a round that shipped no engine change (the defect this function
    exists to remove), never fail to rotate on one that did.

    LOGGING IS UNCONDITIONAL, deliberately, not gated on `scoped !=
    pinned_sha` (an earlier version of this function was gated that way).
    A gated print is silent in exactly the two cases that most need
    telling apart: `pinned_sha` itself is the last engine-touching commit
    (scoping legitimately returns it unchanged) and a git failure fell
    back to `pinned_sha` unscoped (this function's own safety net). Both
    write an IDENTICAL stamp and, under the gated version, an IDENTICAL
    (silent) log -- so a round whose scoped git call silently failed reads
    from the log exactly like a round that scoped correctly. Observed
    live 2026-08-21: the first round to carry this function's code had
    `pinned_sha` already engine-touching (`ddf8587d…`, a popup-guard
    commit under `coordinator_core/`), so `scoped == pinned_sha` and the
    prior gated print never fired -- there was no way, from that round's
    own log, to tell a legitimate match from a silent fallback. Printing
    every outcome, tagged with WHICH of the three paths produced it,
    closes that gap without adding a second read surface.
    """
    toplevel_result = _git_rev_parse_detailed(root, "--show-toplevel")
    if toplevel_result.stdout is None:
        print(
            f"  Engine build stamp: sha={pinned_sha} source=fallback-not-a-work-tree "
            f"({toplevel_result.describe_failure()})",
            file=out,
        )
        return pinned_sha
    toplevel = Path(toplevel_result.stdout)
    scoped = _git_capture(
        toplevel, "log", "-1", "--format=%H", pinned_sha, "--", *_ENGINE_TOUCHING_PATHS
    )
    if not scoped:
        print(
            f"  Engine build stamp: sha={pinned_sha} source=fallback-scoped-log-empty-or-failed",
            file=out,
        )
        return pinned_sha
    source = "scoped-match-pin" if scoped == pinned_sha else "scoped-earlier-than-pin"
    print(f"  Engine build stamp: sha={scoped} source={source} (round pin {pinned_sha})", file=out)
    return scoped


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
    multiple entries into one repo — a per-root extraction is one whole
    tracked-file population's worth of work, per row, per publish run
    (23,804 tracked files per `git ls-files | wc -l`, measured 2026-08-16;
    a point-in-time observation of a growing repo, not a constant — pack
    size not re-verified at this edit) — and would destroy the nesting
    relationship between the real roots, since two shadow trees that
    should be one tree become disjoint copies.

    Raises `GitMaterializeError` if `root` is genuinely not inside a git
    work tree, or if `ref` does not resolve to a commit there — never
    falls back to a live-tree copy. A transient git failure (lock
    contention, a momentarily-missing path, `git` unavailable) raises with
    the actual returncode/stderr instead of asserting either of those two
    structural claims it has not established (see incident: a concurrent-
    publish lock collision on `dist/mirror-native/` was misreported as
    "not inside a git work tree" for a path that was, in fact, tracked).
    """
    toplevel_result = _git_rev_parse_detailed(root, "--show-toplevel")
    if toplevel_result.stdout is None:
        if toplevel_result.not_a_work_tree:
            raise GitMaterializeError(f"{root} is not inside a git work tree — cannot materialize {ref!r}")
        raise GitMaterializeError(
            f"could not determine the git toplevel for {root} — cannot materialize {ref!r} "
            f"({toplevel_result.describe_failure()})"
        )
    toplevel = Path(toplevel_result.stdout)

    prefix = _git_rev_parse(root, "--show-prefix") or ""

    sha_result = _git_rev_parse_detailed(toplevel, ref)
    if sha_result.stdout is None:
        raise GitMaterializeError(
            f"could not resolve ref {ref!r} to a commit for {toplevel} ({sha_result.describe_failure()})"
        )
    sha = sha_result.stdout

    cache_key = (str(toplevel), sha)
    shadow_toplevel = _MATERIALIZED_REF_CACHE.get(cache_key)
    if shadow_toplevel is None:
        # Review: a single post-extraction line carries the same MISS signal as
        # the removed pre-extraction print, without reading as two separate events.
        _materialize_start = time.perf_counter()
        shadow_toplevel = _extract_git_archive(toplevel, sha)
        print(
            f"  [timing] _git_materialize_ref: cache MISS for {cache_key!r}: extracted in "
            f"{time.perf_counter() - _materialize_start:.3f}s",
            file=sys.stdout,
        )
        _MATERIALIZED_REF_CACHE[cache_key] = shadow_toplevel
    else:
        print(f"  [timing] _git_materialize_ref: cache HIT for {cache_key!r}", file=sys.stdout)

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


# ---------------------------------------------------------------------------
# --delta mode (task brief "Deliverable 2 — delta publishing"). A whole-ROW
# skip-work optimisation, never a skip-verification one (§ `build_arg_parser`
# --delta help): a row is skipped ONLY when this invocation can prove, right
# now, that nothing about it could have changed since its last recorded
# publish — the store+transform-code signature, the source contributing
# roots' committed HEAD, and the destination's committed HEAD all match a
# prior recorded record, AND (repo-mode rows only — § `delta_row_unchanged`
# condition 6) the destination working tree is currently clean. Mirror/
# flat-mirror rows are exempted from the clean-tree leg: C5/C6 of the swap
# plan deliberately never commit published bytes into a mirror, so its
# working tree is permanently dirty with the pipeline's own prior output
# and the clean-tree check can never discriminate signal there — it just
# always fails, making `--delta` unconditionally dead on mirror rows (see
# state/bug-backlog/2026-08-10-delta-is-unreachable-on-publish-mirrors-56a2531183a3.yaml).
# Any ambiguity (missing record, unresolvable git sha, dirty repo-mode
# destination, absent destination dir) means "do not skip" — every check
# below is written to fail closed toward the full-row path, never toward a
# skip. The end-of-run identity/install-doc/unscanned-published checks in
# `main()` are UNCONDITIONAL — they scan the full destination tree on every
# run regardless of which rows this invocation skipped.
# ---------------------------------------------------------------------------
def _git_is_clean(path: Path) -> Optional[bool]:
    """True iff `path` is a clean git working tree (`git status --porcelain`
    prints nothing — no staged/unstaged changes, no untracked files).
    `None` when `path` is not a git repo or the check could not be run —
    callers MUST treat `None` as "cannot verify", never as clean, since a
    dirty destination is exactly the "someone edited the published tree"
    drift case `--delta` must never let a skip paper over."""
    if not _is_git_repo(path):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() == ""


def _delta_state_path(setup_dir: Path, name: str) -> Path:
    """Per-row delta record, alongside the existing `<name>.lastsync`
    marker in `setup/percolate-state/` (§ `write_lastsync_marker`)."""
    return setup_dir / "percolate-state" / f"{name}.delta-state.json"


def _hash_bytes_of(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        h.update(b"<unreadable>")
    return h.hexdigest()


def _hash_py_tree(root: Path) -> str:
    """Order-stable sha256 over every `*.py` file's relative path + bytes
    under `root`. `root` not existing/not a directory hashes to a fixed
    sentinel rather than raising — a caller composing several of these
    into one signature (§ `compute_delta_invalidation_signature`) still
    gets a signature that changes if `root` starts/stops existing."""
    import hashlib

    h = hashlib.sha256()
    if not root.is_dir():
        h.update(b"<absent>")
        return h.hexdigest()
    for p in sorted(root.rglob("*.py")):
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()


def compute_delta_invalidation_signature(
    percolate_store_path: Path,
    engine_ctx: "PercolateEngineContext",
) -> str:
    """A single sha256 signature that changes whenever anything capable of
    changing published BYTES for a store-declared file changes: the
    percolate store itself, this driver's own copy/transform logic
    (`publish.py`, `coordinator/lib/percolate/`), and — the case the task
    brief calls out explicitly ("a transform fix had to reach files whose
    source never changed") — the engine repo's own
    `coordinator_core.percolate` transform package and
    `coordinator_core.ops` phase-dispatch package, resolved via
    `inspect.getfile` off an already-resolved engine callable rather than
    re-deriving the engine root. `engine_ctx.engine_claude_klabauter is None` (engine
    unavailable) folds in a sentinel that can never match a prior recorded
    signature — a delta skip decision must never trust a signature that
    could not actually verify engine-side transform code."""
    import hashlib

    h = hashlib.sha256()
    h.update(_hash_bytes_of(percolate_store_path).encode("ascii"))
    h.update(_hash_bytes_of(Path(__file__).resolve()).encode("ascii"))
    h.update(_hash_py_tree(_COORDINATOR_LIB / "percolate").encode("ascii"))
    if engine_ctx.engine_claude_klabauter is None:
        h.update(b"<engine-unavailable>")
    else:
        try:
            ops_pkg_dir = Path(inspect.getfile(engine_ctx.engine_claude_klabauter.run_percolate)).resolve().parent
            engine_root = ops_pkg_dir.parent  # .../coordinator_core
            h.update(_hash_py_tree(ops_pkg_dir).encode("ascii"))
            h.update(_hash_py_tree(engine_root / "percolate").encode("ascii"))
        except Exception:  # noqa: BLE001 - fail-safe: unresolvable engine layout must never verify
            h.update(b"<engine-signature-unresolvable>")
    return h.hexdigest()


def _delta_row_source_sha(
    target: "ResolvedTarget",
    round_pinned_shas: "dict[str, str]",
    *,
    out: IO[str] = sys.stdout,
) -> Optional[str]:
    """Combined committed-HEAD sha across every one of `target`'s
    contributing source roots (§ `_contributing_roots`), sorted for a
    stable signature. `None` (never skip) if ANY root is not inside a git
    work tree or its HEAD cannot be resolved.

    Reads through `round_pinned_shas` (§ `_round_pin_source_sha`,
    `late=True`) rather than a fresh `_git_rev_parse(root, "HEAD")` — the
    delta skip-check and post-publish record must agree with the sha this
    row actually materialized and published from, not with whatever HEAD a
    peer session's mid-round commit happens to have moved to by the time
    this function runs."""
    parts: List[str] = []
    for root in _contributing_roots(target):
        try:
            sha = _round_pin_source_sha(root, round_pinned_shas, out=out, late=True)
        except GitMaterializeError:
            return None
        parts.append(f"{root}:{sha}")
    return "|".join(sorted(parts))


def load_delta_record(setup_dir: Path, name: str) -> Optional[dict]:
    """The last-recorded delta record for `name`, or `None` if absent or
    unreadable/malformed — either case means "cannot verify, do not
    skip"."""
    import json

    path = _delta_state_path(setup_dir, name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_delta_record(
    setup_dir: Path, name: str, *, signature: str, source_sha: str, dest_head: str
) -> None:
    import json

    path = _delta_state_path(setup_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"signature": signature, "source_sha": source_sha, "dest_head": dest_head}),
        encoding="utf-8", newline="\n",
    )


def delta_row_unchanged(
    setup_dir: Path,
    target: "ResolvedTarget",
    signature: str,
    round_pinned_shas: "dict[str, str]",
) -> bool:
    """True iff `target` can be PROVEN unchanged since its last recorded
    `--delta` publish (§ module comment above `_git_is_clean` — every
    check here is written to fail closed toward "do not skip"):

      1. `target.dest_dir` exists on disk.
      2. A prior delta record exists for `target.name`.
      3. The record's `signature` matches `signature` (current store +
         transform-code signature — a mismatch means the store or the
         transform code changed, invalidating every file this row
         publishes regardless of source bytes).
      4. The record's `source_sha` matches `target`'s CURRENT contributing-
         roots committed HEAD (§ `_delta_row_source_sha`) — a mismatch, or
         an unresolvable sha, means the committed source moved.
      5. The record's `dest_head` matches the destination's CURRENT
         committed HEAD — a mismatch means the destination repo advanced
         (a new commit landed, possibly reverting/altering published
         content) since the recorded publish.
      6. NON-MIRROR ROWS ONLY: the destination working tree is clean RIGHT
         NOW (§ `_git_is_clean`) — catches uncommitted drift (a local edit,
         or a half-completed prior run) that HEAD equality alone cannot.

         Mirror/flat-mirror rows (`target.mode in mirror_like_wire_names()`)
         are exempted from this leg. The swap plan's C5/C6 deliberately
         never commit or push published bytes into a publish mirror, so a
         mirror destination's working tree carries the drift of every prior
         publish permanently and `_git_is_clean` can never return `True`
         there — condition 6 is unconditionally unsatisfiable on a mirror
         target, making `--delta` dead code on every mirror row regardless
         of whether the row actually changed (measured 2026-08-10: a
         `--delta` run against an unchanged mirror row re-synced 189 files
         instead of skipping; see
         state/bug-backlog/2026-08-10-delta-is-unreachable-on-publish-mirrors-56a2531183a3.yaml).
         The clean-tree guard exists to stop a publish clobbering a
         human's uncommitted work in a REPO-mode destination; in a publish
         mirror the "drift" it is tripping on is only the pipeline's own
         prior output, never a human's, so the guard protects nothing
         there while permanently disabling the optimization. Conditions
         3-5 (store+transform signature, source HEAD, destination HEAD)
         still do the real correctness work for mirror rows: the
         destination HEAD leg still catches a mirror repo that advanced
         out from under this run (e.g. a human/other-automation commit),
         and the signature/source legs still catch any store, transform-
         code, or source change. This does NOT relax anything for
         repo-mode destinations — condition 6 still applies there
         unchanged, protecting a human's uncommitted work exactly as
         before.
    """
    _bootstrap_engine()
    if not target.dest_dir.is_dir():
        return False
    record = load_delta_record(setup_dir, target.name)
    if record is None:
        return False
    if record.get("signature") != signature:
        return False
    source_sha = _delta_row_source_sha(target, round_pinned_shas)
    if source_sha is None or record.get("source_sha") != source_sha:
        return False
    if not _is_git_repo(target.dest_dir):
        return False
    dest_head = _git_head(target.dest_dir)
    if not dest_head or record.get("dest_head") != dest_head:
        return False
    if target.mode not in mirror_like_wire_names():
        if _git_is_clean(target.dest_dir) is not True:
            return False
    return True


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
    (marker_dir / f"{name}.lastsync").write_text(dest_head + "\n", encoding="utf-8", newline="\n")


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


def _dest_prefix_for(dest_dir: Path) -> str:
    """The row's repo-root-relative dest path (§ engine.py `_repo_relative_path`,
    § docs/plans/2026-08-07-publish-identity-scrub-and-two-repo-gates.md chunk
    C3), forward-slashed, no leading/trailing slash -- `""` for a toplevel row
    (`dest_dir` IS the repo root, or no `.git` ancestor is found at all -- the
    identity check has its own separate fail-closed handling for that case;
    this helper degrades to the pre-existing `""` default rather than raising).

    Review: code-reviewer (Finding 1, P1) -- this is the piece that was never
    computed at all: every real caller of `run_percolate`/`run_inject_for_section`
    omitted `dest_prefix`, so it silently defaulted to `""` on every publish,
    including the five of six klabauter rows whose dest IS a subdir.
    """
    repo_root = _dest_repo_root(dest_dir)
    if repo_root is None or repo_root == dest_dir:
        return ""
    return dest_dir.relative_to(repo_root).as_posix()


def _dest_is_owned_subdir(dest_dir: Path) -> bool:
    """True iff `dest_dir` is a subdirectory BENEATH a destination repo root
    rather than the root itself — i.e. iff every file directly under it was put
    there by a publish row and none belongs to the destination repo.

    Sole consumer: `dispatch_mirror_like`'s `sweep_top_level_orphans` argument
    (see `publish_sync._sweep_mirror_top_level_orphans` for the retirement this
    unblocks). Fail-closed by construction — `_dest_repo_root` returns None when
    no `.git` ancestor is found at all, and that is "could not determine", never
    "not the root". A bare `_dest_repo_root(d) != d` would read None as
    not-the-root and authorize a delete on exactly the case nothing is known
    about, so the None arm returns False here instead.

    Must be called with a row's REAL `dest_dir`, never a staging tree — see
    `dispatch_mirror_like`'s own docstring for why the distinction decides
    whether files are deleted.
    """
    repo_root = _dest_repo_root(dest_dir)
    if repo_root is None:
        return False
    return repo_root != dest_dir


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


#: The `git status --porcelain=v1 -z` status codes that emit TWO NUL-separated
#: path fields (new path, then old path). Every other code emits exactly one.
_PORCELAIN_TWO_PATH_CODES = ("R", "C")


def _parse_porcelain_z(stdout: str) -> "List[str]":
    """Parse `git status --porcelain=v1 -z` output into a de-duplicated path
    list, preserving first-seen order.

    Split out from its caller so the parsing is testable without a git repo,
    and so `_dirty_paths_under` reduces to "ask the engine, parse the answer"
    with no branching of its own."""
    fields = stdout.split("\0")
    paths: "List[str]" = []
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        # Porcelain v1 is a fixed 2-char status code, one space, then the
        # path — sliced by position rather than split on whitespace, which
        # would mis-parse both the leading-space codes (` M`) and any path
        # containing a space.
        code, path = record[:2], record[3:]
        if not path:
            continue
        paths.append(path)
        if code[:1] in _PORCELAIN_TWO_PATH_CODES:
            # Rename/copy: the next field is the OLD path. Its deletion is
            # part of the same dirty state, so it belongs in the same commit
            # — omitting it commits the addition and leaves the removal
            # behind, which reads to the next round as residue.
            if index < len(fields) and fields[index]:
                paths.append(fields[index])
            index += 1
    return list(dict.fromkeys(paths))


def _dirty_paths_under(repo_root: Path, scope_dirs: Sequence[Path]) -> Optional["List[str]"]:
    """Enumerate every dirty path beneath `scope_dirs` as repo-root-relative
    FILE paths — the commit pathspec `_commit_published_dests` hands
    `coordinator_core.git.commit.commit_paths`.

    Derived from `git status`, NOT from this run's own `changed_files_sink`/
    `visited_files_sink` accumulators, because those record what the sync
    WROTE and a publish round also DELETES: a deletion appears in neither
    sink, and a pathspec missing it leaves the mirror dirty after its own
    commit — reproducing the exact confusion this step exists to end
    (state/sizings/2026-08-19-percolate-auto-commits-its-own-successfu.yaml).

    `-uall` is load-bearing, not cosmetic: without it git collapses a wholly
    new directory into a single `dir/` entry, and `ceremony.scoped_git_commit`
    refuses a pathspec containing a directory element (§ `percolate-round.
    _build_commit_pathspec`, which carries the same constraint on its side of
    this seam).

    Returns `None` when the probe itself failed — deliberately distinct from
    `[]` ("clean"): committing nothing under an unknown state is the silent-
    drop shape this driver's exit-code contract exists to prevent.

    Negative-spec: does NOT widen to the whole repo root. The pathspec is
    scoped to the dest dirs this run actually swapped, so a mirror carrying
    unrelated operator edits outside those subtrees keeps them uncommitted
    rather than having them swept into a publish commit.
    """
    from coordinator_core.ops.ceremony import git_native  # noqa: PLC0415 - lazy, see module header

    probe = git_native.status_porcelain_scoped(
        repo_root, [str(scope) for scope in scope_dirs]
    )
    if not probe.ok:
        return None
    return _parse_porcelain_z(probe.stdout)


def _normalize_dest_exec_bits(repo_root: Path, scope_dirs: Sequence[Path]) -> "List[str]":
    """Re-mode every file tracked under `scope_dirs` whose blob starts with
    `#!` but whose INDEX mode is `100644`, returning the paths it fixed.

    WHY THIS EXISTS. Both this repo and the mirror run `core.fileMode=false`
    (Windows), so git never reads an exec bit off disk: a dest entry's mode is
    whatever `git add` first recorded, which is `100644` for anything newly
    added. `_extract_git_archive` deliberately preserves source modes through
    `filter='tar'`, but that work is discarded at the dest `git add`, so a
    shebanged entrypoint reaches a POSIX clone non-executable. The failure is
    silent on Windows, where every caller invokes the interpreter explicitly
    and never exercises the bit. The mirror's own release CI catches it
    (`.github/scripts/check-exec-bit.py`) — this makes the pipeline stop
    producing what that gate exists to reject.

    The predicate is deliberately the GATE's predicate, not a source-mode
    comparison: matching `check-exec-bit.py` exactly (index mode `100644` +
    blob opening `#!`) is what makes a green run here mean a green run there,
    and it needs no dest-path-to-source-path mapping. It is also correct
    where the two disagree — `coordinator/bin/percolate-mirror.py` and
    `coordinator/bin/statusline.py` are shebanged and `100644` in claude-klabauter's own
    index today, so a source-mode copy would faithfully propagate the defect.

    Converges, and is cheap once converged: an entry already at `100755` stays
    there across later `git add`s under `core.fileMode=false`, so steady state
    is two git calls that find nothing.

    Batched by construction — one `ls-files`, one `cat-file --batch`, one
    `update-index` over every offender — never a call per path
    (`coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py`).

    SCOPED TO `scope_dirs`, never the whole index, for the same reason
    `_dirty_paths_under` is: the caller's commit pathspec covers exactly these
    subtrees, and a mode change staged OUTSIDE them is one no pathspec picks
    up — it would sit staged-uncommitted and leave the mirror permanently
    dirty, tripping the next round's dest-cleanliness precondition. Fixing a
    mode this run cannot also commit is worse than leaving it to the run whose
    scope does cover it.

    Negative-spec: does NOT commit, and does NOT `git add`. It stages a mode
    delta only; the caller folds those paths into its own commit pathspec.
    """
    staged = _git_capture(repo_root, "ls-files", "--stage", "--", *[str(d) for d in scope_dirs])
    if staged is None:
        return []
    by_blob: "dict[str, List[str]]" = {}
    for line in staged.splitlines():
        meta, _, path = line.partition("\t")
        if not path:
            continue
        fields = meta.split()
        # `<mode> SP <object> SP <stage> TAB <path>`. Stage != 0 means a merge
        # conflict; leave a conflicted entry entirely alone.
        if len(fields) != 3 or fields[0] != "100644" or fields[2] != "0":
            continue
        by_blob.setdefault(fields[1], []).append(path)
    if not by_blob:
        return []

    from coordinator_core.ops.ceremony import git_native  # noqa: PLC0415 - lazy, see module header

    blobs = git_native.cat_file_batch_objects(repo_root, sorted(by_blob))
    offenders = sorted(
        path
        for blob, paths in by_blob.items()
        if (blobs.get(blob) or "").startswith("#!")
        for path in paths
    )
    if not offenders:
        return []
    if _git_capture(repo_root, "update-index", "--chmod=+x", "--", *offenders) is None:
        print(
            f"publish.py: could not re-mode {len(offenders)} shebanged path(s) in "
            f"'{repo_root}' — the mirror's release CI will reject them "
            "(.github/scripts/check-exec-bit.py).",
            file=sys.stderr,
        )
        return []
    return offenders


def _commit_published_dests(
    published_dest_dirs_by_repo_root: "dict[Path, set[Path]]",
    *,
    succeeded_row_names: Sequence[str],
    round_pinned_shas: "dict[str, str]",
) -> bool:
    """Commit each destination repo's synced bytes, once, at the successful
    conclusion of a percolation. Returns `True` when every destination either
    committed or had nothing to commit.

    WHY THIS EXISTS. A bare `coordinator-publish` run used to exit 0 with
    every gate green and leave the mirror holding its own certified output as
    uncommitted changes. `percolate-round` then refused on its dest-
    cleanliness precondition, naming `--reconcile-dest=discard` as the
    remedy — which resets the mirror to HEAD and destroys exactly those
    certified bytes. Committing here is what makes "dest is dirty" mean
    "a predecessor crashed" again, which is the only thing that precondition
    was ever meant to detect.

    COMMIT, NOT PUBLISH (PM ruling, 2026-08-19). This step ends at a local
    commit. It never pushes a branch and never merges — publishing the mirror
    stays a separate deliberate act, named for the operator by `main()`'s
    per-dest `percolate-push` nudge (§ "Percolate-push next-step nudge"),
    not by this function.

    That is enforced by `push_mode=PUSH_MODE_NEVER`, which skips the
    pipeline's own push leg AND stands the `post-commit` hook's detached push
    down, so no publisher pushes this commit on any branch.

    It used to be enforced by neither. This function passed the default
    `push_mode="sync"` and relied on the push leg's `work/*`-only branch
    policy (`push_with_retry` -> `auto_push.branch_gate`) declining, because
    a publish mirror sits on `candidate`/`main`. That produced the right
    outcome for a reason unrelated to the requirement: the mirror was
    unpublished because of how its branch happened to be NAMED, so renaming
    it to `work/*` — or relaxing that policy for any reason of its own —
    would have turned every percolation into a publication, silently and
    with nothing in this file to catch it. A side effect is not a safeguard;
    the mode is (2026-08-21, PM: "there shouldn't be an auto-push ... the
    percolation should end in a commit and then suggest publishing with
    another button press").

    Calls `coordinator_core.git.commit.commit_paths` in-process (`ceremony.
    commit_v2`'s own in-process call, mirrored here rather than round-tripped
    through the op registry -- this driver already runs in-process) --
    repointed off the killed `run_commit_pipeline` (C4, docs/plans/2026-08-29-
    the-push-subsystem-leaves-and-then-the-pipeline-can-go.md), the same
    shape `execute_plan_assemble.close_out_and_stamp` and `ops.session.
    safe_commit_offer` were repointed onto by the same plan. No push leg at
    all: this loop never owned a synchronous push, publication stays a
    separate deliberate act per this function's own "COMMIT, NOT PUBLISH"
    section above.

    Negative-spec: NOT called under `--dry-run`, NOT called when any row
    failed, and NOT called when an end-of-run gate failed — a gate failure
    means this run's published bytes are unverified (AC15 fail-closed), and
    committing unverified bytes would hand the next round a clean dest that
    certifies nothing.

    Negative-spec: does NOT run when `percolate-round` drives the publish
    (it passes `--no-commit`). The round owns its own
    commit -> CI-smoke -> push sequence (DR-301) and moving the commit ahead
    of its CI smoke would reorder that contract.
    """
    from functools import partial  # noqa: PLC0415 - lazy, keeps this driver's import cost off every run

    from coordinator_core.git.commit import (  # noqa: PLC0415
        CommitRefused,
        FilterUnsupported,
        commit_paths,
        hash_worktree_blobs_via_spawn,
    )

    all_ok = True
    for repo_root, scope_dirs in published_dest_dirs_by_repo_root.items():
        if not scope_dirs or not _is_git_repo(repo_root):
            continue
        paths = _dirty_paths_under(repo_root, sorted(scope_dirs))
        if paths is None:
            print(
                f"publish.py: could not enumerate dirty paths under '{repo_root}' "
                "(git status probe failed) — refusing to commit under an unknown "
                "state; the mirror is left dirty and this run exits non-zero.",
                file=sys.stderr,
            )
            all_ok = False
            continue
        # Before the pathspec is frozen, not after: a re-moded path is only
        # in the commit if it is in `paths`, and `_dirty_paths_under` cannot
        # see a mode delta that does not exist yet.
        remoded = _normalize_dest_exec_bits(repo_root, sorted(scope_dirs))
        if remoded:
            print(
                f"  {repo_root}: re-moded {len(remoded)} shebanged path(s) to 100755 "
                f"({', '.join(remoded[:5])}{', …' if len(remoded) > 5 else ''})."
            )
            paths = sorted(set(paths) | set(remoded))
        if not paths:
            print(f"  {repo_root}: already clean — nothing to commit.")
            continue
        rows = ", ".join(succeeded_row_names) if succeeded_row_names else "no named rows"
        subject = (
            f"percolate: sync {len(paths)} path(s) to {repo_root.name} ({rows})"
            f"{_pinned_source_sha_suffix(round_pinned_shas)}"
        )
        # `deleted_paths` split out explicitly: `commit_paths` reads a
        # present path's bytes off the worktree, so a path the sync deleted
        # must go through its `deleted_paths` kwarg instead of `paths` --
        # the same accounting `run_commit_pipeline`'s own `stage_paths`
        # auto-classification used to do internally (`ceremony.
        # scoped_git_commit`'s 2026-08-04 defect A/B, whose own call site
        # passes exactly this). Measured here before that fix: a deleted
        # file stayed `D` in the mirror after a "successful" commit -- i.e.
        # still dirty, which is the whole failure this step exists to end.
        present_paths = [p for p in paths if (repo_root / p).exists()]
        deleted_paths = [p for p in paths if p not in present_paths]
        try:
            outcome = commit_paths(
                repo_root,
                present_paths,
                subject,
                deleted_paths=deleted_paths,
                blob_fallback=partial(hash_worktree_blobs_via_spawn, cwd=repo_root),
            )
        except (CommitRefused, FilterUnsupported) as exc:
            print(
                f"publish.py: commit of '{repo_root}' failed — the published "
                "bytes ARE on disk but are not committed; reconcile by hand "
                "before the next round."
                f"\n  {exc}",
                file=sys.stderr,
            )
            all_ok = False
            continue
        sha = outcome.sha
        print(f"  {repo_root}: committed {len(paths)} path(s) as {sha[:12]}.")
        # No `integrity_breach` branch here any more, and its absence is the
        # contract rather than an omission: `PUSH_MODE_NEVER` returns
        # `integrity_breach=False` unconditionally (there is no synchronous
        # push outcome to breach against). The line it replaced reported a
        # FAILED push, which this mode can no longer produce.
        #
        # No push notice here either, deliberately: `main()` already prints
        # one per DEST (§ "Percolate-push next-step nudge", 2026-08-20),
        # grouped by dest sigil so nine klabauter rows collapse to one line
        # naming the base row. A second notice in this loop printed the same
        # command twice per round — observed live 2026-08-21.
    return all_ok


def should_warn_unresolved_rename_exemption(
    *,
    dry_run: bool,
    renamed_file_names: "frozenset[str] | None",
    mode_descriptor: object,
    declares_basename_rename: bool,
) -> bool:
    """Whether a dry-run row owes the `Rename exemption: UNRESOLVED` banner.

    Pure decision, extracted from `process_target` so the condition is
    testable without standing up a git work tree and spawning a publish
    (`coordinator/tests/test_publish_rename_banner_covers_flat_mirror.py`).

    Fires when ALL hold: this is a PREVIEW (a real run resolves the exemption
    or refuses outright, so the banner would be a lie there); the exemption
    did NOT resolve (`renamed_file_names is None`); the mode is mirror-like
    (`manifest`/`repo-cut` print no sync preview, so there are no REMOVE lines
    to explain); and the row ACTUALLY declares a `basename_rename`.

    NEGATIVE SPEC -- deliberately NOT keyed on
    `mode_descriptor.accepts_renamed_dir_names`, which is what this predicate
    replaced and what made the banner unreachable for `flat-mirror`. That flag
    answers "does this mode's entry point take `renamed_dir_names`?", not
    "can this row's preview print a misleading REMOVE?" -- and `flat-mirror`
    answers False to the first and True to the second, which is precisely the
    gap. Keyed on the row's own declaration rather than the mode so a
    flat-mirror row with no rename map stays silent.
    """
    if not dry_run or renamed_file_names is not None:
        return False
    if mode_descriptor is None or not getattr(mode_descriptor, "is_mirror_like", False):
        return False
    return bool(declares_basename_rename)


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

    An EXISTING `dest_dir` that has no other `.git` ancestor above it (i.e.
    this row's `dest_dir` is itself supposed to BE the repo root — the
    toplevel row, no `dest_subdir`) but also carries no `.git` of its own is
    a DEGRADED destination, not a virgin one: some earlier run's swap left
    content behind without its repo metadata (§
    `_swap_publish_staging_into_dest`'s `PublishSwapPartial`). That must also
    fail loudly rather than silently treat stray content as ready to publish
    back over.

    Port of setup/publish.sh."""
    if target.dest_dir.is_dir():
        if not (target.dest_dir / ".git").exists() and not _dest_has_git_ancestor(target.dest_dir.parent):
            print(
                f"  Error: destination is a repo-root row but has no .git "
                f"(degraded, not virgin — a prior swap may have stranded it "
                f"elsewhere; see _swap_publish_staging_into_dest): {target.dest_dir}",
                file=sys.stderr,
            )
            print(f"  Skipping {target.name}.", file=out)
            print("", file=out)
            return False
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
# Declared-ref assertion (C8, docs/plans/2026-08-15-klabauter-release-
# channels.md) -- DoE's highest-severity finding: nothing on the copy path
# previously asserted the dest's checked-out branch, so a publish intended
# for one branch could land silently on whatever happened to be checked out.
# Runs at dest resolution, per-row, BEFORE `dispatch_mirror_like` and before
# any destination write this function's caller (`process_target`) performs --
# placement is deliberate, see that call site's own comment. Generic: asserts
# ANY row's dest against ITS OWN declared `publish.mirrors.<key>.track_ref`
# (C9, docs/reference/klabauter-release-channels.md § "The declared registry
# fact"); nothing here names klabauter.
#
# Refusing is the feature -- this never checks the dest out itself.
# ---------------------------------------------------------------------------
_PUBLISH_MIRRORS_PREFIX = "publish.mirrors."
_PUBLISH_MIRROR_PATH_SUFFIX = ".path"
_PUBLISH_MIRROR_TRACK_REF_SUFFIX = ".track_ref"
# The raw portable-row dest-sigil prefix (`publish-mirror:<key>`,
# resolve_target.py's "Publish-mirror" row shape) -- distinct from
# `_PUBLISH_MIRRORS_PREFIX` above, which is the RESOLVED registry key
# namespace (`publish.mirrors.<key>.*`); `_engine_declaring_mirror_keys`
# reads the former (raw rows) and yields keys in the latter's namespace.
_PUBLISH_MIRROR_SIGIL_PREFIX = "publish-mirror:"
# LAST-RESORT default for an absent `track_ref`, matching the live
# `plugin.mirrors.<key>.track_ref` precedent's own parsers (`read_mirrors.py`,
# `coordinator_core/plugin_health/drift.py`) byte-for-byte. Reached only when
# `_resolve_remote_default_branch` also can't answer (no `origin` remote, or
# its HEAD symref was never set) -- `assert_dest_on_declared_ref` tries the
# dest's actual resolved remote default branch FIRST, so a registered mirror
# whose remote default isn't `main` is compared against its real default
# rather than an assumed one (state/subagent-share/93578a3d.../
# coordinatorcode-reviewer-e094bd79.md P1).
_DEFAULT_PUBLISH_TRACK_REF = "origin/main"


def _publish_mirror_key_for_repo_root(repo_root: Path) -> Optional[str]:
    """Reverse-lookup: which `publish.mirrors.<key>` registry entry's
    declared `.path` resolves to `repo_root`?

    The row-parsing pipeline (`percolate.targets.load_targets` ->
    `resolve_target.resolve_publish_row`) resolves the mirror `key` into an
    already-resolved `dest_dir` well before a `ResolvedTarget` reaches this
    module -- the key itself is not carried on the row, so it has to be
    recovered here by matching `dest_dir`'s repo root back against the
    registry's declared paths. Enumerates the merged registry
    (`registry.toml` then `registry.local.toml`, later wins) the same order
    `coordinator_core.machine_resolver.registry_get` resolves any single key.

    Returns `None` (not a registered `publish.mirrors.*` destination, or the
    registry is unreadable) when no entry's path matches -- this assertion is
    then out of scope for the row, not a refusal; a dest outside the
    `publish.mirrors.*` namespace has no declared ref to assert against."""
    from coordinator_core.machine_resolver import _flatten, _load_toml, registry_dir

    reg_dir = registry_dir()
    merged: dict = {}
    for fname in ("registry.toml", "registry.local.toml"):
        merged.update(_flatten(_load_toml(Path(reg_dir) / fname)))
    norm_root = os.path.realpath(str(repo_root))
    for key, value in merged.items():
        if not key.startswith(_PUBLISH_MIRRORS_PREFIX) or not key.endswith(_PUBLISH_MIRROR_PATH_SUFFIX):
            continue
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        path_s = str(value) if value is not None else ""
        if not path_s:
            continue
        if os.path.realpath(path_s) == norm_root:
            return key[len(_PUBLISH_MIRRORS_PREFIX) : -len(_PUBLISH_MIRROR_PATH_SUFFIX)]
    return None


@functools.lru_cache(maxsize=None)
def _dest_checked_out_ref(repo_root: Path) -> Optional[str]:
    """The dest's current local branch name (`git symbolic-ref --short HEAD`),
    or `None` on any failure -- git absent, not a work tree, or a detached
    HEAD (symbolic-ref has no ref to report, exits non-zero), which is
    already a correct mismatch: a detached dest never matches a declared
    branch name. `symbolic-ref`, not `rev-parse --abbrev-ref`, deliberately
    -- the latter fails on an unborn branch (a freshly-created dest with no
    commits yet still has a real checked-out branch name to assert).

    Invoked from OUTSIDE the clone via `git -C` -- never `cd`, the
    publish-mirror guard refuses that including for read-only git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    ref = result.stdout.strip()
    return ref or None


@functools.lru_cache(maxsize=None)
def _resolve_remote_default_branch(repo_root: Path) -> Optional[str]:
    """The dest's ACTUAL remote default branch (`origin/<branch>`), read from
    the local `refs/remotes/origin/HEAD` symbolic ref -- the pointer a plain
    `git clone` sets automatically, no network call. `None` when no such ref
    exists (no `origin` remote, or it was never set) -- the caller degrades
    to `_DEFAULT_PUBLISH_TRACK_REF` in that case, same as before this
    function existed. Deliberately local-only: a network `git ls-remote` on
    this pre-write gate would trade a wrong-name default for a slow/offline-
    fragile one, worse than the fallback it would replace."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    ref = result.stdout.strip()
    return ref or None


def _expected_local_branch(track_ref: str) -> str:
    """`track_ref` values follow the live `plugin.mirrors.<key>.track_ref`
    shape -- `origin/<branch>` or a bare branch/tag name
    (`refresh-plugin-live-install.py`'s own checkout leg strips the
    `origin/` prefix to name the local branch it checks out); normalize the
    same way so the comparison is against what the dest's local branch name
    would actually be, not the remote-qualified spelling."""
    if track_ref.startswith("origin/"):
        return track_ref[len("origin/") :]
    return track_ref


# Per-portable-file cache for `_engine_declaring_mirror_keys` (below) --
# keyed on the resolved `publish-targets.portable` path (str), not on
# `setup_dir` itself, so distinct portable files (distinct tests, or a
# future distinct percolation source) never share an entry, while N rows
# against the SAME portable file within one publish round parse it once.
_ENGINE_DECLARING_MIRROR_KEYS_CACHE: "dict[str, frozenset]" = {}


def _engine_declaring_mirror_keys(setup_dir: Optional[Path]) -> "frozenset[str]":
    """Which `publish.mirrors.<key>` registry keys the PRIMARY portable
    topology (`setup/publish-targets.portable`) actually writes
    `coordinator_core` into for -- i.e. which mirrors carry the engine
    payload (the `claude-klabauter` row, klabauter shape) versus which are
    registered but deliberately engine-free (coordinator-claude shape).

    Derived from the SAME rows that already declare klabauter's engine
    payload -- self-maintaining DATA, not a second registry key an operator
    has to remember to set (`assert_dest_engine_root_viable`'s SCOPE
    docstring, second narrowing). A row counts when its dest sigil is
    `publish-mirror:<key>` (field 2) and its dest_subdir (field 4) is
    exactly `coordinator_core` or a strict descendant of it -- same
    strict-descendant reading `allowlist.py::_apply_exclusions` uses for
    inclusion entries, not a bare prefix match (`coordinator_core-extra`
    must not count).

    Reads the UNRESOLVED row set the same way `raw_dest_sigil_by_name`
    does -- no machine-local resolution, no subprocess -- so this stays
    cheap enough for the per-row call site below. Memoized per resolved
    portable-file path (see cache above); `setup_dir=None` (call site could
    not resolve one) falls back to this repo's own `setup/`, matching
    `_resolve_percolate_root_and_rung`'s rung-3 last resort.

    Fails OPEN (empty set, "declares nothing here") on ANY resolution
    failure -- portable file missing or unreadable -- same posture as
    `_publish_mirror_key_for_repo_root` returning `None`: a config-read
    failure must never turn into a publish refusal."""
    _bootstrap_engine()
    resolved_setup_dir = setup_dir if setup_dir is not None else (_REPO_ROOT / "setup")
    try:
        portable_file = _resolve_portable_file(resolved_setup_dir)
    except Exception:
        return frozenset()

    cache_key = str(portable_file)
    cached = _ENGINE_DECLARING_MIRROR_KEYS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    keys: "set[str]" = set()
    try:
        if portable_file.is_file():
            for raw_row in _iter_portable_rows(portable_file):
                fields = raw_row.split("|")
                if len(fields) < 5:
                    continue
                sigil = fields[2]
                if not sigil.startswith(_PUBLISH_MIRROR_SIGIL_PREFIX):
                    continue
                dest_subdir = fields[4]
                if dest_subdir == "coordinator_core" or dest_subdir.startswith("coordinator_core/"):
                    keys.add(sigil[len(_PUBLISH_MIRROR_SIGIL_PREFIX) :])
    except Exception:
        keys = set()

    result = frozenset(keys)
    _ENGINE_DECLARING_MIRROR_KEYS_CACHE[cache_key] = result
    return result


def assert_dest_engine_root_viable(
    target: "ResolvedTarget",
    totals: RunTotals,
    *,
    setup_dir: Optional[Path] = None,
    out: IO[str] = sys.stdout,
) -> bool:
    """Refuse this row when the dest is in a state the published-engine rung
    would reject: detached HEAD, or `coordinator_core/` absent from the dest
    after this round would complete (C10). Returns True (proceed) for a dest
    with no `.git` ancestor at all (`_ensure_dest_ready` owns that refusal).

    DoE synthesized a broken mirror and drove the ladder against it
    (`DoE-claude coordinator/tests/test_engine_root_degraded_mirror_outcomes.py`,
    `be3dec68b027`, five cases, mutation-tested): a clean consumer box hits
    `unresolved`/root `None` -- a LOUD failure, not wrong bits. A MIXED
    machine (a consumer repo alongside a reachable live checkout) is the
    only one of the five shapes that silently falls through to the live
    working tree instead -- that fallback is NOT the general behaviour of
    every consumer, only of that mixed-machine shape. An engine-working repo
    never consumes the published engine at all, so it cannot bite either way.
    `_prepublish_projection.py` records `coordinator/percolate/` "observed
    absent on the 2026-08-12-registered claude-klabauter mirror" and falls
    through today, so the degraded state this guard closes is real, not
    theoretical.

    A test proving what a degraded mirror DOES (their fixture above) is not
    a guard preventing publish from CREATING one -- different doors, which
    is why this still ships against their fixture rather than being
    satisfied by it.

    This closes the PUBLISH-TIME path only. NAMED RESIDUAL, not solved
    here: a session can be mid-turn when someone runs `git checkout` in the
    mirror outside a publish, and under whole-box dogfooding a promotion
    (`klabauter-promote.py`) IS a checkout event -- the same silent fallback
    to the live working tree, arriving through a door this guard does not
    cover. See docs/reference/klabauter-release-channels.md's "Named
    residuals" section (C11's live-ops preflight is a partial mitigation,
    not a fix).

    SCOPE, corrected post-review (state/subagent-share -- coordinatorcode-
    reviewer-e094bd79.md, two P1s): DoE's own evidence for this guard is a
    REGISTERED mirror going degraded ("the 2026-08-12-registered claude-
    klabauter mirror") -- `resolve_engine_root()`'s downstream consumers only
    ever reach a dest through the `publish.mirrors.*` registry, so a dest
    this row's registry has no entry for is never on that path at all and
    the check is out of scope for it, same rationale C9
    (`assert_dest_on_declared_ref`) already applies via
    `_publish_mirror_key_for_repo_root`. Without this, EVERY mirror row --
    a docs mirror, a flat toplevel mirror, an unregistered test/ad-hoc dest
    -- was refused merely for lacking a `coordinator_core/` it was never
    meant to have.

    SCOPE, second narrowing (cross-repo memo 2026-08-16-doe-claude-em-
    engine-guards-block-coordinator-claude-publish.md): registration alone
    is still too wide -- `coordinator_claude` (`publish.mirrors.
    coordinator_claude`, path per `machine-local get publish.mirrors.
    coordinator_claude.path`) IS a registered mirror and is DELIBERATELY
    engine-free by design (the doctrine-only OSS mirror; it has never
    carried `coordinator_core/`), so all 5 of its rows refused under the
    registration-only predicate -- 0/5 rows succeeded.
    Registration answers "does a declared registry entry exist for this
    dest", not "does this mirror carry the engine payload"; those are
    different facts and only the second one is what this guard is FOR.
    Narrowed again to `_engine_declaring_mirror_keys()`: a registered
    mirror's key is in scope for this guard IFF the portable topology
    itself writes `coordinator_core` into it somewhere (the `claude-
    klabauter` row does; no `coordinator_claude` row does). Derived rather
    than a THIRD registry key (`declares_engine`) an operator would have to
    remember to set -- "the operator remembers" is not an artifact, and a
    derived-from-data predicate is self-maintaining against the same rows
    that already declare klabauter's payload. Default is `False` (not
    declaring), so an engine-free mirror is never judged on an absence that
    defines it, and this second narrowing is itself scoped BENEATH the
    first: an unregistered dest still short-circuits above without ever
    reaching this check.

    POST-WRITE, not just current state: a dest whose OWN `coordinator_core/`
    is exactly what THIS row's write is about to populate (source already
    carries it) must not be judged on its pre-write absence -- that is a
    virgin-dest false refusal, not a degraded mirror. `target.dest_dir ==
    engine_root_dir` already covered the "this row IS the coordinator_core
    row" shape; `target.source_dir / "coordinator_core"` covers the same
    row-writes-the-payload-directly shape when the dest nests it one level
    down. A sibling row (bin/scripts/lib) whose OWN write never touches
    `coordinator_core/` still correctly reads CURRENT state -- its write
    can't make coordinator_core appear or vanish, so "does it exist right
    now" is the right question for it; a true first-ever multi-row bootstrap
    ordering gap (an entrypoint row runs before the emitter row has ever
    written coordinator_core once) is a NAMED RESIDUAL, not solved here --
    same posture as the residual above, and out of scope per the "do not
    move guard placement" constraint on this pass."""
    repo_root = _dest_repo_root(target.dest_dir)
    if repo_root is None:
        return True

    mirror_key = _publish_mirror_key_for_repo_root(repo_root)
    if mirror_key is None:
        # Not a registered `publish.mirrors.*` destination -- no declared
        # engine-root expectation to assert against (see SCOPE above).
        return True

    if mirror_key not in _engine_declaring_mirror_keys(setup_dir):
        # Registered, but the portable topology never writes coordinator_core
        # into this mirror -- an engine-free mirror by design (coordinator-
        # claude shape), out of scope for this guard (see SCOPE, second
        # narrowing, above). Default False keeps this check inert for a
        # mirror that never declared an engine payload in the first place.
        return True

    actual_ref = _dest_checked_out_ref(repo_root)
    if actual_ref is None:
        print(
            f"  Error: dest at {repo_root} is on a detached HEAD -- the "
            "published-engine rung would reject it.",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False

    engine_root_dir = repo_root / "coordinator_core"
    will_have_engine_root = (
        engine_root_dir.is_dir()
        or target.dest_dir == engine_root_dir
        or (target.source_dir / "coordinator_core").is_dir()
    )
    if not will_have_engine_root:
        print(
            f"  Error: {engine_root_dir} would be absent after this round -- "
            "the published-engine rung would reject it.",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False
    return True


def assert_dest_on_declared_ref(
    target: "ResolvedTarget", totals: RunTotals, *, out: IO[str] = sys.stdout
) -> bool:
    """Refuse this row when the dest's checked-out branch does not match its
    declared `publish.mirrors.<key>.track_ref` (C9). Returns True (proceed)
    for a dest with no `.git` ancestor at all (`_ensure_dest_ready` owns that
    refusal) and for a dest outside the `publish.mirrors.*` namespace (no
    declared ref exists to assert against)."""
    repo_root = _dest_repo_root(target.dest_dir)
    if repo_root is None:
        return True
    key = _publish_mirror_key_for_repo_root(repo_root)
    if key is None:
        return True

    from coordinator_core.machine_resolver import registry_get

    track_ref = (
        registry_get(f"{_PUBLISH_MIRRORS_PREFIX}{key}{_PUBLISH_MIRROR_TRACK_REF_SUFFIX}")
        or _resolve_remote_default_branch(repo_root)
        or _DEFAULT_PUBLISH_TRACK_REF
    )
    expected_branch = _expected_local_branch(track_ref)
    actual_ref = _dest_checked_out_ref(repo_root)
    if actual_ref is None:
        print(f"  Error: could not read the checked-out ref at {repo_root}.", file=sys.stderr)
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False
    if actual_ref != expected_branch:
        print(
            f"  Error: dest is not on the declared publish ref for '{key}' "
            f"(expected '{expected_branch}', dest is on '{actual_ref}').",
            file=sys.stderr,
        )
        print(f"  Skipping {target.name}.", file=out)
        print("", file=out)
        return False
    return True


# ---------------------------------------------------------------------------
# Candidate-to-main divergence report (C14, docs/plans/2026-08-15-klabauter-
# release-channels.md) -- discharges "promotion-by-memory". The PM owns the
# promotion ACT; what must not depend on memory -- theirs or an EM's -- is
# NOTICING that one is due. This computes the notice, every publish round,
# for any dest whose declared `publish.mirrors.<key>.track_ref` (C9) names a
# channel other than the default `origin/main` -- i.e. any mirror that
# actually carries a candidate/release branch, not just klabauter by name.
#
# Thresholds are a first guess, deliberately, not a ruling -- PM, 2026-08-15:
# "lick your LLM finger, stick it in the air, and call it... so long as I get
# a reminder if it's getting bad." At the measured ~7.3h median inter-round
# publish cadence (docs/reference/klabauter-release-channels.md), 300 commits
# is roughly a fortnight of real drift and 750 roughly a month -- a later
# reader should be adjusting these two numbers, not re-deriving the policy:
#   - advisory  at 300 commits ahead of origin/main, OR 14 days since the
#     last promotion, whichever comes first;
#   - escalated wording at 750 commits.
#
# Reported, never gated -- a publish must never fail, not even a non-zero
# exit, because this delta is large. Any failure in the computation itself
# (no candidate branch yet -- the live state today, no origin/main, a git
# error) degrades to a quiet skip: a diagnostic that can break the publish
# path is worse than no diagnostic.
# ---------------------------------------------------------------------------
_CANDIDATE_DIVERGENCE_ADVISORY_COMMITS = 300
_CANDIDATE_DIVERGENCE_ADVISORY_DAYS = 14
_CANDIDATE_DIVERGENCE_ESCALATED_COMMITS = 750


def _git_rev_list_count(repo_root: Path, range_spec: str) -> Optional[int]:
    """`git rev-list --count <range_spec>` from OUTSIDE the clone (`git -C`,
    never `cd` -- same publish-mirror-guard constraint as `_dest_checked_out_
    ref`). Returns `None` on any failure -- git absent, not a work tree, an
    unknown ref on either side of the range (e.g. no candidate branch yet),
    or malformed output -- so the caller can treat "no answer" as "nothing to
    report" rather than a crash."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", range_spec],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _git_merge_base_date(repo_root: Path, ref_a: str, ref_b: str) -> Optional[datetime]:
    """Commit date (`%cI`, timezone-aware ISO 8601) of `git merge-base ref_a
    ref_b`, or `None` on any failure. No promotion-record artifact exists
    yet (`klabauter-promote.py` does not write one) -- this is the honest
    fallback source for "days since last promotion" the plan calls for: the
    point where the candidate line last touched `main` is the best available
    proxy for "when was this last promoted", named as a fallback rather than
    silently reported as if it were a real promotion record."""
    try:
        mb_result = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", ref_a, ref_b],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if mb_result.returncode != 0:
        return None
    sha = mb_result.stdout.strip()
    if not sha:
        return None
    try:
        date_result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%cI", sha],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if date_result.returncode != 0:
        return None
    iso = date_result.stdout.strip()
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def report_candidate_divergence(repo_root: Path, *, out: IO[str] = sys.stdout) -> None:
    """Emit an advisory when a dest's declared candidate/release branch (C9's
    `publish.mirrors.<key>.track_ref`) has drifted from `origin/main` past
    the thresholds above -- called from `main()`, once per distinct
    published dest repo root, after the round lands.

    Skips silently (no `key`, `track_ref` is the default `origin/main` --
    this dest mirrors main itself, no candidate channel exists to diverge --
    or the divergence computation fails for any reason) rather than raising:
    a publish must never fail on this report's account (plan body, "Reported,
    never gated"). Below-threshold divergence is also silent, deliberately
    -- this is an advisory for a PM to act on, not a per-round status line,
    and the guard-messaging register this repo follows treats repetition as
    the failure mode, not the omission.

    Reports THREE numbers, per the PM's own target register (plan body):
    the actual distance, the recommendation, and the post-promotion delta --
    the last is always 0 in this topology, because promotion fast-forwards
    `main` onto the candidate ref (docs/reference/klabauter-release-
    channels.md's promotion mechanism, arm 3) rather than resetting to some
    smaller residual; that is the number that makes the recommendation
    actionable rather than nagging."""
    try:
        key = _publish_mirror_key_for_repo_root(repo_root)
        if key is None:
            return

        from coordinator_core.machine_resolver import registry_get

        # Review: E-divergence-report — reuse _resolve_remote_default_branch
        # (slice D) rather than falling straight to the _DEFAULT_PUBLISH_
        # TRACK_REF constant, matching the sibling resolution at
        # assert_dest_on_declared_ref above.
        track_ref = (
            registry_get(f"{_PUBLISH_MIRRORS_PREFIX}{key}{_PUBLISH_MIRROR_TRACK_REF_SUFFIX}")
            or _resolve_remote_default_branch(repo_root)
            or _DEFAULT_PUBLISH_TRACK_REF
        )
        if track_ref == _DEFAULT_PUBLISH_TRACK_REF:
            return  # this mirror tracks main itself -- no candidate channel to diverge
        candidate_branch = _expected_local_branch(track_ref)

        commits_ahead = _git_rev_list_count(repo_root, f"origin/main..{candidate_branch}")
        if commits_ahead is None:
            return  # no candidate branch yet (today's live state), no origin/main, or a git error

        last_promotion_date = _git_merge_base_date(repo_root, "origin/main", candidate_branch)
        days_since: Optional[int] = None
        promotion_source = "no promotion record exists — falling back to the merge-base date"
        if last_promotion_date is not None:
            if last_promotion_date.tzinfo is None:
                last_promotion_date = last_promotion_date.replace(tzinfo=timezone.utc)
            days_since = max(0, (datetime.now(timezone.utc) - last_promotion_date).days)

        # Review: E-divergence-report — the days-only trigger is gated on
        # commits_ahead > 0 so a stationary candidate (0 commits ahead, just a
        # stale merge-base date) never fires a "recommend promoting ... drops
        # the delta from 0 to 0" advisory -- there is nothing to promote.
        advisory = commits_ahead > 0 and (
            commits_ahead >= _CANDIDATE_DIVERGENCE_ADVISORY_COMMITS
            or (days_since is not None and days_since >= _CANDIDATE_DIVERGENCE_ADVISORY_DAYS)
        )
        if not advisory:
            return

        escalated = commits_ahead >= _CANDIDATE_DIVERGENCE_ESCALATED_COMMITS
        severity = "ESCALATED" if escalated else "advisory"
        if days_since is not None:
            days_clause = f"{days_since}d since last promotion ({promotion_source})"
        else:
            days_clause = "days-since-promotion unavailable"

        print("", file=out)
        print(
            f"  [{severity}] '{candidate_branch}' is {commits_ahead} commit(s) ahead of "
            f"origin/main ({days_clause}).",
            file=out,
        )
        print(
            f"  Recommend promoting '{candidate_branch}' to main now -- that drops the "
            "delta from "
            f"{commits_ahead} to 0.",
            file=out,
        )
    except Exception:
        return


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
# phases has already succeeded. A raise in the sync/sweep/guard/inject/pre_ci
# phases discards the staging copy; the real destination is never touched.
# Once the swap itself (`_swap_publish_staging_into_dest`) begins, that
# guarantee narrows: a raise from the content rename restores `dest_dir` from
# `prior_backup` and re-raises (destination still ends up as the prior tree,
# untouched in effect), but a raise from the trailing `.git` re-home
# (`PublishSwapPartial`) leaves new content already live at `dest_dir` with
# `.git` stranded at `prior_backup` — observable, not silently absorbed. See
# that function's docstring for the exact state at each step.
# ---------------------------------------------------------------------------
def _rmtree_clear_readonly_onerror(func: Callable, path: str, exc_info) -> None:
    """`shutil.rmtree` error handler: on Windows a read-only attribute makes
    the underlying `os.remove`/`os.rmdir` raise, which — under a bare
    `ignore_errors=True` — aborts the walk with the directory only PARTIALLY
    removed rather than skipping past it. This clears the read-only bit and
    retries `func` once; if that still fails, the error is swallowed here
    (never re-raised) so a staging-dir cleanup can never fail the publish it
    is trying to keep tidy — matching the `ignore_errors=True` contract this
    replaces, not tightening it.

    `onerror` (not `onexc`) because this repo's floor is Python 3.11
    (`pyproject.toml`'s `requires-python`) and `onexc` is 3.12+; `onerror`
    remains accepted (if deprecated) through at least 3.14 and is the only
    signature portable across the whole supported range."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


# A provisioned fleet environment and its siblings, matched on the TOP-LEVEL
# basename only (§ `_create_publish_staging_dir`'s own "fleet-env" paragraph for
# why this is safe and why it is scoped to the root-dest row). Deliberately not
# sourced from `surface.STRUCTURAL_NEVER_PUBLISHED_PREFIXES`: that tuple answers
# "is this file publish-owned content", a question asked of every path at every
# depth, whereas this one answers "must this top-level directory be COPIED into
# staging", which has a completely different failure mode -- a wrong answer here
# deletes a multi-GB directory rather than merely skipping a scan. Keeping the
# two separate is intentional: if that tuple ever gains a name which is not a
# top-level dest-local directory, folding them together would silently start
# excluding real content from the staging copy.
_FLEET_ENV_STAGING_SKIP_RE = re.compile(r"^\.fleet-env(\.prior|\.gen-.+)?$")


def _fleet_env_unstaged_names(dest_dir: Path) -> frozenset:
    """The top-level names of `dest_dir` that `_create_publish_staging_dir`
    will NOT stage — empty for any row it stages in full.

    `_create_publish_staging_dir` is the ONLY caller, deliberately.
    `_report_published_diff` needs the same answer but derives it by looking
    at what is actually in `staging_dir` (§ its `_went_unstaged`) rather than
    calling this — an observation cannot drift from, or race, the decision it
    observes, and two earlier attempts to share a derivation here did both.

    Both conditions below are load-bearing:

      * root-dest rows only. A `dest_subdir` row's swap renames staging ONTO
        the destination, so declining to stage a name there would destroy it
        rather than preserve it; such a row is staged in full and must be
        reported in full.
      * directories only. The root-dest swap DOES unlink a top-level FILE
        absent from staging, so a file carrying one of these names is staged
        normally — and therefore has to be reported normally too.

    ROUND-SCOPED MEMO (`lru_cache`): this answer cannot change while a round is
    running, and nine rows publishing into nine subdirectories of ONE dest repo
    each asked it independently -- one `git` process per row for a fact that is
    identical across all of them. `publish.py` never runs `checkout`, `switch`,
    `fetch`, or `reset` (grepped; the only `reset --hard` in the publish chain
    is `percolate-round.py`'s dest reconcile, which runs to completion in a
    SEPARATE process before this one starts), so within one `publish.py`
    process the answer is immutable and the process lifetime IS the round.
    Keyed on `repo_root`, so two dests in one round keep their own answers.


    ROUND-SCOPED MEMO (`lru_cache`): this answer cannot change while a round is
    running, and nine rows publishing into nine subdirectories of ONE dest repo
    each asked it independently -- one `git` process per row for a fact that is
    identical across all of them. `publish.py` never runs `checkout`, `switch`,
    `fetch`, or `reset` (grepped; the only `reset --hard` in the publish chain
    is `percolate-round.py`'s dest reconcile, which runs to completion in a
    SEPARATE process before this one starts), so within one `publish.py`
    process the answer is immutable and the process lifetime IS the round.
    Keyed on `repo_root`, so two dests in one round keep their own answers.

    """
    if not (dest_dir / ".git").exists() or not dest_dir.is_dir():
        return frozenset()
    return frozenset(
        entry.name
        for entry in dest_dir.iterdir()
        if _FLEET_ENV_STAGING_SKIP_RE.match(entry.name) and entry.is_dir()
    )


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
    unbounded cost with no correctness benefit. `.git` is never moved into
    this staging tree either (not at creation, not at swap time) — it rides
    with `dest_dir` straight into `_swap_publish_staging_into_dest`'s
    `prior_backup`, untouched, and is re-homed into the new `dest_dir` only
    after the content swap has already landed. This keeps `.git` out of the
    tree every early `return`/exception before the swap discards via
    `_discard_publish_staging_dir` — a doomed directory should never hold a
    repo's only copy of its own history.

    A provisioned fleet environment (`.fleet-env/`, plus its `.prior`/`.gen-*`
    siblings — § `_FLEET_ENV_STAGING_SKIP_RE`) is excluded on exactly the same
    grounds as `.git`, and measured far larger: a live toplevel run copied
    9.6GB of vendored site-packages into staging, swept every file of it for
    depersonalization, compared it byte-for-byte via `_dir_trees_equal`, and
    then deleted the copy — four full passes over content no phase this tree
    feeds ever reads. That is the "severe, unbounded cost with no correctness
    benefit" the `.git` paragraph above names, in a bigger tree.

    Two constraints make the exclusion safe, and BOTH are load-bearing:

      * TOP-LEVEL ONLY. The ignore callable returns early unless the directory
        being walked IS `dest_dir`, so a nested path that happens to carry one
        of these basenames is copied normally. `shutil.ignore_patterns` cannot
        express this — it matches at every level — which is why this is a
        callable rather than another pattern argument.
      * ROOT-DEST ROWS ONLY, gated on `(dest_dir / ".git").exists()` — the SAME
        predicate `_swap_publish_staging_into_dest` uses to pick its root-dest
        branch, so the exclusion is exactly co-extensive with the branch that
        tolerates it. That branch swaps per top-level entry and never removes a
        directory from `dest_dir` (§ `_swap_publish_staging_into_dest_root`'s
        "Top-level DIRECTORIES are never removed here"), so an excluded
        directory is simply left in place, untouched. The whole-tree branch
        renames `staging_dir` ONTO `dest_dir`, where the same exclusion would
        destroy the environment instead of preserving it — hence the gate. A
        `dest_subdir` row's `dest_dir` never holds a `.git`, and no fleet-env
        has ever lived anywhere but a repo root, so this is belt-and-braces on
        both sides rather than a live discrimination; keep it anyway.

    `dest_dir` not yet existing (a virgin publish row, § `_ensure_dest_ready`'s
    bootstrap leg already having created it as an empty dir by the time this
    runs) yields an all-but-empty staging dir — correct, there is no prior
    content to seed it with.

    Orphan-on-partial-copy guard: `mkdtemp` and `copytree` are two separate
    steps, and this function only returns a path on FULL success. A raise
    from `copytree` partway through (permission error on one file, a
    concurrent mutation of `dest_dir` mid-copy — this machine routinely runs
    50-70 concurrent sessions, § `docs/wiki/machine-load-norm.md`) used to
    propagate straight out of this function before the `return` — the
    caller's `staging_dir = _create_publish_staging_dir(...)` assignment
    then never completes, so `process_target`'s own `staging_dir` local
    stays `None` and its `finally` block's `_discard_publish_staging_dir`
    call is a no-op (guards on `is not None`), permanently orphaning the
    already-`mkdtemp`'d, partially-copied directory with no reference left
    anywhere to reclaim it on a later run (unlike the `.prior` shape, which
    at least gets refused-on-detection next time). This function now cleans
    up its OWN `mkdtemp`'d directory before re-raising, so a caller either
    gets back a fully-seeded staging dir or nothing is left behind at all —
    the cleanup rmtree runs through `_rmtree_clear_readonly_onerror`, which
    clears a Windows read-only attribute and retries, so a read-only copied
    file cannot leave the directory only partially removed the way a bare
    `ignore_errors=True` would.
    """
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{dest_dir.name}.publish-staging-", dir=str(dest_dir.parent))
    )
    unstaged = _fleet_env_unstaged_names(dest_dir)

    def _ignore(directory: str, names: list[str]) -> set[str]:
        if Path(directory) != dest_dir:
            return set()
        return {name for name in names if name == ".git" or name in unstaged}

    try:
        if dest_dir.is_dir():
            shutil.copytree(
                dest_dir,
                staging_dir,
                ignore=_ignore,
                symlinks=True,
                dirs_exist_ok=True,
            )
    except BaseException:
        shutil.rmtree(staging_dir, onerror=_rmtree_clear_readonly_onerror)
        raise
    return staging_dir


def _sweep_stale_publish_staging_dirs(
    dest_dir: Path,
    totals: RunTotals,
    *,
    max_age_seconds: float = 3600.0,
    dry_run: bool = False,
    out: IO[str] = sys.stdout,
) -> None:
    """Removes staging directories this tool itself minted (§
    `_create_publish_staging_dir`'s `.{dest_dir.name}.publish-staging-*`
    prefix) that were orphaned by a prior run of THIS destination — a
    `kill -9`, a machine reboot, or a session killed mid-publish all leave
    one behind (the fix at commit 56c0303d7 only stops NEW orphans; it does
    nothing for ones already on disk). Called once per row, before that
    row's own `_create_publish_staging_dir`, so a stale directory never sits
    around as untracked cruft in `dest_dir`'s parent, indistinguishable from
    real publish payload in a `git status` someone might build a commit
    pathspec from.

    Glob is deliberately the exact `_create_publish_staging_dir` mint shape,
    scoped to `dest_dir.parent` only — never a broader pattern, never another
    destination's directory. `.prior` directories (§
    `_swap_publish_staging_into_dest`'s stranded-`.git` guard) are a DIFFERENT
    lifecycle with their own refuse-on-detection handling at swap time and
    are explicitly excluded here — this sweep must never touch that mechanism.

    Liveness discriminator: directory MTIME age, not a PID/liveness check.
    `mkdtemp` requires no PID bookkeeping and this glob has no reliable way
    to recover which process (if any) owns a candidate directory — a PID
    file would be another thing to get wrong under `kill -9`, and a stale
    PID reused by an unrelated process would falsely read as live anyway.
    Age is simpler and portable (pathlib/shutil only, no shell-out, no
    per-OS process-liveness API). `max_age_seconds` defaults to one hour,
    and the live-but-slow case is safer than "an hour of wall-clock row
    time" alone suggests: `shutil.copytree` (§ `_create_publish_staging_dir`)
    creates entries directly under `staging_dir` as it runs, and the OS
    refreshes a directory's own mtime on every entry creation within it —
    so a genuinely live, merely-slow concurrent copy keeps re-stamping
    `staging_dir`'s mtime for as long as it keeps creating files. This sweep
    only misfires on a live row if the directory itself goes a FULL HOUR
    between successive file-creation events, not merely if the row's total
    runtime exceeds an hour. Every observed publish row still completes in
    low single-digit minutes even at the machine's 1000+-file end of the
    size range, so the margin is wide either way.

    `dest_dir.name` is `glob.escape`d before interpolation: an un-escaped
    `*`/`?`/`[...]` in the name would let the glob under- or over-match
    against the exact literal prefix `_create_publish_staging_dir` mints
    with `tempfile.mkdtemp(prefix=...)` — this sweep deletes directories in
    a publish destination, so the match set must stay exact. The trailing
    `*` wildcard is appended after escaping and must keep its glob meaning.

    A sweep failure (permission error, concurrent removal, a transient
    holder) is logged via `warn` and this function returns — it must never
    fail the publish it is trying to keep tidy.

    `dry_run=True` keeps discovery/age-filtering intact but skips the
    `shutil.rmtree` at the removal site, printing what would have been
    swept instead — `dry_run` gates every other write in this file
    (Finding 1, s3-sweep-and-dirty review) and this is the sweep's own
    mutation, not row disposition, so it must obey the same gate without
    losing C3's row-disposition-independent placement."""
    try:
        if not dest_dir.parent.is_dir():
            return
        now = time.time()
        escaped_prefix = glob.escape(f".{dest_dir.name}.publish-staging-")
        for candidate in dest_dir.parent.glob(f"{escaped_prefix}*"):
            if candidate.name.endswith(".prior"):
                continue
            if not candidate.is_dir():
                continue
            try:
                age = now - candidate.stat().st_mtime
            except OSError:
                continue
            if age < max_age_seconds:
                continue
            if dry_run:
                print(f"  [dry-run] would sweep stale publish-staging dir: {candidate}", file=out)
                continue
            try:
                shutil.rmtree(candidate)
            except OSError as exc:
                warn(
                    totals,
                    f"stale publish-staging sweep: failed to remove {candidate}: {exc}",
                    out=out,
                )
    except OSError as exc:
        warn(totals, f"stale publish-staging sweep failed for {dest_dir}: {exc}", out=out)


def _dir_trees_equal(a: Path, b: Path) -> bool:
    """Cheap recursive equality check (relative file paths + size + mtime,
    never byte content) used only by `_swap_publish_staging_into_dest_root`
    to decide whether a root-dest top-level DIRECTORY genuinely needs its
    rename-aside swap, or can be left untouched.

    A root-dest row's `staging_dir` is seeded by `shutil.copytree`-ing the
    ENTIRE previous `dest_dir` (§ `_create_publish_staging_dir`), so every
    sibling row's top-level directory this row does not itself manage rides
    along as an untouched copy — `copytree`'s default `copy2` preserves
    mtimes, so an untouched copy's (size, mtime) pairs match the original
    exactly. Swapping those unconditionally would rename-aside (and risk a
    Windows sharing violation on) every OTHER row's live output for no
    reason — exactly the defect this whole change exists to stop causing.
    A directory this row's own manifest actually updated differs in at
    least one file's size or mtime and is swapped; an unmodified sibling
    copy does not, and is left alone."""
    if not b.is_dir():
        return False
    a_stat = {p.relative_to(a).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in a.rglob("*") if p.is_file()}
    b_stat = {p.relative_to(b).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in b.rglob("*") if p.is_file()}
    return a_stat == b_stat


def _load_publish_refusal_record_module():
    """Lazy-loads the sibling `publish_refusal_record.py` module (same
    directory as this file) via `spec_from_file_location`, matching this
    module's own established sibling-load pattern (§ `_load_publish_sync_
    module` above) rather than a bareword `import publish_refusal_record` —
    `coordinator/bin` is never added to `sys.path`, and this module can
    itself be loaded under an arbitrary name (§ `coordinator/bin/tests/
    test_publish_swap_preserves_dest_git.py`), so a bareword import is not
    guaranteed to resolve. Called ONLY from inside an `except` handler at
    one of the six swap call sites (§ CALL SITES, dispatch brief C1) — the
    success path never pays this import."""
    bin_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "publish_refusal_record", bin_dir / "publish_refusal_record.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not build a module spec for publish_refusal_record.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record_publish_swap_refusal(
    exc: BaseException,
    *,
    refused_path: Path,
    aside_path: Optional[Path],
    swap_branch: str,
    failing_operation: str,
) -> None:
    """Records ONE of the six publish-swap call sites' refusals, only when
    `exc` is the discriminated holder shape (§ `publish_refusal_record.
    is_holder_refusal`). Callers wrap this call in `try: ... except
    BaseException: pass` (§ ORDERING, dispatch brief C1) — a record-write
    (or import) failure must never substitute for or mask the original
    refusal, so this function is deliberately allowed to raise and relies
    entirely on the caller to swallow it."""
    module = _load_publish_refusal_record_module()
    if not module.is_holder_refusal(exc):
        return
    module.record_publish_swap_refusal(
        refused_path=refused_path,
        aside_path=aside_path,
        swap_branch=swap_branch,
        failing_operation=failing_operation,
        exc=exc,
    )


def _swap_publish_staging_entry(dest_entry: Path, staging_entry: Path) -> None:
    """Swaps ONE top-level name from `staging_entry` into `dest_entry` —
    the per-entry primitive `_swap_publish_staging_into_dest_root` uses in
    place of a single whole-tree rename. A file is replaced with
    `os.replace` (same-filesystem, effectively atomic). A directory is
    renamed aside first (`dest_entry` -> `dest_entry` + `.prior`), then
    `staging_entry` -> `dest_entry`; a failure of that second rename
    restores the aside copy, so a partial failure leaves `dest_entry`
    exactly as it was before this call, never missing.

    Each of the three legs below (aside rename, second rename, file
    replace) records a refusal (§ `_record_publish_swap_refusal`) before
    re-raising unchanged — this is the root-dest branch's per-entry
    primitive, so every recorded `swap_branch` here is `"root-dest"`."""
    if staging_entry.is_dir():
        prior = dest_entry.with_name(dest_entry.name + ".prior")
        if dest_entry.exists():
            try:
                os.rename(dest_entry, prior)
            except OSError as exc:
                try:
                    _record_publish_swap_refusal(
                        exc,
                        refused_path=dest_entry,
                        aside_path=prior,
                        swap_branch="root-dest",
                        failing_operation="aside_rename",
                    )
                except BaseException:
                    pass
                raise
        try:
            os.rename(staging_entry, dest_entry)
        except OSError as exc:
            if prior.exists():
                os.rename(prior, dest_entry)
            try:
                _record_publish_swap_refusal(
                    exc,
                    refused_path=staging_entry,
                    aside_path=prior,
                    swap_branch="root-dest",
                    failing_operation="content_rename",
                )
            except BaseException:
                pass
            raise
        if prior.exists():
            shutil.rmtree(prior, onerror=_rmtree_clear_readonly_onerror)
    else:
        try:
            os.replace(staging_entry, dest_entry)
        except OSError as exc:
            try:
                _record_publish_swap_refusal(
                    exc,
                    refused_path=staging_entry,
                    aside_path=None,
                    swap_branch="root-dest",
                    failing_operation="file_replace",
                )
            except BaseException:
                pass
            raise


def _refuse_stranded_root_swap_prior(dest_dir: Path) -> None:
    """The root-dest branch's counterpart to the whole-tree branch's own
    stranded-prior refusal, which it could never have reached OR matched.

    Could not reach: `_swap_publish_staging_into_dest` delegates to the
    root-dest branch and RETURNS before the whole-tree refusal below it ever
    runs. Both publish mirrors are repo roots, so both take that branch and
    neither has ever been offered a stranded-prior check.

    Could not match: the whole-tree refusal globs `dest_dir.parent` for
    `.{dest_dir.name}.publish-staging-*.prior` and predicates on a `.git`
    inside the candidate. `_swap_publish_staging_entry` mints
    `<entry>.prior` INSIDE `dest_dir` and never moves `.git` (it is not in
    `staging_dir` at all), so a root-branch strand matches neither the glob
    nor the predicate. `surface.PUBLISH_STAGING_DIR_RE` does not match it
    either -- no surface walk, manifest widening or pathspec filter sees one.

    WHAT IT COSTS TO GO UNSEEN, which is why this is a refusal and not a
    warning. `_swap_publish_staging_entry` renames `dest_entry` aside to
    `<entry>.prior`, then renames `staging_entry` into place; the restore
    sits in an `except OSError` and so covers a failed rename but NOT a
    SIGKILL, OOM or host reboot between the two. A death in that window
    leaves a whole top-level subtree gone from the worktree, its content in
    an untracked `<entry>.prior`, and every one of its files still tracked at
    dest HEAD -- which is exactly the three conditions percolate-round's
    removal side reads as a stranded removal (`(head_tree n row_scope) -
    declared_payload`). `_refuse_removals_present_on_disk` cannot catch it:
    those paths are genuinely absent. The per-entry loop reopens the window
    once per top-level entry per round.

    Reported by doe-claude-6e (2026-08-26), verified line-by-line here.
    Live mechanism, not a live incident -- neither mirror carried a strand
    when this landed.

    NO FALSE-POSITIVE PATH FROM NORMAL OPERATION. A successful swap
    `rmtree`s its own `.prior` before returning, so a surviving one means a
    swap that did not finish. `surface.STRUCTURAL_NEVER_PUBLISHED_PREFIXES`
    is subtracted because it NAMES `.fleet-env.prior` -- destination-repo
    build plumbing minted by something else entirely, which an unfiltered
    check would read as a strand and refuse every round on.
    """
    import fnmatch  # noqa: PLC0415 - lazy, this check is the only user

    from coordinator_core.percolate.surface import (  # noqa: PLC0415
        STRUCTURAL_NEVER_PUBLISHED_PREFIXES as _STRUCTURAL,
    )

    # `dest_dir.glob("*.prior")` never yields a dotted basename -- stdlib
    # glob hides `.`-prefixed names from a pattern that does not itself
    # start with `.`, and `_swap_publish_staging_into_dest_root` iterates
    # `staging_dir.iterdir()` (no dotfile filter), so it can legally mint a
    # dotted strand like `.github.prior`. Scan `iterdir()` directly instead.
    stranded = sorted(
        entry
        for entry in dest_dir.iterdir()
        if entry.name.endswith(".prior")
        and not any(fnmatch.fnmatch(entry.name, pattern) for pattern in _STRUCTURAL)
    )
    if not stranded:
        return
    shown = "".join(f"      {p}\n" for p in stranded[:10])
    raise PublishSwapPartial(
        f"refusing to publish {dest_dir}: {len(stranded)} stranded "
        "prior-backup entr(ies) from an earlier incomplete root-dest swap "
        "sit in the destination root:\n"
        f"{shown}"
        "    Each one holds the ONLY copy of a top-level subtree that is "
        "still tracked at dest HEAD but absent from its worktree. Restore it "
        "by hand (rename `<entry>.prior` back to `<entry>`, or reconcile "
        "against HEAD) before re-running this row -- publishing over it "
        "would let the removal side read that subtree as retired payload.",
        # representative sample only -- the rendered message above carries
        # the full `stranded` list; the sole consumer (`process_target`)
        # only prints the message on this path, never reads this field.
        prior_backup=stranded[0],
        content_swapped=False,
    )


def _swap_publish_staging_into_dest_root(dest_dir: Path, staging_dir: Path) -> None:
    """Root-dest branch of `_swap_publish_staging_into_dest`, taken when
    `dest_dir` IS a repo root (§ that function's docstring for the
    detection and the tradeoff this branch accepts). Never renames
    `dest_dir` itself — instead swaps top-level names one at a time via
    `_swap_publish_staging_entry`, so a live handle held anywhere under a
    SIBLING row's subtree (another `claude-klabauter*` row's own subdir, or
    a coordinator ceremony interpreter running out of this same live
    engine install) can never block this row's own publish the way a
    whole-tree rename of the repo root can on Windows.

    Add/update: for each top-level entry in `staging_dir`, swap it into
    `dest_dir` — except a directory whose content already matches `dest_dir`
    byte-for-byte per `_dir_trees_equal` (an untouched sibling-row copy;
    § that function's docstring) is left alone entirely, not even
    renamed-aside. `.git` is never a candidate here: `_create_publish_
    staging_dir` never copies it into `staging_dir` in the first place.

    Removal: a top-level FILE present in `dest_dir` but absent from
    `staging_dir` is deleted, matching what a whole-tree replace would
    have discarded — `staging_dir` is a full copy of `dest_dir` taken
    before this row's own sync/transform pipeline ran (§ `_create_
    publish_staging_dir`), and nothing else ever mutates this staging_dir
    instance, so a file that vanished from it was deliberately removed by
    THIS row's own processing (e.g. `sync_flat_mirror`'s own "not in
    source" deletion phase, which already runs against this same staging
    copy — see `process_target`'s `sync_target = replace(target,
    dest_dir=staging_dir)`). `.git` is excluded from this walk explicitly
    (belt-and-braces; it was never in `staging_dir` to begin with, so it
    could never be flagged as absent-from-staging regardless).

    Top-level DIRECTORIES are never removed here: `staging_dir` is seeded
    as a full recursive copy of `dest_dir` (§ `_create_publish_staging_
    dir`), so a directory present in `dest_dir` before this call is always
    still present in `staging_dir` too (untouched or updated) — it can
    never be "absent from staging", so no directory-removal case exists to
    preserve. This is a real asymmetry with the subdir-row whole-tree path
    (which discards an entire missing directory the same as a missing
    file), accepted because this row's actual dispatch mode
    (`sync_flat_mirror`) never manages directories at all (file-only, by
    that function's own Phase 1/2 split) — a hypothetical future root-dest
    row in a directory-managing mode would need this reconsidered, and
    should say so rather than silently relying on this note.

    Never touches `.git/coordinator-sessions/` (nested under `.git`,
    already excluded) or any other entry the row does not own; ownership
    for the add/update leg is exactly "named in `staging_dir`" — never
    inferred by listing `dest_dir` — and for the removal leg is exactly
    "a file that was in `dest_dir`'s original copy and is no longer in
    `staging_dir`"."""
    staged_names = {p.name for p in staging_dir.iterdir()}
    for staging_entry in sorted(staging_dir.iterdir(), key=lambda p: p.name):
        dest_entry = dest_dir / staging_entry.name
        if staging_entry.is_dir() and dest_entry.is_dir() and _dir_trees_equal(staging_entry, dest_entry):
            continue
        _swap_publish_staging_entry(dest_entry, staging_entry)

    if dest_dir.is_dir():
        for dest_entry in sorted(dest_dir.iterdir(), key=lambda p: p.name):
            if dest_entry.name == ".git":
                continue
            if dest_entry.is_file() and dest_entry.name not in staged_names:
                try:
                    dest_entry.unlink()
                except OSError as exc:
                    try:
                        _record_publish_swap_refusal(
                            exc,
                            refused_path=dest_entry,
                            aside_path=None,
                            swap_branch="root-dest",
                            failing_operation="unlink",
                        )
                    except BaseException:
                        pass
                    raise

    # Every entry this loop moved is gone from `staging_dir` already
    # (`os.replace`/`os.rename` both remove the source); what remains is
    # leftover cruft this row does not own (a `_dir_trees_equal`-skipped
    # sibling copy) — discard the whole staging tree now, matching the
    # whole-tree branch's own contract that `staging_dir` never survives a
    # successful swap. `_rmtree_clear_readonly_onerror` clears a Windows
    # read-only bit rather than aborting the walk partway (§ that
    # function's own docstring).
    if staging_dir.exists():
        shutil.rmtree(staging_dir, onerror=_rmtree_clear_readonly_onerror)


def _swap_publish_staging_into_dest(dest_dir: Path, staging_dir: Path) -> None:
    """Replaces `dest_dir`'s content with the fully-verified content of
    `staging_dir` (§ `_create_publish_staging_dir`) — the ONLY point in a
    staged publish row where the real destination is ever mutated, reached
    only after sync + the content-transform sweep + its guards + inject +
    pre_ci have all already succeeded against `staging_dir`.

    Root-dest branch (`dest_dir` IS a repo root — detected via `(dest_dir /
    ".git").exists()`, the same signal `_ensure_dest_ready` already uses to
    distinguish a toplevel row's own `.git` from a `dest_subdir` row's
    ancestor `.git`; a `dest_subdir` row's `dest_dir` never holds `.git`
    directly, only an ancestor does, so this check cannot false-positive on
    one): delegates to `_swap_publish_staging_into_dest_root` and returns
    immediately, BEFORE any of the whole-tree steps below ever run. On
    Windows, renaming a directory fails with a sharing violation if ANY
    process holds an open handle ANYWHERE in that subtree — for a repo-root
    `dest_dir` that subtree is the union of every sibling row's own output
    plus a live engine install's `.git`/`.git/coordinator-sessions/`
    interpreters, so the single `os.rename(dest_dir, prior_backup)` below
    can essentially never succeed for that row (`claude-klabauter-publish-
    repo-toplevel`, diagnosed via `WinError 32`/`PermissionError(13, ...)`).
    The root branch trades whole-tree swap atomicity for PER-ENTRY
    atomicity to make that rename avoidable at all — a `dest_subdir` row
    keeps the stronger whole-tree guarantee unchanged below; only the
    root-dest row takes the weaker, entry-scoped one. This tradeoff is
    deliberate, already decided, not open for re-litigation here.

    That branch also makes step 3 below (the `.git` re-home) and the
    `PublishSwapPartial` stranded-`.git` raise UNREACHABLE for the only row
    that could ever hit them: `_swap_publish_staging_into_dest_root` never
    touches `.git` at all (it is never copied into `staging_dir` — §
    `_create_publish_staging_dir` — and this function's root branch
    explicitly skips the name `".git"` in both its add/update and removal
    legs), so no `.git`-bearing `prior_backup` is ever created for that row
    under the new code, and the stranded-`.prior`-with-`.git` refuse-loudly
    guard at the top of this function (below) is also never reached for it
    (the root branch returns before that check runs). A pre-existing
    stranded `.prior` from a run of the OLD code cannot exist for this row
    either: the diagnosis established this row's root `os.rename(dest_dir,
    prior_backup)` always failed on Windows (the mirror root's files carry
    stale mtimes from before this fix), so `prior_backup` itself was never
    successfully created historically. Verified against the code, not
    assumed: the only remaining caller of step 3 / `PublishSwapPartial` is
    a `dest_subdir` row, which never has a `.git` of its own to strand in
    the first place (§ this docstring's own prior paragraph on seven of
    eight rows carrying a `dest_subdir`) — so in practice this class is now
    dead for every row, kept only because a hypothetical row shape this
    driver does not currently declare could still reach it.

    `.git` is deliberately NOT pre-moved into `staging_dir` before the swap.
    It rides with `dest_dir` into `prior_backup` untouched, and is re-homed
    into the new `dest_dir` only afterward, if one was there to move — this
    keeps `.git` out of the doomed tree that every early `return`/exception
    in `process_target` discards via `_discard_publish_staging_dir`. Refusing
    to pre-move also means step 3 below is a NO-OP on most rows: seven of
    `setup/publish-targets.portable`'s eight `claude-klabauter*` rows carry a
    `dest_subdir`, so `dest_dir` is never a repo root and never holds a real
    `.git`; only the `-publish-repo-toplevel` row does. Refuse-on-stranded-
    `.prior` guard: before any rename, refuse loudly if a `.prior` directory
    from an earlier, incomplete swap of this same destination already exists
    and still holds a `.git` — see the guard block below. `dest_dir.name` is
    `glob.escape`d before interpolation here too (§
    `_sweep_stale_publish_staging_dirs`, same rationale): an un-escaped
    `*`/`?`/`[...]` in the name would let this guard's glob under- or
    over-match against the exact literal `.prior` directories a real swap
    mints. The trailing `*.prior` suffix is appended after escaping and must
    keep its glob meaning.

    Every rename below is same-filesystem (`staging_dir` was created via
    `tempfile.mkdtemp(dir=dest_dir.parent)`), so each is a metadata-only
    operation on every OS this driver supports, never a full-tree copy. The
    prior `dest_dir` is renamed aside rather than deleted outright, and only
    reclaimed after `staging_dir` has successfully taken its place — this
    keeps the window in which the destination NAME resolves to neither tree
    as small as a single `os.rename` call, on both POSIX and Windows (neither
    of which supports atomically renaming onto an existing, non-empty
    directory, so the aside-then-remove sequence is the portable shape, not a
    POSIX-only single rename).

    Sequence and the state after a raise at each step:
      1. `dest_dir -> prior_backup` (only if `dest_dir` exists). A raise here
         leaves `dest_dir` untouched — nothing to unwind.
      2. `staging_dir -> dest_dir`. A raise here is caught, `prior_backup` is
         restored to `dest_dir` (now a COMPLETE repo, `.git` included, since
         `.git` rode along in step 1), and the exception is re-raised.
      3. `prior_backup / ".git" -> dest_dir / ".git"`, only when
         `prior_backup` exists AND holds a `.git` (i.e. only on the
         repo-toplevel row). A raise here is the one genuinely new state:
         content is already current at `dest_dir`, but `.git` is still sitting
         in `prior_backup`. This is NOT swallowed and NOT bare-re-raised — it
         is wrapped in `PublishSwapPartial`, naming `prior_backup`'s concrete
         path so an operator can finish the `.git` re-home by hand.
         `process_target` catches it, records the swap as having happened
         (content DID change), and re-raises so the row still reports FAILED.
      4. `shutil.rmtree(prior_backup, ignore_errors=True)`, reached only on
         full success.

    Accepted residual risk — an external transient holder (antivirus scan,
    search indexer) on any of these renames is not mitigated here, and that is
    deliberate. A bounded retry once wrapped all three; it was removed because
    the `PermissionError` it was added for came from a handle THIS process held
    for the whole publish (the per-destination lock sidecar, then living under
    `<dest>/.git/coordinator-locks/`), which no amount of retrying could ever
    clear. The retry did not fix that and did delay its diagnosis by a full
    cycle. A future `PermissionError` here should therefore be re-diagnosed
    from first principles — find whose handle it is — never answered by
    restoring a blind retry.

    A shape that WAS considered and cut, kept here as the shape to reach for
    IF an external holder is ever actually demonstrated (not assumed): catch
    ONLY `PermissionError`, discriminating on `.winerror in (5, 32)`
    (ERROR_ACCESS_DENIED / ERROR_SHARING_VIOLATION) — never on `.errno`
    (CPython maps both Windows codes to `EACCES`, so `.errno` cannot tell them
    apart) — and never a blanket `except OSError` (`FileExistsError` /
    `NotADirectoryError` / `IsADirectoryError` are permanent and would just be
    retried pointlessly). Bounded tightly, well under a second total, given
    the machine's 50-70 concurrent sessions. Cut on PM ruling 2026-08-10,
    staff-eng finding 5: eliminating the known self-held cause (above) is not
    the same as demonstrating an external one. Condition that would change
    this ruling: a single observed `PermissionError` with `winerror` 5 or 32
    from these renames in a real run — cite
    `state/lessons/2026-08-07-a-retry-over-a-resource-error-hides-whet-e31057280e2b.yaml`
    by file and date, not paraphrase, if reopening this. This sits ALONGSIDE
    the "re-diagnose from first principles" warning above, not instead of it.
    No retry is added here, or anywhere in this change."""
    if (dest_dir / ".git").exists():
        _refuse_stranded_root_swap_prior(dest_dir)
        _swap_publish_staging_into_dest_root(dest_dir, staging_dir)
        return

    prior_backup = staging_dir.with_name(staging_dir.name + ".prior")

    escaped_prefix = glob.escape(f".{dest_dir.name}.publish-staging-")
    for candidate in dest_dir.parent.glob(f"{escaped_prefix}*.prior"):
        if (candidate / ".git").exists():
            raise PublishSwapPartial(
                f"refusing to publish {dest_dir}: a stranded prior-backup "
                f"directory from an earlier incomplete swap still holds a "
                f".git at {candidate} — finish that re-home by hand (move "
                f"{candidate / '.git'} into {dest_dir / '.git'}) before "
                f"re-running this row",
                prior_backup=candidate,
                content_swapped=False,
            )

    if dest_dir.exists():
        try:
            os.rename(dest_dir, prior_backup)
        except OSError as exc:
            try:
                _record_publish_swap_refusal(
                    exc,
                    refused_path=dest_dir,
                    aside_path=prior_backup,
                    swap_branch="whole-tree",
                    failing_operation="prior_backup_rename",
                )
            except BaseException:
                pass
            raise

    try:
        os.rename(staging_dir, dest_dir)
    except OSError:
        # Content swap itself failed. `.git` (if any) rode into
        # `prior_backup` untouched in step 1, so restoring it here returns a
        # COMPLETE repo under the real name, not a content-only tree.
        if prior_backup.exists():
            os.rename(prior_backup, dest_dir)
        raise

    if prior_backup.exists() and (prior_backup / ".git").exists():
        try:
            os.rename(prior_backup / ".git", dest_dir / ".git")
        except OSError as exc:
            try:
                _record_publish_swap_refusal(
                    exc,
                    refused_path=prior_backup / ".git",
                    aside_path=prior_backup,
                    swap_branch="whole-tree",
                    failing_operation="git_rehome",
                )
            except BaseException:
                pass
            raise PublishSwapPartial(
                f"{dest_dir}: content swap succeeded but re-homing .git from "
                f"{prior_backup} failed ({exc}) — repo metadata is stranded "
                f"at {prior_backup}; finish the re-home by hand",
                prior_backup=prior_backup,
                content_swapped=True,
            ) from exc

    if prior_backup.exists():
        shutil.rmtree(prior_backup, ignore_errors=True)


def _forward_sync_diagnostics(buffer: "io.StringIO", real_out: IO[str]) -> None:
    """Forwards a suppressed sync-dispatch pass's genuine diagnostics —
    lines containing `WARNING`/`Error`/`ERROR` (a genuinely missing source
    file, a malformed manifest entry, an empty-source-mass-delete abort
    preview, etc.) — to `real_out`. Whitelist, not a blacklist: every OTHER
    line from that pass (`NEW:`/`UPDATE:`/`STRIP:`/`DELETE:`/`REMOVE:`/
    `NEW DIR:`/`REMOVE DIR:`/`(up to date)`/plugin-header noise) is
    unreliable before the content-transform sweep has run (§
    `_report_published_diff`) and must not reach the operator-visible log —
    a real problem report must."""
    for line in buffer.getvalue().splitlines():
        upper = line.upper()
        if "WARNING" in upper or "ERROR" in upper:
            print(line, file=real_out)


def _report_published_diff(
    staging_dir: Path,
    dest_dir: Path,
    totals: RunTotals,
    *,
    out: IO[str] = sys.stdout,
) -> "tuple[frozenset[str], frozenset[str]]":
    """Prints this row's authoritative `NEW:`/`UPDATE:`/`REMOVE:` lines and
    folds real counts into `totals.synced`/`totals.deleted`, computed by
    comparing the fully-synced-AND-transformed `staging_dir` against
    `dest_dir`'s current (pre-swap) published bytes.

    Returns `(changed, removed)`: `changed` is the `NEW:`/`UPDATE:` rel-path
    set (staging_dir-relative POSIX, `.py` and non-`.py` alike), i.e. exactly
    the files THIS row actually changed content for this run. `removed`
    (chunk C3.5, docs/plans/2026-08-23-rebuild-the-percolate-round-as-six-
    steps.md) is the `REMOVE:` set -- dest_dir-relative POSIX paths no
    longer present in `staging_dir` at all -- added so a caller building
    C2's `RoundManifest` has a real removed-set to persist rather than
    re-deriving it from a second walk or a stdout scrape; every pre-existing
    call site that ignores this function's return value is unaffected by
    the tuple's second element. `changed` alone is still never a call-
    site scope for anything. § chunk C2 of state/dispatch-briefs/2026-08-21-
    the-payload-proves-itself-before-it-overwrites-the-engine/C2.md: this
    function already computed this set for its own printed report; C2's own
    "changed files" scope (`dispatch_preswap_payload_parity_gate`) reuses it
    rather than re-deriving it with a second filesystem walk -- this is the
    one refactor the plan names ("have that function return what it already
    computes").

    This is the ONLY point a staged publish row's change report is honest:
    the sync dispatch (`sync_manifest`/`dispatch_mirror_like`) that ran
    earlier against `staging_dir` necessarily compared raw, untransformed
    source bytes against a staging seed that already carried the PRIOR
    run's post-transform output (§ `_create_publish_staging_dir` — staging
    is seeded from a copy of `dest_dir`), so for any row with a copy-time
    transform (fleet-only strip, or the engine's post_rsync content-
    transform sweep: substitute/stem-rewrite/depersonalize/basename-rename)
    that early comparison mismatches BY CONSTRUCTION on every run, whether
    or not the published bytes actually changed. Callers therefore run the
    sync dispatch against a throwaway `RunTotals`/quiet `out` (see
    `process_target`) and rely on THIS function, called immediately before
    `_swap_publish_staging_into_dest`, for the real report — `staging_dir`
    here already reflects sync + the content-transform sweep + its guards +
    inject + pre_ci, i.e. exactly what is about to be published, and
    `dest_dir` is still the untouched prior tree.

    `.git` is excluded from both sides: staging never carries one (§
    `_create_publish_staging_dir`), and `dest_dir`'s copy is publish
    machinery, never payload this row's report should count.

    The fleet-env family (§ `_FLEET_ENV_STAGING_SKIP_RE`) is excluded from the
    `dest_dir` side for the SAME structural reason, and the exclusion is NOT
    optional bookkeeping. Anything `_create_publish_staging_dir` declines to
    stage is, by construction, present in `dest_dir` and absent from
    `staging_dir`, so `set(dest_files) - set(staged_files)` would report every
    one of its files as a REMOVE. Measured on a live toplevel row: 95,256
    phantom REMOVE lines, a ~9MB log, and `totals.deleted` inflated by the
    same, for a tree the swap never touches
    (`_swap_publish_staging_into_dest_root` removes top-level FILES only).

    Not a cosmetic report defect, which is why it is pinned by tests rather
    than left to the reader: `percolate-round.py::_extract_change_lines`
    parses these exact `NEW:`/`UPDATE:`/`REMOVE:` lines to build the pathspec
    it hands `scoped-git-commit`. An unexcluded fleet-env puts ~95k paths into
    a commit pathspec, asking git to record the deletion of a gitignored
    multi-GB environment that nothing deleted.

    `_went_unstaged` OBSERVES that outcome rather than recomputing it: a
    top-level name is excluded iff it matches the family pattern AND is
    absent from `staging_dir`. Two earlier attempts re-derived the answer
    from `dest_dir` instead, and both were wrong in a way this shape cannot
    be:

      * The first dropped `_create_publish_staging_dir`'s root-dest and
        directories-only conditions, so a `dest_subdir` row (which stages the
        family in full) and a top-level FILE (which is staged deliberately,
        since the swap unlinks top-level files absent from staging) both read
        as phantom `NEW:`. Presence in `staging_dir` answers both without
        restating either condition.
      * The second restored those conditions but scanned `dest_dir` a second
        time, minutes after the copy, opening a TOCTOU window (review:
        code-reviewer on 97f0a5830): this machine runs 50-70 concurrent
        sessions, one of which provisioning a fresh `.fleet-env.gen-<pid>-
        <hex>` in that gap yields a directory staged in full but excluded
        from the dest walk — phantom `NEW:` again. A directory that appears
        after the copy is simply absent from staging and is excluded; one
        that was staged is present and is reported. No window.

    The rule to preserve is therefore "the report reflects what staging did",
    never "the report re-derives what staging should have done".

    That rule has a residual requirement `_went_unstaged` does not enforce on
    its own: it hard-codes `_FLEET_ENV_STAGING_SKIP_RE` as one leg of its AND,
    and today that agrees with `_create_publish_staging_dir`'s `_ignore`
    closure only because `_ignore` derives its exclusion set from the same
    regex (§ `_fleet_env_unstaged_names`). Any future copy-side exclusion
    added to `_ignore` that does not also match `_FLEET_ENV_STAGING_SKIP_RE`
    — a hardcoded literal, say — would be excluded from staging while
    `_went_unstaged` still returned `False` for it, reopening the phantom-
    `REMOVE:` defect this function exists to close.
    """
    staged_files: dict[str, Path] = {
        p.relative_to(staging_dir).as_posix(): p
        for p in staging_dir.rglob("*")
        if p.is_file()
    }

    def _went_unstaged(top_level_name: str) -> bool:
        return _FLEET_ENV_STAGING_SKIP_RE.match(top_level_name) is not None and not (
            staging_dir / top_level_name
        ).exists()

    dest_files: dict[str, Path] = {}
    if dest_dir.is_dir():
        for p in dest_dir.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(dest_dir).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if _went_unstaged(rel.split("/", 1)[0]):
                continue
            dest_files[rel] = p

    synced = 0
    deleted = 0
    changed: "set[str]" = set()
    removed: "set[str]" = set()
    for rel in sorted(staged_files):
        dest_path = dest_files.get(rel)
        if dest_path is None or not dest_path.is_file():
            print(f"  NEW:    {rel}", file=out)
            synced += 1
            changed.add(rel)
        elif bytes_differ(staged_files[rel], dest_path):
            print(f"  UPDATE: {rel}", file=out)
            synced += 1
            changed.add(rel)

    for rel in sorted(set(dest_files) - set(staged_files)):
        print(f"  REMOVE: {rel}", file=out)
        deleted += 1
        removed.add(rel)

    if synced == 0 and deleted == 0:
        print("  (up to date — no published-byte changes)", file=out)

    totals.synced += synced
    totals.deleted += deleted
    return frozenset(changed), frozenset(removed)


def _report_rename_manifest(
    rename_manifest: "Optional[list[dict]]", *, out: IO[str] = sys.stdout
) -> None:
    """Prints one `RENAME:` line per `rename_manifest` entry (old->new,
    dest-relative, both sides exactly as `_report_published_diff`'s own
    `NEW:`/`UPDATE:`/`REMOVE:` lines are), on the same stdout channel, so
    the sibling change-line parser in `percolate-round.py`
    (`_extract_change_lines`) can resolve a pathspec entry that is a
    rename SOURCE to its rename TARGET (§ that module's docstring, AC7's
    commit-pathspec provenance invariant, and the originating plan's C1/C2).

    `rename_manifest` is the `RenameManifest.as_records()` wire shape (a
    list of `{old_path, new_path, kind}` dicts, § `dispatch_percolate_
    post_rsync`'s docstring) — NOT the older flat `{old_path: new_path}`
    dict this used to accept. Each `RENAME:` line now carries its entry's
    `kind` as a `RENAME[directory]:` keyword PREFIX tag, printed only for a
    directory-kind entry — a file-kind entry's line is BYTE-IDENTICAL to
    what this printed before the wire carried `kind` at all, since `'file'`
    is both the default kind and the only kind that ever existed before
    directory renames did) so `percolate-round.py`'s own `_RENAME_LINE_RE`
    parser can reconstruct a real `RenameManifest` and call `.resolve()`
    instead of an exact-key dict lookup that can never match a path
    beneath a renamed directory (docs/plans/2026-08-14-publishing-runs-
    itself.md § C1 — the defect this fix closes).

    A no-op when `rename_manifest` is `None` or empty — a row with no
    renames must produce byte-identical output to today (§ the originating
    plan's C1 body). Never called under `--dry-run`: the dry-run leg never
    dispatches `dispatch_percolate_post_rsync`, so it never has a manifest
    to report, and inventing one there would resurrect the cried-wolf class
    docs/plans/2026-08-11-dry-run-cries-wolf-on-the-rename-exemption.md
    just closed.

    Spec backlink: pln-the-publish-round-commits-the-fa5df4
    § Tasks C1, Acceptance Criteria AC1.

    Review: coordinator:code-reviewer — the kind tag is printed as a
    `RENAME[directory]:` PREFIX, not a trailing ` [directory]` suffix on
    the path, because a suffix is a position a real `new_path` can occupy
    (a path literally ending in ` [directory]` would be misparsed as
    directory-kind) and a trailing tag is silently swallowed by an
    un-upgraded reader's old regex as part of the captured path. A prefix
    can never be forged by path content, and an old `_RENAME_LINE_RE`
    anchored on the bare `RENAME:` form simply fails to match a tagged line
    of corrupting the path it extracts. File-kind lines are unchanged
    (still bare `RENAME:`) to stay byte-identical to pre-existing output.

    publish.py and percolate-round.py are one wire contract for this
    tag and must be upgraded together in the same commit — an old
    percolate-round.py cannot parse a `RENAME[directory]:` line at all
    (it degrades to not-matching, never to a corrupted path; see
    `_RENAME_LINE_RE`'s own docstring note).
    """
    if not rename_manifest:
        return
    for entry in rename_manifest:
        old_rel, new_rel = entry["old_path"], entry["new_path"]
        kind = entry["kind"]
        tag = f"[{kind}]" if kind == "directory" else ""
        print(f"  RENAME{tag}: {old_rel} -> {new_rel}", file=out)


def _discard_publish_staging_dir(staging_dir: Optional[Path]) -> None:
    """Reclaims a staged publish row's staging directory on any abort path
    before the swap has landed (`staging_swapped` still False in
    `process_target`) — the real destination was never touched in that case,
    so there is nothing to reconcile, only this throwaway tree to remove.
    `.git` is never staged here (§ `_create_publish_staging_dir`), so this
    can never discard a repo's history — only its candidate content. Goes
    through `_rmtree_clear_readonly_onerror` for the same reason the
    cleanup-before-reraise path in `_create_publish_staging_dir` does: a
    Windows read-only attribute under a bare `ignore_errors=True` leaves the
    directory only partially removed instead of skipped past whole."""
    if staging_dir is not None:
        shutil.rmtree(staging_dir, onerror=_rmtree_clear_readonly_onerror)


def process_target(
    target: ResolvedTarget,
    setup_dir: Path,
    totals: RunTotals,
    *,
    identity_file_exists: bool,
    identity: Optional[PercolateIdentity],
    dry_run: bool,
    round_pinned_shas: "Optional[dict[str, str]]" = None,
    engine_ctx: PercolateEngineContext,
    percolate_store_path: Optional[Path] = None,
    publish_sync_module: object = None,
    shadow_roots_sink: "Optional[List[Path]]" = None,
    visited_files_sink: "Optional[set[Path]]" = None,
    published_dest_dirs_sink: "Optional[set[Path]]" = None,
    changed_files_sink: "Optional[set[Path]]" = None,
    changed_undetermined_sink: "Optional[set[Path]]" = None,
    removed_files_sink: "Optional[set[Path]]" = None,
    timing_sink: "Optional[List[tuple[str, str, float, float]]]" = None,
    out: IO[str] = sys.stdout,
) -> None:
    _bootstrap_engine()
    print(f"=== {target.name} ({target.mode}) ===", file=out)
    print(f"  Source: {target.source_dir}", file=out)
    print(f"  Target: {target.dest_dir}", file=out)

    # C3 (docs/dispatch-briefs .../C3.md): sweep prior-run orphans for THIS
    # destination unconditionally per row, before any of the early-return
    # gates below — a refused or skipped row must not leave cleanup for
    # `_sweep_stale_publish_staging_dirs` depending on some LATER row
    # reaching the staging-mint point. Moved out of the `else:` branch
    # further down (dry-run / engine-available gated) so a stale directory
    # from a prior killed/crashed run is reclaimed even when this row itself
    # never gets that far. `dry_run` is still threaded through to the sweep
    # itself so row-disposition independence and dry-run inertness both
    # hold: unconditional WHEN it runs, gated on WHETHER it removes.
    _sweep_stale_publish_staging_dirs(target.dest_dir, totals, dry_run=dry_run, out=out)

    for root in _contributing_roots(target):
        if not root.is_dir():
            print(f"  Error: source path does not exist: {root}", file=sys.stderr)
            print(f"  Skipping {target.name}.", file=out)
            print("", file=out)
            if timing_sink is not None:
                timing_sink.append((target.name, "REFUSED: source path absent", 0.0, 0.0))
            return

    with _time_phase(timing_sink, target.name, "run_pre_sync_gates"):
        gate_result = run_pre_sync_gates(
            target,
            setup_dir,
            identity_file_exists,
            identity,
            totals,
            dry_run=dry_run,
            round_pinned_shas=round_pinned_shas,
            out=out,
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
        if timing_sink is not None:
            timing_sink.append((target.name, "REFUSED: pre-sync gate declined", 0.0, 0.0))
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

    # C8 (declared-ref assertion) — MUST run before the one-shot bootstrap
    # just below (`repo-cut`'s bootstrap already writes to `target.dest_dir`)
    # and before every other write this function performs, per that helper's
    # own module comment.
    with _time_phase(timing_sink, target.name, "assert_dest_on_declared_ref"):
        declared_ref_ok = assert_dest_on_declared_ref(target, totals, out=out)
    if not declared_ref_ok:
        if timing_sink is not None:
            timing_sink.append((target.name, "REFUSED: dest not on declared ref", 0.0, 0.0))
        return

    # C10 (docs/plans/2026-08-15-klabauter-release-channels.md) — same
    # placement reasoning as C8 immediately above: before every write this
    # function performs, beside C8's refusal so the two share one shape
    # rather than growing two dialects.
    with _time_phase(timing_sink, target.name, "assert_dest_engine_root_viable"):
        engine_root_viable = assert_dest_engine_root_viable(
            target, totals, setup_dir=setup_dir, out=out
        )
    if not engine_root_viable:
        if timing_sink is not None:
            timing_sink.append((target.name, "REFUSED: dest engine root not viable", 0.0, 0.0))
        return

    try:
        # One-shot bootstrap (AC4/AC5/AC6) — runs strictly AHEAD
        # of `_ensure_dest_ready`, not inside it: that check refuses a
        # destination with no `.git` ancestor at all
        # (`_dest_has_git_ancestor`), so a virgin `repo-cut` destination must
        # already be a git repo by the time it runs, or it is rejected as an
        # unresolved destination rather than bootstrapped. Folding this into
        # `_ensure_dest_ready` itself would reopen the fabricate-a-tree-in-
        # the-wrong-place hole that function's own docstring documents.
        # AC11 (the row's SOURCE must be a committed git work tree) is
        # already enforced above by `run_pre_sync_gates`/`_git_materialize_ref`
        # (this function's own `gate_result` check, before this point) —
        # pre-existing engine behaviour, not duplicated here.
        mode_descriptor = descriptor_for(target.mode)
        if mode_descriptor is not None and mode_descriptor.is_bootstrap_bearing:
            if publish_sync_module is None:
                raise ProcessTargetCallerContractError(
                    "process_target: repo-cut target dispatched without a resolved "
                    "publish_sync_module — caller must resolve it once in main() before "
                    "the loop"
                )
            bootstrapped = publish_sync_module.sync_repo_cut(target.dest_dir, dry_run=dry_run)
            if bootstrapped:
                warn(
                    totals,
                    f"repo-cut: bootstrapped a virgin destination repo at {target.dest_dir}",
                    out=out,
                )

        with _time_phase(timing_sink, target.name, "_ensure_dest_ready"):
            dest_ready = _ensure_dest_ready(target, totals, out=out)
        if not dest_ready:
            if timing_sink is not None:
                timing_sink.append((target.name, "REFUSED: dest not ready", 0.0, 0.0))
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
        elif engine_ctx.engine_claude_klabauter is None or engine_ctx.store is None or percolate_store_path is None:
            print(
                f"  Error: percolate engine unavailable — refusing to publish {target.name} "
                "(AC15 fail-closed, see startup error above).",
                file=sys.stderr,
            )
            print(f"  Skipping {target.name}.", file=out)
            print("", file=out)
            if timing_sink is not None:
                timing_sink.append((target.name, "REFUSED: percolate engine unavailable", 0.0, 0.0))
            return
        else:
            try:
                with _time_phase(timing_sink, target.name, "dispatch_percolate_pre_rsync"):
                    dispatch_percolate_pre_rsync(engine_ctx, percolate_store_path, target)
                # C-W3 item 7 — the 2 standalone Shape E guard hooks (game-dev
                # source-dir-absent against SOURCE; prune-stale-handoff-cruft
                # against DEST, pre-sync timing) — see `dispatch_standalone_guards`.
                with _time_phase(timing_sink, target.name, "dispatch_standalone_guards"):
                    dispatch_standalone_guards(engine_ctx, target, effective_source_dir)
            except EngineUnavailableError as exc:
                print(f"  Error: {exc}", file=sys.stderr)
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: engine unavailable mid-row", 0.0, 0.0))
                return

            # Every phase from here through `dispatch_percolate_pre_ci` can
            # mutate a destination tree — reached only in this `else:` branch
            # (not dry-run, engine available), the same condition gating the
            # post_rsync/inject/pre_ci dispatch below. The prior-run orphan
            # sweep itself now runs unconditionally near the top of this
            # function (§ C3 comment there) — stage now, before the sync
            # dispatch, so the sync itself also lands on the staging copy
            # rather than the real destination.
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

        # Honest-report seam (task brief "make UPDATE: mean the published
        # bytes changed"): when a staging copy exists, the sync dispatch
        # below compares raw source bytes against a staging seed that
        # already carries the PRIOR run's post-transform output (§
        # `_create_publish_staging_dir`), so every transformed file
        # mismatches by construction regardless of whether published bytes
        # actually changed — see `_report_published_diff`'s docstring for
        # the full chain. Route that dispatch's counts/prints into a
        # throwaway sink in that case; the REAL report/counts come from
        # `_report_published_diff` below, computed AFTER the content-
        # transform sweep, immediately before the swap — the only point the
        # comparison is against what is actually about to publish. The
        # dry-run path (no staging_dir, no transform sweep ever runs) keeps
        # using the real `totals`/`out` unchanged — its raw-source-vs-live-
        # dest comparison is already honest, there being no transform to
        # cross.
        sync_totals = RunTotals() if staging_dir is not None else totals
        sync_out: IO[str] = io.StringIO() if staging_dir is not None else out

        # `row_sync_changed` (§ docs/plans/2026-08-16-percolate-round-timing-
        # and-changed-only.md chunk C4) — the sync layer's own copy/update
        # decisions (§ `dispatch_mirror_like`'s `changed_sink`), sourced ONLY
        # for a mirror-like row (the one mode this chunk captures, § its own
        # module comment). `None` for every other mode (manifest, repo-cut)
        # — undeterminable, not empty — so `dispatch_percolate_post_rsync`'s
        # `sync_changed_paths=None` correctly fails this row's changed-set
        # WIDE rather than narrowing it to "nothing" (§ that param's own
        # fail-wide contract).
        row_sync_changed: "Optional[set[str]]" = None

        if target.mode in mirror_like_wire_names():
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
            # directory-rename output, UNIONED with the target's STATIC
            # `basename_rename` section, BEFORE dispatching sync (state/audits/
            # 2026-08-05-first-full-payload-identity-findings.md Group E) --
            # this sync pass is about to recreate the pre-rename source
            # directory fresh, and this pass's own upcoming content-transform
            # sweep is about to rename it again, so the destination copy of
            # last pass's rename target must survive THIS sync's orphan
            # sweep rather than being deleted (or FATAL-aborting the whole
            # publish) as an apparent stray. The ledger alone is a CACHE that
            # is EMPTY on a fresh clone/machine -- exactly the case that needs
            # the exemption most, since the row can never write a ledger
            # without first surviving the FATAL its absence causes (docs/
            # plans/2026-08-12-publish-allowlist-acknowledges-imported-
            # modules.md). The static section is always present and needs no
            # prior run, so it is the authoritative member of the union; the
            # ledger still contributes any generation-specific entry the
            # static map itself does not (or no longer) declare. Preview and
            # real run MUST agree on this exemption set -- a dry run that
            # cannot see it reports a fatal a real run will never hit (docs/
            # plans/2026-08-11-dry-run-cries-wolf-on-the-rename-exemption.md).
            # Guarded on a live engine explicitly (never assumed from an
            # earlier return): `engine_ctx.engine_claude_klabauter is not None` is the
            # real check -- when the engine failed to import and this driver
            # degraded to a sync-only preview (§ `main`'s own
            # EngineUnavailableError/dry-run warning path), the engine root may
            # never have been placed on `sys.path` at all, and this module
            # import would raise instead of degrading gracefully, so the load
            # is defensive: an import failure, an unreadable ledger, or an
            # undeclared target falls back to today's pre-fix behaviour (empty
            # exemption set) rather than propagating. `mode == "mirror"` only
            # -- flat-mirror rows have no top-level orphan sweep this
            # exemption applies to. This never writes, creates, refreshes, or
            # reaps the ledger -- read-only, in preview and in a real run
            # alike.
            renamed_dir_names = None
            # The FILE-granular twin of `renamed_dir_names`, resolved from the same
            # ledger and the same static section in the same pass. Consumed by the
            # top-level orphan sweep (§ `publish_sync._sweep_mirror_top_level_
            # orphans`), which without it deletes every engine-renamed published
            # file as an orphan -- measured at 10 of 12 proposed deletions on the
            # first real preview of that sweep. Basenames, not rel-paths: the sweep
            # is top-level-only, where the two coincide, and `read_rename_ledger`
            # returns rel-paths for nested files this sweep never looks at.
            renamed_file_names = None
            mode_descriptor = descriptor_for(target.mode)
            if (
                mode_descriptor is not None
                and mode_descriptor.accepts_renamed_dir_names
                and engine_ctx.engine_claude_klabauter is not None
            ):
                try:
                    rewrite_basename_module = _import_percolate_rewrite_basename_module()
                    ledger = rewrite_basename_module.rename_ledger_path(target.name)
                    ledger_dir_names = frozenset(
                        rewrite_basename_module.read_directory_rename_ledger(ledger)
                    )
                    renamed_dir_names = ledger_dir_names
                    renamed_file_names = frozenset(
                        Path(rel).name
                        for rel in rewrite_basename_module.read_rename_ledger(ledger)
                    )
                    # The ledger alone is a CACHE, not a source of truth: it is
                    # empty on a fresh clone/machine where this row has never
                    # published successfully, which is exactly the case that
                    # needs the exemption most (state/audits/2026-08-05-first-
                    # full-payload-identity-findings.md Group E's deadlock —
                    # the row can never produce a ledger without first
                    # surviving the FATAL its own absence causes). The STATIC
                    # `basename_rename` section declared in the store is
                    # always present and needs no prior run, so it is unioned
                    # in as the authoritative source; the ledger still
                    # contributes any generation-specific entry the static
                    # map itself does not (or no longer) declare. Resolved in
                    # its OWN nested try — an undeclared `target.name` in
                    # `engine_ctx.store` (a caller that never wired a real
                    # store, e.g. a dry-run-only test double, or a target the
                    # store genuinely omits) must degrade to "no static
                    # contribution" WITHOUT discarding the ledger contribution
                    # already computed above; the outer `except` below would
                    # otherwise reset the whole set to `None` over a failure
                    # in a purely-additive second source. Deliberate contract:
                    # a malformed static entry is TOLERATED, not fatal -- one
                    # bad `basename_rename` pair degrades only the static
                    # contribution (this row falls back to ledger-only, same
                    # as before this diff existed) rather than aborting a
                    # real publish or discarding the ledger leg already
                    # resolved above. `KeyError` is `resolve_target`'s
                    # undeclared-target signal; `DirectoryRenamePairShapeError`
                    # (a `ValueError` subclass, `rewrite_basename.py`) is
                    # `declared_directory_dst_names`'s malformed-pair signal --
                    # both must land here, not the outer except, or a single
                    # bad static entry on a real (non-dry-run) publish wipes
                    # out an already-successfully-computed ledger exemption
                    # too (state/subagent-share/2c701e4a-e768-4812-9065-
                    # 16df98acc4c1/coordinatorcode-reviewer-eb5cf764.md P1).
                    try:
                        resolve_target_fn = _import_percolate_store_resolve_target()
                        section = resolve_target_fn(engine_ctx.store, target.name)
                        static_dir_names = rewrite_basename_module.declared_directory_dst_names(
                            section.get('basename_rename') or []
                        )
                        renamed_dir_names = ledger_dir_names | static_dir_names
                        renamed_file_names = renamed_file_names | (
                            rewrite_basename_module.declared_file_dst_names(
                                section.get('basename_rename') or []
                            )
                        )
                    except (
                        KeyError,
                        rewrite_basename_module.DirectoryRenamePairShapeError,
                    ):
                        pass
                # Review: coordinator:code-reviewer -- narrowed from a bare `except
                # Exception` (which silently swallowed a REAL-run failure, contrary to
                # the plan's AC3 byte-identity requirement). The catch set is deliberate,
                # not incidental, derived from what each of the calls in THIS outer try
                # can actually raise: `_import_percolate_rewrite_basename_module` fails
                # only with `ImportError` (its subclass `ModuleNotFoundError` included);
                # `rename_ledger_path` calls `consumer_state_home()`, whose only
                # documented failure mode is `Path.home()` raising `RuntimeError` when
                # the home directory can't be resolved; `read_directory_rename_ledger`
                # already swallows `(OSError, ValueError)` internally against the REAL
                # ledger reader and returns `[]`, so it structurally never raises those
                # here -- `OSError`/`ValueError` stay in this except anyway as
                # belt-and-suspenders against a future ledger-reader change, matching the
                # exact pair the callee itself treats as "degrade, don't raise". The inner
                # inner `except (KeyError, DirectoryRenamePairShapeError)` above is
                # deliberately its OWN narrower catch, not folded into this one: a
                # malformed or undeclared static entry must degrade the STATIC
                # contribution only, not wipe
                # out a ledger contribution this outer try already computed successfully
                # -- see that inner block's own comment, which explicitly catches
                # `declared_directory_dst_names`'s `DirectoryRenamePairShapeError` (a
                # `ValueError` subclass) alongside `KeyError` for exactly this reason --
                # it degrades the static leg only, never reaching this outer except.
                # Anything outside `(ImportError, OSError,
                # ValueError, RuntimeError)` propagates on both dry-run and real-run -- do
                # not re-broaden this to `Exception` without re-deriving the set from
                # every call site (outer AND inner).
                except (ImportError, OSError, ValueError, RuntimeError):
                    renamed_dir_names = None
            # A row that DECLARES a `basename_rename` previews its published
            # rename targets as REMOVE whenever the exemption did not resolve --
            # and that is true for every mirror-like mode, not only the ones
            # carrying `accepts_renamed_dir_names`. `flat-mirror` never enters
            # the exemption block above (its descriptor is
            # `accepts_renamed_dir_names=False` and `sync_flat_mirror` sweeps its
            # top-level files unconditionally), so `renamed_file_names` is
            # unconditionally None for it -- which gated this banner OFF for
            # exactly the rows that most need it. Measured on
            # `claude-klabauter-docs-install`, a flat-mirror row whose store
            # section declares `klabauter-agent-install-manifest.json ->
            # agent-install-manifest.json`: the preview prints `REMOVE:
            # agent-install-manifest.json (not in source)` for a file that IS in
            # source under its pre-rename name, with no banner to say so.
            # Keyed on the row's OWN declaration rather than on the mode flag so
            # a flat-mirror row with no rename map stays silent instead of
            # paying a banner it has no REMOVE lines to explain.
            declares_basename_rename = False
            if (
                dry_run
                and renamed_file_names is None
                and mode_descriptor is not None
                and mode_descriptor.is_mirror_like
            ):
                try:
                    _resolve_target_fn = _import_percolate_store_resolve_target()
                    declares_basename_rename = bool(
                        _resolve_target_fn(engine_ctx.store, target.name).get(
                            'basename_rename'
                        )
                    )
                # Same tolerated-degradation contract as the exemption block
                # above: an undeclared target, an absent or unwired store, or an
                # unimportable helper means "cannot tell whether this row
                # renames", which suppresses the banner rather than aborting a
                # preview over a purely explanatory line.
                except (ImportError, OSError, ValueError, RuntimeError, KeyError,
                        AttributeError, TypeError):
                    declares_basename_rename = False
            if should_warn_unresolved_rename_exemption(
                dry_run=dry_run,
                renamed_file_names=renamed_file_names,
                mode_descriptor=mode_descriptor,
                declares_basename_rename=declares_basename_rename,
            ):
                # Say it AT the output it explains, not only in the run-level engine
                # banner 200 lines up. With no exemption set, the sync preview below
                # reports every published rename target as `REMOVE: <published-name>
                # (not in source)` and re-adds it under its pre-rename source name --
                # which reads as the row's rename map running BACKWARDS, and was filed
                # as exactly that (state/bug-backlog/2026-08-26-publish-dry-run-wants-
                # to-un-rename-test-*.yaml) before anything connected the two. A real
                # run never does this: it refuses outright when the engine is
                # unavailable, and when the engine IS available the exemption resolves
                # and the transform pass renames what sync deposits. The plan this
                # requirement comes from names the contract directly -- preview and
                # real run MUST agree on the exemption set (docs/plans/2026-08-11-dry-
                # run-cries-wolf-on-the-rename-exemption.md); until they do, the
                # preview has to say which of the two it is showing.
                print(
                    "  Rename exemption: UNRESOLVED — this row's published rename "
                    "targets preview as REMOVE, their source names as NEW. Absent "
                    "exemption, not a failing rename map; a real run resolves it.",
                    file=out,
                )
            row_sync_changed = set()
            with _time_phase(timing_sink, target.name, "dispatch_mirror_like"):
                dispatch_mirror_like(
                    publish_sync_module,
                    sync_target,
                    effective_source_dir,
                    sync_totals,
                    dry_run=dry_run,
                    renamed_dir_names=renamed_dir_names,
                    out=sync_out,
                    changed_sink=row_sync_changed,
                    # `target`, deliberately, NOT `sync_target`: this asks where
                    # the row LANDS, and `sync_target.dest_dir` is the staging
                    # tree. A row whose destination is the mirror repo's own
                    # root shares that root with repo-owned files no row
                    # published (`README.md`, `LICENSE`, dotfiles), so its
                    # top-level files are never sweepable; a row projecting into
                    # a subdirectory owns every file directly under it.
                    #
                    # Fail-closed twice over, because both inputs have an
                    # undeterminable arm and a wrong answer here DELETES:
                    #
                    #   * `_dest_repo_root` returns None when no `.git` ancestor
                    #     is found at all -- "could not tell", never "not the
                    #     root", which is why `_dest_is_owned_subdir` exists
                    #     rather than a bare `!=` folded in here.
                    #   * `renamed_file_names` is None, not empty, whenever the
                    #     rename-exemption block above did not run -- most
                    #     commonly because the percolate engine is unavailable
                    #     (an unresolvable engine root, or an import that
                    #     raises). Empty and unknown are NOT the same: an empty
                    #     exemption means "no renames exist", while None means
                    #     "renames may exist and I cannot enumerate them", and
                    #     sweeping under None deletes every engine-renamed
                    #     published file. Observed live before this guard
                    #     existed -- an engine that failed to load was enough to
                    #     put 10 renamed files on the delete list.
                    #
                    # The cost of failing closed is one round that does not reap
                    # an orphan; the cost of failing open is deleting published
                    # files. Not symmetric, so this is not a tuning choice.
                    sweep_top_level_orphans=(
                        _dest_is_owned_subdir(target.dest_dir)
                        and renamed_file_names is not None
                    ),
                    renamed_file_names=renamed_file_names,
                )
        elif target.mode == "manifest":
            with _time_phase(timing_sink, target.name, "sync_manifest"):
                manifest_ok = sync_manifest(effective_source_dir, sync_target.dest_dir, sync_totals, dry_run=dry_run, out=sync_out)
            if not manifest_ok:
                _forward_sync_diagnostics(sync_out, out)
                totals.warnings += sync_totals.warnings
                totals.audit_files.extend(sync_totals.audit_files)
                print(f"  Skipping {target.name}.", file=out)
                print("", file=out)
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: manifest sync failed", 0.0, 0.0))
                return
        else:
            # `repo-cut` (and any future bootstrap-bearing mode) has no
            # payload sync of its own to dispatch here — its one-shot
            # bootstrap already ran above, ahead of `_ensure_dest_ready`
            # (AC4/AC5/AC6). Read `is_bootstrap_bearing` off the
            # descriptor rather than adding a `target.mode == "repo-cut"`
            # literal at this site (AC1) — a mode absent from the table
            # entirely (`mode_descriptor is None`) still falls through to
            # the unknown-mode error below.
            mode_descriptor = descriptor_for(target.mode)
            if mode_descriptor is None or not mode_descriptor.is_bootstrap_bearing:
                print(f"  Error: unknown mode '{target.mode}'", file=sys.stderr)
                print("", file=out)
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: unknown mode", 0.0, 0.0))
                return

        # Forward non-noise diagnostics (WARNING/Error lines — a genuinely
        # missing source file, a malformed manifest entry, etc.) from the
        # suppressed sync-dispatch pass into the real output/totals; the
        # `NEW:`/`UPDATE:`/`STRIP:`/`DELETE:`/`REMOVE:` report noise itself
        # is dropped here on purpose — `_report_published_diff` below is the
        # honest source for that. A no-op when `sync_out is out` (dry-run —
        # nothing was suppressed to begin with).
        if sync_out is not out:
            _forward_sync_diagnostics(sync_out, out)
            totals.warnings += sync_totals.warnings
            totals.audit_files.extend(sync_totals.audit_files)

        # post_rsync -> inject (separate, not phase-wired) -> pre_ci, in that
        # order (§ dispatch_percolate_inject docstring). Same dry-run skip as
        # the pre_rsync dispatch above.
        if not dry_run and engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None and percolate_store_path is not None:
            # `staging_dir` is guaranteed non-None here — the same condition
            # (not dry_run, engine available) is what created it above.
            # `row_visited` collects staged-path entries locally; they are
            # translated to real-destination paths and folded into the
            # caller's `visited_files_sink` below, AFTER the swap, so the
            # end-of-run unscanned-published check still sees real paths.
            row_visited: "set[Path]" = set()
            # `row_changed_files` (§ docs/plans/2026-08-16-percolate-round-
            # timing-and-changed-only.md chunk C4): the wire's `changed_files`
            # for this row's post_rsync phase, § `dispatch_percolate_post_
            # rsync`'s own return-value docstring. `None` (undeterminable) for
            # any row whose `row_sync_changed` above stayed `None`. Folded
            # into the caller's `changed_files_sink`/`changed_undetermined_
            # sink` below, AFTER the swap, same timing as `row_visited`.
            row_changed_files: "Optional[frozenset[str]]" = None
            try:
                with _time_phase(timing_sink, target.name, "dispatch_percolate_post_rsync"):
                    rename_manifest, row_changed_files = dispatch_percolate_post_rsync(
                        engine_ctx,
                        percolate_store_path,
                        sync_target,
                        effective_source_dir,
                        visited_sink=row_visited,
                        sync_changed_paths=row_sync_changed,
                    )
                with _time_phase(timing_sink, target.name, "dispatch_percolate_inject"):
                    inject_shadow_toplevels = dispatch_percolate_inject(
                        engine_ctx,
                        sync_target,
                        percolate_root=setup_dir.parent,
                        visited_sink=row_visited,
                        round_pinned_shas=round_pinned_shas,
                    )
                with _time_phase(timing_sink, target.name, "dispatch_percolate_pre_ci"):
                    dispatch_percolate_pre_ci(
                        engine_ctx,
                        percolate_store_path,
                        sync_target,
                        effective_source_dir,
                        rename_manifest,
                        identity_dest_dir=target.dest_dir,
                        percolate_root=setup_dir.parent,
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
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: engine unavailable in post_rsync/inject/pre_ci", 0.0, 0.0))
                # `staging_dir` is discarded by the `finally` block below
                # (`staging_swapped` stays False) — the real destination was
                # never touched by this row's sync, sweep, guards, or inject.
                return

            # INVARIANT: a path this row reports as written was actually
            # written this run, and a path not written is never reported as
            # written.
            #
            # The diff must be COMPUTED here, while `staging_dir` still holds
            # the transformed candidate and `target.dest_dir` still holds the
            # untouched prior tree — after the swap the two are identical and
            # there is no diff left to take. But it must not be EMITTED here:
            # the swap below is a partial-`os.rename` risk this module already
            # accepts (§ `_swap_publish_staging_into_dest`), and a raise there
            # leaves the destination unmutated. `main`'s per-row handler marks
            # the row FAILED, which does not retract bytes already written to
            # `out` — so emitting before the swap publishes an authoritative
            # `UPDATE:` line for a file on disk that never changed.
            #
            # Computing into a throwaway buffer and folding into the real
            # `out`/`totals` only after the swap returns keeps both halves.
            # The fold covers exactly the fields `_report_published_diff`
            # writes; widening that function's totals surface without widening
            # the fold below silently drops the new field on every row.
            report_buffer = io.StringIO()
            report_totals = RunTotals()
            with _time_phase(timing_sink, target.name, "_report_published_diff"):
                row_changed_files, row_removed_files = _report_published_diff(
                    staging_dir, target.dest_dir, report_totals, out=report_buffer
                )
            _report_rename_manifest(rename_manifest, out=report_buffer)
            with _time_phase(timing_sink, target.name, "dispatch_preswap_function_gate"):
                preswap_gate_ok = dispatch_preswap_function_gate(engine_ctx, target, staging_dir, out=out)
            if not preswap_gate_ok:
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: pre-swap function gate failed", 0.0, 0.0))
                return
            # RE-WIRED (chunk C5, state/dispatch-briefs/2026-08-26-payload-
            # parity-asks-an-index-not-the-payload/C5.md): the gate itself
            # never changed shape -- what changed is what it reads. The
            # 1250ms cost this call site was withdrawn for (§ git history,
            # commit 881d4a262) was the whole-payload rglob+read scan
            # `_files_referencing_needles` falls back to when
            # `token_index_path` is absent. C1-C4 built a persistent,
            # incrementally-maintained inverted index keyed on the row's
            # REPO ROOT (`coordinator_core.percolate.token_index`, on disk
            # at `<repo_root>/.percolate/token-index.bin` -- § C5 defect fix:
            # the writer, `_update_token_index_from_delta`, always keys and
            # locates the index at `_manifest_root`, a repo root, never a
            # row's own `dest_dir`, so the reader has to seek the same repo
            # root or it finds nothing for every non-toplevel row) that the
            # prescreen seeks into instead -- same index this round's own
            # end-of-run leg below (`_update_token_index_from_delta`) keeps
            # current. Passing its path through is what makes THIS call
            # cheap. Review: coordinator:code-reviewer (slice C, P3) -- the
            # gate is not merely "otherwise identical" to the one C2
            # shipped: this diff also adds degrade-to-full-scan semantics on
            # a `None`, unreadable, or unbuilt index, which C2 never had.
            # Review: coordinator:code-reviewer (slice C, P2) -- the two
            # lazy imports below used to sit ahead of any try/except, so an
            # ImportError here (packaging/OSS-shaped subprocess missing this
            # module -- the same hermetic-import concern
            # `dispatch_preswap_function_gate` already probes for) would
            # abort `process_target` with an uncaught exception instead of
            # refusing through the documented fail-closed path. Folding the
            # import into the same fail-closed boundary degrades to
            # `token_index_path=None` (full scan, per the gate's own
            # None-handling) on import failure, never an abort -- it does
            # NOT touch what happens on a genuine gate refusal.
            _row_token_index_repo_root = _dest_repo_root(target.dest_dir)
            _row_token_index_path: "Optional[Path]" = None
            if _row_token_index_repo_root is not None:
                try:
                    from coordinator_core.ops.percolate_build_token_index import (  # noqa: PLC0415 - lazy, this call site is the only user in process_target
                        _INDEX_DIRNAME as _row_token_index_dirname,
                    )
                    from coordinator_core.ops.percolate_build_token_index import (  # noqa: PLC0415
                        _INDEX_FILENAME as _row_token_index_filename,
                    )
                except ImportError:
                    _row_token_index_path = None
                else:
                    _row_token_index_path = (
                        _row_token_index_repo_root / _row_token_index_dirname / _row_token_index_filename
                    )
            with _time_phase(timing_sink, target.name, "dispatch_preswap_payload_parity_gate"):
                preswap_parity_ok = dispatch_preswap_payload_parity_gate(
                    target,
                    staging_dir,
                    row_changed_files,
                    token_index_path=_row_token_index_path,
                    out=out,
                )
            if not preswap_parity_ok:
                if timing_sink is not None:
                    timing_sink.append((target.name, "REFUSED: pre-swap payload parity gate failed", 0.0, 0.0))
                return
            try:
                with _time_phase(timing_sink, target.name, "_swap_publish_staging_into_dest"):
                    _swap_publish_staging_into_dest(target.dest_dir, staging_dir)
            except PublishSwapPartial as exc:
                # Do NOT swallow: re-raise either way so the row still marks
                # FAILED and the operator sees `exc`'s message. Whether to
                # record a swap depends on which of the two situations §
                # `PublishSwapPartial`'s docstring describes this is:
                if exc.content_swapped:
                    # Content DID land this run even though the row still
                    # fails overall — record exactly as the success path
                    # below does, so this stays honest to `process_target`'s
                    # stated invariant (a path reported as written was
                    # actually written this run).
                    staging_swapped = True
                    out.write(report_buffer.getvalue())
                    print(
                        f"  Warning: content published, but .git re-home failed — "
                        f"repo metadata stranded at {exc.prior_backup}: {exc}",
                        file=out,
                    )
                    totals.synced += report_totals.synced
                    totals.deleted += report_totals.deleted
                    if visited_files_sink is not None:
                        for staged_path in row_visited:
                            rel = staged_path.relative_to(staging_dir)
                            visited_files_sink.add(target.dest_dir / rel)
                    if row_changed_files is None:
                        if changed_undetermined_sink is not None:
                            changed_undetermined_sink.add(target.dest_dir)
                    elif changed_files_sink is not None:
                        for relative_id in row_changed_files:
                            changed_files_sink.add(target.dest_dir / relative_id)
                    if removed_files_sink is not None:
                        for relative_id in row_removed_files:
                            removed_files_sink.add(target.dest_dir / relative_id)
                    if published_dest_dirs_sink is not None:
                        published_dest_dirs_sink.add(target.dest_dir)
                else:
                    # Refused before touching this run's `dest_dir`/
                    # `staging_dir` at all — nothing to record, the throwaway
                    # `staging_dir` is reclaimed by the `finally` block below
                    # as on any other pre-swap abort.
                    print(f"  Error: {exc}", file=sys.stderr)
                raise
            staging_swapped = True
            out.write(report_buffer.getvalue())
            totals.synced += report_totals.synced
            totals.deleted += report_totals.deleted
            if visited_files_sink is not None:
                for staged_path in row_visited:
                    rel = staged_path.relative_to(staging_dir)
                    visited_files_sink.add(target.dest_dir / rel)
            # `row_changed_files` fold (§ docs/plans/2026-08-16-percolate-
            # round-timing-and-changed-only.md chunk C4) — `None` means this
            # row's changed-set is undeterminable (§ its own comment above),
            # recorded via `changed_undetermined_sink` so the caller's
            # per-repo-root aggregation fails WIDE (full sweep) for this
            # row's repo root rather than silently treating it as "changed
            # nothing".
            if row_changed_files is None:
                if changed_undetermined_sink is not None:
                    changed_undetermined_sink.add(target.dest_dir)
            elif changed_files_sink is not None:
                for relative_id in row_changed_files:
                    changed_files_sink.add(target.dest_dir / relative_id)
            # `row_removed_files` fold (chunk C3.5) — always determined once
            # `_report_published_diff` has run (unlike `row_changed_files`,
            # there is no undetermined state for the removed set here: this
            # comparison always runs before the swap on this path), so it
            # folds unconditionally, no undetermined-sink counterpart needed.
            if removed_files_sink is not None:
                for relative_id in row_removed_files:
                    removed_files_sink.add(target.dest_dir / relative_id)
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
        # module comment) — every early `return` above, and every exception
        # raised before the swap has landed, leaves `staging_swapped` False;
        # discard the throwaway staging copy in that case. This does NOT mean
        # the real destination is guaranteed untouched on every path anymore:
        # a `PublishSwapPartial` from `_swap_publish_staging_into_dest` sets
        # `staging_swapped = True` before re-raising precisely because the
        # content swap DID land in that case — only `.git`'s re-home failed.
        # A `None` `staging_dir` (dry-run, engine unavailable, or a `return`
        # before staging was ever created) is a no-op.
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
        help=(
            "Publish to one or more named targets only (comma-separated, e.g. "
            "'claude-klabauter,claude-klabauter-bin'; default: all resolved "
            "targets). Every named row is resolved and dispatched in this ONE "
            "invocation — the 4-tier target set and percolate store are each "
            "loaded once and reused across every matching row (task brief "
            "'Deliverable 1 — one invocation, all rows')."
        ),
    )
    p.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    p.add_argument(
        "--changed-only",
        action="store_true",
        default=True,
        help=(
            "Scope the end-of-run ENTRYPOINT gate (§ chunk C5) to entrypoints "
            "whose transitive first-party import closure actually reaches a "
            "file this run visited, plus an always-swept floor of entrypoints "
            "no changed set could ever select. DEFAULT ON (PM ruling, "
            "2026-08-15): the entrypoint gate runs --changed-only or --delta, "
            "never a full sweep, at the entrypoint gate. This flag is accepted "
            "for explicitness/back-compat; pass --full-sweep to opt out."
        ),
    )
    p.add_argument(
        "--full-sweep",
        action="store_true",
        help=(
            "Opt out of the --changed-only default (PM ruling, 2026-08-15) and "
            "sweep every shipped entrypoint every run, as every publish did "
            "before that default existed."
        ),
    )
    p.add_argument(
        "--full-audit",
        action="store_true",
        help="Reserved for the Phase-4 audit gate — accepted for CLI parity, not wired by this driver.",
    )
    p.add_argument(
        "--delta",
        action="store_true",
        default=True,
        help=(
            "DEFAULT ON (PM ruling 2026-08-19). Accepted for explicitness and "
            "back-compat; pass --no-delta to opt out. Skip whole rows this "
            "invocation can PROVE are unchanged since their last successful "
            "publish: the row's percolate store + transform-code signature, "
            "its source contributing-roots' committed HEAD sha, and its "
            "destination's committed HEAD sha all match the recorded "
            "last-publish record, AND the destination working tree is "
            "currently clean (no drift). A skipped row runs NO gates, sync, or "
            "engine phases this run — but the end-of-run "
            "identity/install-doc/unscanned-published checks still scan the "
            "FULL destination tree unconditionally, every run (this is a "
            "skip-WORK optimisation, never a skip-VERIFICATION one)."
        ),
    )
    p.add_argument(
        "--no-commit",
        dest="commit",
        action="store_false",
        default=True,
        help=(
            "Opt out of committing each destination repo at the successful "
            "conclusion of the percolation (default ON, PM ruling 2026-08-19). "
            "COMMIT ONLY — this driver never pushes a branch and never merges "
            "either way. Passed by `percolate-round`, which owns its own "
            "commit -> CI-smoke -> push sequence (DR-301); a bare "
            "`coordinator-publish` run wants the default, since exiting 0 with "
            "green gates and a dirty mirror is what makes the next round refuse "
            "on its dest-cleanliness precondition."
        ),
    )
    p.add_argument(
        "--no-delta",
        dest="delta",
        action="store_false",
        help=(
            "Opt out of the delta default and force a full row re-derivation. "
            "Verification is unconditional either way, so this only buys "
            "re-doing work a proof says is idle."
        ),
    )
    return p


def _modes_in_run_from_rows(rows: Sequence[str]) -> Optional[frozenset[str]]:
    """Field 2 of each row is its wire-name mode (§ the header grammar in
    `setup/publish-targets.portable`). A row this parse cannot read a mode
    off — malformed, or a mode absent from `PUBLISH_MODES` — collapses the
    scoping to `None`, i.e. back to checking the whole table: an
    unrecognised row is exactly when we do NOT know which entry points the
    run will reach, so the conservative form is the correct one there.
    `load_targets` validates the vocabulary downstream and fails loud on a
    genuinely bad mode; this parse only decides how wide the gate is.

    Review: coordinator:code-reviewer — a zero-pipe row was previously
    silently dropped from the set-builder instead of collapsing the result
    to `None`, diverging from this very docstring's stated "unrecognised
    row -> check the whole table" contract. Unparseable rows are now
    tracked explicitly so they force the fallback.
    """
    _bootstrap_engine()
    rows = list(rows)
    row_modes = {row.split("|")[1].strip() for row in rows if row.count("|") >= 1}
    has_unparseable_row = any(row.count("|") < 1 for row in rows)
    return (
        frozenset(row_modes)
        if row_modes
        and not has_unparseable_row
        and all(descriptor_for(mode) is not None for mode in row_modes)
        else None
    )


# ---------------------------------------------------------------------------
# Klabauter parity-group ordering invariant (2026-08-15, docs/plans/2026-08-15-
# bind-the-klabauter-publish-rows-into-a-parity-group.md, chunk C3). The eight
# `publish-mirror:claude_klabauter` rows in `setup/publish-targets.portable`
# split one argv contract across independently-landing rows: `claude-klabauter`
# (source `coordinator_core`) COMPOSES argv and hands it to the five
# entrypoint-carrying rows below, which PARSE it with strict
# `argparse.parse_args`. Each row stages then swaps independently, so a round
# is internally inconsistent for its whole duration; the direction of that
# window matters. A parser row landing ahead of an emitter that later adds a
# flag parses fine (harmless, for additions only); an emitter row landing
# ahead of its parser exits 2 before running (the 2026-08-15 live incident
# the plan's § Problem records). `setup/publish-targets.portable` therefore
# orders every entrypoint row BEFORE the emitter row; these two constants
# record that invariant so `main()` can refuse a table edited back into
# emitter-first order instead of silently reconstructing the bug.
#
# SCOPED TO ADDITIVE parser changes only — removals, renames, newly-
# `required=True` arguments, and tightened `choices` INVERT this ordering's
# safety and must be staged over two publish rounds instead (widen the
# parser, publish, THEN narrow the emitter). This constant and the assert
# below do not, and cannot, make those non-additive cases safe — they only
# enforce the row shape that keeps the additive case benign.
# ---------------------------------------------------------------------------
_KLABAUTER_PARITY_EMITTER_ROW = "claude-klabauter"
_KLABAUTER_PARITY_ENTRYPOINT_ROWS = (
    "claude-klabauter-bin",
    "claude-klabauter-scripts",
    "claude-klabauter-lib",
    "claude-klabauter-coordinator-lib",
    "claude-klabauter-coordinator-bin",
)


def _assert_klabauter_parity_group_ordering(rows: Sequence[str]) -> bool:
    """Pre-flight refusal (LOUD, not a warning): every row named in
    `_KLABAUTER_PARITY_ENTRYPOINT_ROWS` must publish before
    `_KLABAUTER_PARITY_EMITTER_ROW`. `rows` is the resolved row list
    `load_targets` returns, in the same file order `main()`'s publish loop
    iterates. Returns `False` — after printing a FATAL naming the violating
    row(s) to stderr — if the emitter's index is not strictly greater than
    every present entrypoint row's index; `True` otherwise. Never raises:
    `main()` folds this into its own `return 1` pre-sync-gate-decline path
    (§ `main`'s exit-code contract — this fires before any row has synced,
    so it is a declined pre-sync gate, not a post-publish verification
    failure, and must map to exit 1, not 2).

    A row named here that is simply ABSENT from `rows` (e.g. a `--target`
    subset that excludes it) is not a violation — this check only orders
    rows that are actually present in this run; it is not a completeness
    check on the parity group's membership.

    Why loud, not advisory: a violation means the table was edited into the
    exact shape the 2026-08-15 incident exhibited (emitter first, parser
    last) — this ordering exists specifically to prevent republishing that
    bug, so silently proceeding here would defeat the fix at the one point
    it can still catch a regression before it ships.

    `index_by_name` keeps only the LAST occurrence of a duplicated row name
    (dict comprehension, later key wins) — an accidental duplicate row name
    in the table would make this check blind to whichever occurrence sorts
    earlier. Not exploitable today: row names in `setup/publish-targets.
    portable` are unique, and that uniqueness is enforced elsewhere
    (`load_targets`/allowlist loading), not by this function. This check
    assumes, but does not itself verify, unique row names.
    """
    index_by_name = {row.split("|", 1)[0]: i for i, row in enumerate(rows)}
    emitter_index = index_by_name.get(_KLABAUTER_PARITY_EMITTER_ROW)
    if emitter_index is None:
        return True
    violations = [
        entrypoint_name
        for entrypoint_name in _KLABAUTER_PARITY_ENTRYPOINT_ROWS
        if entrypoint_name in index_by_name and index_by_name[entrypoint_name] > emitter_index
    ]
    if violations:
        print(
            "[publish.py] FATAL: klabauter parity-group ordering violated — "
            f"'{_KLABAUTER_PARITY_EMITTER_ROW}' (argv emitter) is ordered "
            f"before {', '.join(violations)} (argv parser row(s)) in "
            "setup/publish-targets.portable. The emitter must publish LAST "
            "among this parity group, after every entrypoint row, or a "
            "round can land a flag the parser side has not learned yet — "
            "the 2026-08-15 incident this ordering exists to prevent. Move "
            f"'{_KLABAUTER_PARITY_EMITTER_ROW}' below "
            f"{', '.join(_KLABAUTER_PARITY_ENTRYPOINT_ROWS)} in the table.",
            file=sys.stderr,
        )
        return False
    return True


def _walk_published_payload(published_dest_dirs: "Iterable[Path]") -> "set[Path]":
    """Every payload path on disk under THIS run's own published dest dirs —
    the widening that carries `declared_payload` past the percolation SCAN
    surface (`include_extensions`/`narrow_to_include_extensions`), which names
    only transform-eligible files and so omits a binary the row genuinely
    published. Measured witness: `coordinator_core/warm/door/door.exe` is
    tracked at the klabauter mirror's HEAD, sits inside a declared directory,
    and appears in no scan set.

    Path enumeration only — no content read, no per-path spawn, no `ast.parse`
    (§ `payload_parity`'s own 3.27s-against-a-500ms-ceiling anti-scope, binding
    here too).

    NEGATIVE SPEC — every prune below is load-bearing, none is tidiness:

    - `surface.STRUCTURAL_NEVER_PUBLISHED_PREFIXES` — `.git`, `.fleet-env` and
      kin: destination-repo plumbing, never publish-owned content. A
      flat-mirror row's `dest_dir` IS the mirror root (`LICENSE` and
      `.gitignore` sit in `declared_payload` today), so an unpruned walk names
      thousands of git objects as declared payload. `declared_payload` drives
      the ADD side of `percolate-round.py :: _pathspec_from_manifest`, so they
      reach the commit leg, which declines every one — and a non-empty
      `declined_paths` refuses the round's push outright (§
      `_round_refusal_reason`). Unpruned, this widening breaks every future
      round rather than merely costing a slow walk.

      A HAND-ROLLED `(".git", "__pycache__")` TUPLE STOOD HERE AND WAS NOT
      ENOUGH, measured on klabauter 2026-08-26: the first post-AC2 manifest
      carried 48,929 declared paths, of which **44,264 were `.fleet-env/`** —
      the multi-GB build tree the mirror's own `.gitignore` excludes. That is
      not merely bloat. `declared_payload` is SUBTRACTED from `row_scope` in
      the removal derivation, so over-declaring silently disables the removal
      side: the dry run reported 0 candidates while the same round warned that
      1 removal went uncarried. An over-wide declaration reads as a clean pass,
      which is the failure shape this whole deliverable exists to close.
      Reusing the SSOT — which already names `.fleet-env`, `.fleet-env.prior`,
      `.fleet-env.gen-*` and `.percolate` — is what makes the prune list
      unable to drift from the one every other walk in this system uses.
    - `surface.PUBLISH_STAGING_DIR_RE`: a crashed round's scratch, which no row
      declares. 1,028 files of one reached the public mirror in round
      `eebf1c67`; letting this walk re-declare one would reopen that incident
      through the back door.
    - `__pycache__`/`.pyc`/`.pyo`: generated locally AT the destination by
      anything that runs Python there, published by no row (§
      `publish_sync._is_structural_build_artifact`, same vocabulary).

    Each prune reuses the SSOT the rest of this system already walks on; none
    introduces a fresh exclusion vocabulary."""
    import fnmatch  # noqa: PLC0415 - lazy, this walk is the only user

    from coordinator_core.percolate.surface import (  # noqa: PLC0415 - lazy, this walk is the only user
        PUBLISH_STAGING_DIR_RE as _STAGING_DIR_RE,
    )
    from coordinator_core.percolate.surface import (  # noqa: PLC0415
        STRUCTURAL_NEVER_PUBLISHED_PREFIXES as _STRUCTURAL,
    )

    def _structural(name: str) -> bool:
        # The SSOT carries glob entries (`.fleet-env.gen-*`) beside literals,
        # so a plain membership test would let a generation directory through.
        return any(fnmatch.fnmatch(name, pattern) for pattern in _STRUCTURAL)

    found: "set[Path]" = set()
    for published_dir in published_dest_dirs:
        for walk_root, walk_dirs, walk_files in os.walk(published_dir):
            walk_dirs[:] = [
                d
                for d in walk_dirs
                if d != "__pycache__"
                and not _structural(d)
                and not _STAGING_DIR_RE.search(d)
            ]
            for walk_file in walk_files:
                if walk_file.endswith((".pyc", ".pyo")):
                    continue
                found.add(Path(walk_root) / walk_file)
    return found


def main(argv: Optional[List[str]] = None) -> int:
    """Exit-code contract (state/bug-backlog/2026-08-10-coordinator-publish-s-
    exit-code-is-not-a-542c9750e55a.yaml): a caller may trust the exit code
    alone to distinguish these four outcomes, without parsing the "Rows
    succeeded"/"Rows FAILED" summary or scanning stdout for FATAL text —

      0 — every requested row's bytes landed (or, under --dry-run, every row
          previewed cleanly) AND, on a real run, every end-of-run
          verification gate (identity/install-doc/unscanned-published/
          function/entrypoint) passed.
      1 — at least one row's bytes did NOT land (raised mid-row, or was
          declined by a pre-sync gate) — "Rows FAILED" names it. Fires under
          --dry-run too: a previewed row can fail its own preconditions
          (e.g. an allowlist-build failure) independently of --dry-run, and
          this driver must never claim success while reporting FAILED rows.
      2 — every requested row's bytes landed, but a POST-publish
          verification gate failed — distinct from 1 on purpose: this is
          "bytes landed, verification incomplete," never "bytes did not
          land." Never fires under --dry-run (those gates never run there).
      3 — every requested row's bytes landed AND every gate passed, but the
          end-of-run COMMIT of a destination repo did not complete (§
          `_commit_published_dests`). Distinct from 2 for the same reason 2
          is distinct from 1: the bytes are published and verified, and what
          is outstanding is only that the mirror is still dirty — the state
          the next `percolate-round` reads as a crashed predecessor. Never
          fires under --dry-run, nor under `--no-commit`.

    Previously (both directions confirmed live, see the bug-backlog entry):
    --dry-run unconditionally returned 0 even when rows were reported
    FAILED, and an end-of-run gate failure returned the same code (1) as a
    row failure, making the two indistinguishable from the exit code alone.
    """
    _bootstrap_engine()
    # Declare the publish lane first, for the same reason `percolate-round.py::main`
    # does and independently of it: this driver is also reached directly (via
    # `coordinator-publish`, a no-argument mixed-dest run), where no round has declared
    # the lane on its behalf. Its `_commit_published_dests` end-of-run leg reaches
    # `ceremony.scoped_git_commit` — exit code 3 above is precisely the outcome when
    # that commit does not complete, which is what the 2s cap and the suspension roster
    # produce for every publish. PM ruling 2026-08-21, DR-350.
    publish_lane.declare_lane()

    args = build_arg_parser().parse_args(argv)

    # § C1 (docs/plans/2026-08-16-percolate-round-timing-and-changed-only.md)
    # — round wall clock starts here, before any argv-driven work, so the
    # end-of-round "unattributed remainder" this chunk prints covers
    # everything `main()` itself does, not just the row loop.
    _round_wall_start = time.perf_counter()
    round_timings: "List[tuple[str, str, float]]" = []

    # Review: code-reviewer P2 — consume (pop, not just read) the inherited-
    # lock-roots token here, once, at the very top of `main()`, so it cannot
    # survive `os.environ` into any nested or second-order invocation this
    # process spawns (e.g. a future `publish.py` calling `publish.py`). The
    # captured value is threaded down to the lock loop below via
    # `_inherited_roots_token`; PID-binding/verification happens there.
    _inherited_roots_token = os.environ.pop(_INHERITED_LOCK_ROOTS_ENV, "")

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

    # Mirror-name/row-name collision resolution (task brief "publishing a
    # mirror must be ONE deterministic, idempotent operation covering EVERY
    # row"). A `publish-mirror:<key>` dest is composed of N rows in
    # `setup/publish-targets.portable`; naming any ONE of those rows bare
    # (no comma) used to publish that ONE row only and report success,
    # silently leaving the rest of the mirror stale — the live defect this
    # fixes (state/bug-backlog entries re: `claude-klabauter`). Naming more
    # than one target (comma-separated) is left exactly as-is — an explicit
    # multi-name request is already unambiguous and is never widened.
    # Resolution chosen deliberately: the bare name IS the whole mirror, not
    # "the row that happens to share the mirror's obvious name" — there is
    # no CLI-visible way to distinguish "the row" from "the mirror" by name
    # alone, so guessing wrong in either direction is unsafe; publishing the
    # superset (every row) is the only direction that can never leave the
    # mirror silently partial. A caller who really does need to touch a
    # single row for debugging still can — resolve_target/process_target
    # remain row-scoped internally — but this CLI's single-bare-name entry
    # point always means "this row's whole mirror."
    mirror_expansion: "Optional[tuple[str, str, List[str]]]" = None  # (mirror_key, requested_name, sibling_names)
    # Review: coordinator:code-reviewer -- a stray leading/trailing comma
    # (`"foo,"`, `",foo"`) is still an EXPLICIT comma-syntax request, not a
    # bare name, even though filtering empty segments collapses it to one
    # element -- `explicit_comma_syntax` preserves that signal so it is
    # never silently reinterpreted as "widen to the whole mirror."
    explicit_comma_syntax = "," in args.target if args.target else False
    solo_requested = [n.strip() for n in args.target.split(",") if n.strip()] if args.target else []
    if len(solo_requested) == 1 and not explicit_comma_syntax:
        sole_name = solo_requested[0]
        sigil_map = raw_dest_sigil_by_name(setup_dir)
        sigil = sigil_map.get(sole_name)
        if sigil and sigil.startswith("publish-mirror:"):
            siblings = sorted(n for n, s in sigil_map.items() if s == sigil)
            if len(siblings) > 1:
                mirror_key = sigil.split(":", 1)[1]
                mirror_expansion = (mirror_key, sole_name, siblings)
                print(
                    f"[publish.py] '{sole_name}' names ONE row of publish-mirror "
                    f"'{mirror_key}' ({len(siblings)} rows share this destination: "
                    f"{', '.join(siblings)}). Publishing the FULL mirror this run "
                    "— a bare row name always means its whole mirror; pass every "
                    "row you want explicitly, comma-separated, to publish a strict "
                    "subset.",
                    file=sys.stdout,
                )
                args.target = ",".join(siblings)

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
    # `args.target` may name more than one row, comma-separated (§
    # `build_arg_parser`'s help text, task brief "Deliverable 1"). Every
    # requested name is validated here so a typo'd/absent name among a
    # multi-name request fails loud up front, same as the pre-existing
    # single-name contract, rather than silently processing the subset
    # that did resolve.
    requested_names = [n.strip() for n in args.target.split(",") if n.strip()] if args.target else []
    if requested_names:
        resolved_names = sorted({row.split("|", 1)[0] for row in rows})
        missing_names = [n for n in requested_names if n not in resolved_names]
        if missing_names:
            print(
                f"[publish.py] FATAL: requested target(s) {', '.join(missing_names)!r} "
                f"not found under PERCOLATE_ROOT {percolate_root} (resolved via rung "
                f"{percolate_root_rung!r}). Targets present: "
                f"{', '.join(resolved_names) if resolved_names else '(none)'}.",
                file=sys.stderr,
            )
            return 1

    # Klabauter parity-group ordering pre-flight (C3): refuse loudly before any
    # row publishes if the table has been edited back into emitter-first order.
    # See `_assert_klabauter_parity_group_ordering`'s own docstring for why
    # this is a declined pre-sync gate (exit 1), not a post-publish
    # verification failure (exit 2) — no row has synced yet at this point.
    if not _assert_klabauter_parity_group_ordering(rows):
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
    engine_ctx = PercolateEngineContext(engine_claude_klabauter=None, store=None)
    try:
        claude_klabauter_pct = _import_claude_klabauter_percolate()
        store = assert_percolate_store_ready(claude_klabauter_pct, percolate_store_path)
        engine_ctx = PercolateEngineContext(engine_claude_klabauter=claude_klabauter_pct, store=store)
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

    modes_in_run = _modes_in_run_from_rows(rows)

    try:
        check_publish_sync_contract(
            publish_sync_module,
            publish_sync_module_path,
            percolate_root_rung,
            modes_in_run=modes_in_run,
        )
    except PublishSyncContractError as exc:
        print(exc.message, file=sys.stderr)
        return 1

    totals = RunTotals()

    # --delta (task brief "Deliverable 2"): computed ONCE, before the target
    # loop, exactly like `engine_ctx`/`publish_sync_module` above — every
    # row's skip decision below reuses this same signature. Disabled
    # (`delta_active = False`) under `--dry-run` (a preview run has nothing
    # to gain from skipping — it never writes) or when the engine is
    # unavailable (§ `compute_delta_invalidation_signature`'s
    # engine-unresolvable fail-safe would make every row's signature check
    # fail anyway, so skip the wasted hashing work and say so plainly).
    delta_active = args.delta and not args.dry_run and engine_ctx.engine_claude_klabauter is not None
    delta_signature: Optional[str] = None
    if args.delta and not delta_active:
        print(
            "publish.py: --delta requested but inactive this run "
            f"({'dry-run preview' if args.dry_run else 'percolate engine unavailable'}) "
            "— every row will be processed in full.",
            file=sys.stderr,
        )
    elif delta_active:
        delta_signature = compute_delta_invalidation_signature(percolate_store_path, engine_ctx)

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
    # C-round-scan attribution (§ `_attribute_identity_findings`) — every
    # row this invocation reached, grouped by the same repo-root key
    # `end_of_run_check_roots` uses, so a failing end-of-run identity
    # finding can be mapped back to the row whose `dest_subdir` it falls
    # under. Populated in lockstep with `end_of_run_check_roots` below
    # (including a `--delta`-skipped row — `skipped_row_names` is what lets
    # the attribution distinguish "this row published the finding this run"
    # from "the finding pre-exists in this row's subtree, untouched").
    end_of_run_rows_by_repo_root: "dict[Path, List[ResolvedTarget]]" = {}
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
    # § `dispatch_end_of_run_entrypoint_gate` chunk C4 (docs/plans/2026-08-16-
    # percolate-round-timing-and-changed-only.md) — the real CHANGED-set (not
    # a read-set, § `end_of_run_visited_by_repo_root` above) this run's rows
    # actually wrote at the destination, keyed the same way. Unioned in below
    # from `process_target`'s `changed_files_sink`. `end_of_run_changed_
    # undetermined_roots` names every repo root with at least one row whose
    # changed-set could not be determined this run (§ `process_target`'s
    # `changed_undetermined_sink`) — the gate must fail WIDE (full sweep) for
    # any such root, never narrow to the partial union already accumulated.
    end_of_run_changed_by_repo_root: "dict[Path, set[Path]]" = {}
    end_of_run_changed_undetermined_roots: "set[Path]" = set()
    # § chunk C4 (state/dispatch-briefs/2026-08-26-payload-parity-asks-an-
    # index-not-the-payload/C4.md, AC8) — a repo root with a row that raised
    # `PublishSwapPartial(content_swapped=True)` (content DID land at dest,
    # but the row still marks FAILED and never reaches the `end_of_run_
    # changed_by_repo_root` fold below, since the exception is re-raised and
    # caught by the row-isolation handler before that fold runs). Left alone,
    # the token index would keep a stale-but-covered stamp for exactly the
    # files this row just changed at dest — worse than absent (§ that
    # module's own negative-spec). Routed through the same single
    # "invalidate this root" call as an undetermined root, per AC8.
    end_of_run_token_index_invalidate_roots: "set[Path]" = set()
    # § chunk C3.5 (docs/plans/2026-08-23-rebuild-the-percolate-round-as-six-
    # steps.md) — this run's own removed-paths accounting, keyed the same way
    # as `end_of_run_changed_by_repo_root`, folded from `process_target`'s
    # `removed_files_sink`. Unlike the changed-set there is no undetermined
    # state to track for removals (§ `process_target`'s `row_removed_files`
    # fold comment) — `_report_published_diff` always determines this set on
    # any row that reaches the swap. Consumed at the end of this run to
    # persist one `RoundManifest` per repo root (§ `write_manifest` call
    # below), the manifest a committer reads instead of scraping this
    # driver's own printed `NEW:`/`UPDATE:`/`REMOVE:` report.
    end_of_run_removed_by_repo_root: "dict[Path, set[Path]]" = {}
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
    # Per-row outcome ledger (mid-first-row publish-run death fix) —
    # `process_target` can raise `SystemExit` from deep inside a dispatched
    # sync (e.g. `publish_sync.py`'s orphan-sweep top-level-presence FATAL,
    # `raise SystemExit(3)`), which is a `BaseException`, not an `Exception`
    # — it sails past any bare `except Exception` and, uncaught here, unwinds
    # straight out of this whole loop and out of `main()`, killing every
    # remaining requested row silently (no traceback, no "Done." summary,
    # whatever real exit code the raise carries). Catching it (and any other
    # per-row exception) at THIS scope — around the `process_target` call,
    # not around the whole loop — turns "one row's fatal guard kills the
    # entire run" into "one row fails, is reported, and the run continues to
    # the rows after it," matching every other row-scoped failure path in
    # this loop (gate failures, `EngineUnavailableError`, etc. all already
    # `return` from inside `process_target` without raising). Excludes
    # `KeyboardInterrupt`/`GeneratorExit` deliberately — those are not row
    # failures, they are "stop everything now."
    succeeded_row_names: "List[str]" = []
    failed_row_names: "List[str]" = []
    # `--delta` whole-row skips (§ below) land here, never in
    # `succeeded_row_names` or `failed_row_names` — a skip is neither. Tracked
    # separately so the end-of-run summary can say so instead of leaving
    # "Rows succeeded: 0/1" to read as the exact shape of the exit-code defect
    # `test_publish_skipped_row_not_counted_succeeded.py` pins (state/bug-
    # backlog/2026-08-10-a-delta-skipped-row-reports-rows-succeed-8806cf839322.yaml).
    skipped_row_names: "List[str]" = []
    # Part B (concurrent-publish guard) — state/handoffs/2026-08-07-percolate-
    # performance-delta-sweep.md. A per-destination advisory lock held for the
    # WHOLE row loop (not per-row), keyed on the resolved destination repo
    # root, acquired up front for every distinct root this invocation's
    # (post --target-filter) rows resolve to — a second concurrent publish
    # targeting an overlapping destination set fails loud before touching any
    # file, not partway through the loop. --dry-run never mutates a
    # destination (process_target skips every phase that would), so it never
    # takes the lock — which means a --dry-run's read can race a concurrent
    # real publish mutating that same destination mid-read, and its report
    # does not necessarily correspond to any single consistent on-disk state
    # before or after that publish. Accepted read-only tradeoff (Review:
    # code-reviewer P3) — a dry-run is advisory, not a commitment, and taking
    # a real lock for it would let a --dry-run block a real, mutating
    # publish, which is the wrong direction of contention.
    #
    # Review: code-reviewer P3 — locks are acquired up front for the WHOLE
    # declared row set, including rows `--delta` will later whole-row-skip
    # (see the `continue` below). A concurrent unrelated writer to a root
    # this run ends up delta-skipping is still blocked against that root for
    # this run's full duration even though this run never touches it.
    # Accepted: over-broad is the safe direction (never under-locks), and the
    # set of distinct destination roots is known only after resolving every
    # row up front, before any row's delta status is evaluated.
    from contextlib import ExitStack

    from coordinator_core.locked_write import (  # type: ignore[import-not-found]
        LockTimeout as _PublishLockTimeout,
        held_lock as _publish_held_lock,
    )
    from percolate.wire_contract import (  # type: ignore[import-not-found]
        lock_busy_message as _lock_busy_message,
        publish_contention_wait_secs as _publish_lock_wait_secs,
    )

    # Review: code-reviewer P3 — parse each row exactly once and reuse the
    # result in the main loop below, rather than parsing it again there.
    # Previously `parse_target_row` ran once here and a second time per-row
    # in the main loop, which cost nothing correctness-wise (a malformed row
    # already raised unguarded in both places, pre- and post-diff) but made
    # the equivalence something a reader had to diff-trace rather than see
    # structurally.
    parsed_rows: "dict[str, ResolvedTarget]" = {row: parse_target_row(row) for row in rows}

    # Round-wide source-sha pin (docs/plans/2026-08-04-publish-from-a-
    # committed-ref.md C1b amendment) — resolved HERE, once per contributing
    # root's git toplevel, before any row's gates or materialization run, so
    # every row in THIS round reads the same commit for a shared toplevel
    # even if HEAD moves mid-round (measured: four distinct SHAs materialized
    # across one round on this box, from peer commits landing mid-round).
    # `round_pinned_shas` is threaded through every `process_target` call
    # below and read by `run_pre_sync_gates` via `_round_pin_source_sha`,
    # which is idempotent — this pass and any row's later use of the same
    # toplevel agree on one sha. A root that fails to resolve here (not a
    # git work tree, or HEAD unresolvable) is deliberately left unpinned
    # rather than aborting the whole round: `run_pre_sync_gates` hits the
    # identical failure lazily (`late=True`) when that specific row is
    # processed, and its existing per-row GitMaterializeError handling skips
    # just that row — the same outcome a pre-round hard failure would have
    # forced on every OTHER row too.
    round_pinned_shas: "dict[str, str]" = {}
    for row in rows:
        candidate = parsed_rows[row]
        if requested_names and candidate.name not in requested_names:
            continue
        for root in _contributing_roots(candidate):
            try:
                _round_pin_source_sha(root, round_pinned_shas, out=sys.stdout, late=False)
            except GitMaterializeError as exc:
                print(
                    f"[publish.py] WARNING: could not pin a round source sha for {root} "
                    f"at round start ({exc}); {candidate.name} will retry (and skip on "
                    "failure) when its own gates run.",
                    file=sys.stderr,
                )

    lock_repo_roots: "List[Path]" = []
    if not args.dry_run:
        for row in rows:
            candidate = parsed_rows[row]
            if requested_names and candidate.name not in requested_names:
                continue
            root = _dest_repo_root(candidate.dest_dir) or candidate.dest_dir
            if root not in lock_repo_roots:
                lock_repo_roots.append(root)
        # Review: code-reviewer P2 — sort by realpath so every invocation
        # acquires locks in one canonical global order. Without this, two
        # legitimately non-overlapping-row-order concurrent publishes (e.g.
        # run A over [repoX, repoY], run B over [repoY, repoX]) can each grab
        # one root and then contend on the other's — a livelock-shaped
        # failure (timeout-bounded, not a true wedge, but both runs can fail
        # with "another publish is running against it" when neither actually
        # is stuck).
        lock_repo_roots.sort(key=lambda p: os.path.realpath(str(p)))

    # No anchor is passed: `held_lock` derives the sidecar directory from its
    # per-user, per-machine rendezvous (`_machine_lock_dir`), which is what
    # makes two publishes running from two DIFFERENT installs of this engine
    # against one destination mutually exclusive. The lock KEY still derives
    # solely from `_lock_root` (§ `_lock_key`).
    # Passing `_lock_root` as the anchor — as this call once did —
    # is now a `LockAnchorError`: it put an open, locked file handle inside
    # `<destination>/.git/coordinator-locks/` for the whole run, and `.git`
    # cannot be renamed while a handle inside it is open, so every publish hit
    # a deterministic (not antivirus-race) `PermissionError` in
    # `_swap_publish_staging_into_dest`.
    # D1 fix — inherited-holder handoff. `percolate-round.py` spans its OWN
    # `held_lock(dest)` across the whole Step 4 real-run subprocess (a
    # deliberate widening, see its own module docstring) and passes the
    # resolved-realpath root(s) it already holds via
    # `PERCOLATE_ROUND_INHERITED_LOCK_ROOTS` (`os.pathsep`-joined absolute
    # `os.path.realpath` paths) in THIS process's env. `held_lock`'s key is
    # `sha1(os.path.realpath(target))` (`_lock_key`) — re-opening that same
    # key from a fresh `os.open` in this child process blocks against the
    # parent's still-open flock (flock is per-open-file-description, not
    # per-process) until `LOCK_TIMEOUT_SECS`, which is exactly the D1
    # deadlock this skip prevents. Only a root whose OWN realpath matches an
    # inherited entry is skipped — every other root in `lock_repo_roots`
    # (e.g. a sibling row's destination this same run also touches) is
    # still acquired below, same as before this fix.
    # Review: code-reviewer P2 — the skip is only honoured when the entry's
    # PID matches this process's TRUE parent (`os.getppid()`); a malformed
    # entry (no `=`, non-integer PID) or a PID mismatch (stray exported
    # value, a nested/second-order invocation) is fail-closed — that root is
    # NOT added to `_inherited_lock_realpaths`, so it acquires the lock
    # below exactly as if no token were present at all.
    _inherited_roots_raw = _inherited_roots_token
    _inherited_lock_realpaths: "set[str]" = set()
    _true_parent_pid = os.getppid()
    for _entry in _inherited_roots_raw.split(os.pathsep):
        if not _entry:
            continue
        _pid_str, _sep, _path = _entry.partition("=")
        if not _sep:
            continue  # malformed — no `=` delimiter; fail closed (still locks)
        try:
            _entry_pid = int(_pid_str)
        except ValueError:
            continue  # malformed — non-integer PID; fail closed (still locks)
        if _entry_pid != _true_parent_pid:
            continue  # PID mismatch — not from the true parent; fail closed (still locks)
        _inherited_lock_realpaths.add(os.path.realpath(_path))

    publish_lock_stack = ExitStack()
    for _lock_root in lock_repo_roots:
        if os.path.realpath(str(_lock_root)) in _inherited_lock_realpaths:
            # Review: code-reviewer P2 -- a stray env var (e.g. left exported in a
            # debugging shell) would silently skip this root's lock with no signal.
            print(
                f"[publish.py] skipping lock for {_lock_root}: inherited from parent per-invocation env",
                file=sys.stderr,
            )
            continue
        try:
            publish_lock_stack.enter_context(
                _publish_held_lock(
                    _lock_root,
                    holder_label=str(_lock_root),
                    timeout=_publish_lock_wait_secs(),
                )
            )
        except _PublishLockTimeout as exc:
            publish_lock_stack.close()
            # Not FATAL and not exit 1: a held destination lock is a queue,
            # not a defect (`percolate.wire_contract.lock_busy_message`
            # carries the same distinction on its side of the seam, shared
            # verbatim with `percolate-round.py`/`percolate-mirror.py`).
            # Exit 75 is EX_TEMPFAIL, so a caller can tell "a peer is
            # mid-publish" from "this publish is broken" without parsing
            # stderr. Refuses on the FIRST contended root in
            # `lock_repo_roots`' canonical sorted order — a multi-row
            # publish never flattens a per-row refusal into a generic FAIL.
            print(
                f"[publish.py] BUSY: {_lock_busy_message(str(_lock_root), exc)}",
                file=sys.stderr,
            )
            return 75

    try:
        try:
            for row in rows:
                target = parsed_rows[row]
                if requested_names and target.name not in requested_names:
                    continue
                repo_root = _dest_repo_root(target.dest_dir) or target.dest_dir
                end_of_run_check_roots.append(repo_root)
                end_of_run_rows_by_repo_root.setdefault(repo_root, []).append(target)
                if engine_ctx.engine_claude_klabauter is not None and engine_ctx.store is not None:
                    try:
                        section = engine_ctx.engine_claude_klabauter.resolve_target(engine_ctx.store, target.name)
                        end_of_run_row_sections.append((target, section))
                    except KeyError:
                        pass  # unresolvable target already surfaces via process_target's own dispatch below
                row_visited: "set[Path]" = set()
                row_published_dest_dirs: "set[Path]" = set()
                row_changed: "set[Path]" = set()
                row_changed_undetermined: "set[Path]" = set()
                row_removed: "set[Path]" = set()

                # --delta whole-row skip (task brief "Deliverable 2") — a skip
                # here runs NO gates, sync, or engine phases for this row; it
                # does NOT touch `end_of_run_check_roots` (already appended
                # above, unconditionally — the end-of-run identity/install-doc
                # checks still scan this repo root's FULL tree regardless), and
                # deliberately leaves `row_visited`/`row_published_dest_dirs`
                # empty, matching a row this run never reached (§
                # `dispatch_end_of_run_unscanned_published_check`'s
                # `published_dest_dirs_by_repo_root` scoping — a skipped row
                # published nothing THIS run, so it is correctly out of scope
                # for that check's verdict too).
                if delta_active and delta_signature is not None and delta_row_unchanged(
                    setup_dir, target, delta_signature, round_pinned_shas
                ):
                    print(f"=== {target.name} ({target.mode}) ===", file=sys.stdout)
                    if target.mode in mirror_like_wire_names():
                        print(
                            "  --delta: unchanged since last publish (store+transform "
                            "signature, source HEAD, destination HEAD all match; "
                            "clean-tree check does not apply to mirror-mode rows) — "
                            "skipping.",
                            file=sys.stdout,
                        )
                    else:
                        print(
                            "  --delta: unchanged since last publish (store+transform "
                            "signature, source HEAD, destination HEAD all match, "
                            "destination tree clean) — skipping.",
                            file=sys.stdout,
                        )
                    print("", file=sys.stdout)
                    skipped_row_names.append(target.name)
                    continue

                prev_processed = totals.processed
                try:
                    process_target(
                        target,
                        setup_dir,
                        totals,
                        identity_file_exists=identity_file_exists,
                        identity=identity,
                        dry_run=args.dry_run,
                        round_pinned_shas=round_pinned_shas,
                        engine_ctx=engine_ctx,
                        percolate_store_path=percolate_store_path,
                        publish_sync_module=publish_sync_module,
                        shadow_roots_sink=all_shadow_roots,
                        visited_files_sink=row_visited,
                        published_dest_dirs_sink=row_published_dest_dirs,
                        changed_files_sink=row_changed,
                        changed_undetermined_sink=row_changed_undetermined,
                        removed_files_sink=row_removed,
                        timing_sink=round_timings,
                    )
                except (SystemExit, Exception) as exc:  # noqa: BLE001 - row isolation, see ledger comment above
                    # § chunk C4 (AC8) — `content_swapped=True` means dest was
                    # actually mutated by this row before the raise; this row's
                    # own changed-set never reaches the fold below (the raise
                    # happens before it), so the token index for this root must
                    # be invalidated rather than left stale-but-covered.
                    if isinstance(exc, PublishSwapPartial) and exc.content_swapped:
                        end_of_run_token_index_invalidate_roots.add(repo_root)
                    code = getattr(exc, "code", None)
                    # `OSError.__repr__` (what `{exc!r}` prints) emits only
                    # `(errno, strerror)` — it discards `.filename`/
                    # `.filename2`/`.winerror`, the very attributes
                    # `os.rename`/`os.replace` populate and that name the
                    # actual path(s) a sharing-violation/permission failure
                    # hit. Surfacing them here is what let this defect
                    # (`claude-klabauter-publish-repo-toplevel`'s root-dest
                    # rename, WinError 32) be diagnosed from the FATAL line
                    # alone instead of a dispatched investigation.
                    filename = getattr(exc, "filename", None)
                    filename2 = getattr(exc, "filename2", None)
                    winerror = getattr(exc, "winerror", None)
                    path_detail = ""
                    if filename is not None or filename2 is not None or winerror is not None:
                        path_detail = (
                            f" [filename={filename!r}, filename2={filename2!r}, "
                            f"winerror={winerror!r}]"
                        )
                    print(
                        f"  FATAL: {target.name} aborted mid-row ({exc!r}, code={code!r}"
                        f"{path_detail}) — "
                        "marking this row FAILED and continuing with the remaining "
                        "requested rows (a single row's fatal guard must not silently "
                        "take the rest of the run with it).",
                        file=sys.stderr,
                    )
                    print("", file=sys.stdout)
                    failed_row_names.append(target.name)
                    continue
                # `process_target` returns `None` on BOTH its success path and
                # every gate-declined-this-row path (allowlist build failure,
                # dest-not-ready, engine unavailable, etc.) — none of those
                # raise, they print their own "skipping" line and `return`
                # early. The only on-disk signal that this row actually
                # completed a publish is `totals.processed` having advanced
                # (incremented once, at the very end of `process_target`'s
                # success path, right before staging normally exits). Treating
                # "did not raise" as "succeeded" counted a skipped row in
                # "Rows succeeded", which also let the succeeded-count disagree
                # with `totals.processed`'s own tally on the summary line.
                if totals.processed == prev_processed:
                    failed_row_names.append(target.name)
                    continue
                succeeded_row_names.append(target.name)
                end_of_run_visited_by_repo_root.setdefault(repo_root, set()).update(row_visited)
                end_of_run_published_dest_dirs_by_repo_root.setdefault(repo_root, set()).update(
                    row_published_dest_dirs
                )
                end_of_run_changed_by_repo_root.setdefault(repo_root, set()).update(row_changed)
                if row_changed_undetermined:
                    end_of_run_changed_undetermined_roots.add(repo_root)
                end_of_run_removed_by_repo_root.setdefault(repo_root, set()).update(row_removed)

                # Record this row's new delta state ONLY after a verified
                # successful publish (`totals.processed` incremented — §
                # `process_target`'s success path). A failed/skipped-by-gate
                # row must never record a delta record — an unrecorded row
                # always falls through to the full path next time, which is
                # the safe direction.
                if delta_active and delta_signature is not None and totals.processed > prev_processed:
                    post_source_sha = _delta_row_source_sha(target, round_pinned_shas)
                    post_dest_head = (
                        _git_head(target.dest_dir) if _is_git_repo(target.dest_dir) else ""
                    )
                    if post_source_sha is not None and post_dest_head:
                        write_delta_record(
                            setup_dir,
                            target.name,
                            signature=delta_signature,
                            source_sha=post_source_sha,
                            dest_head=post_dest_head,
                        )
        finally:
            _cleanup_shadow_roots(tuple(dict.fromkeys(all_shadow_roots)))

        # Publish provenance record (docs/plans/2026-08-19-the-published-
        # engine-says-what-it-was-published-from.md C1) — after shadow-root
        # cleanup, alongside the row-outcome tallies this same block already
        # computed. Never under --dry-run: nothing landed to record
        # provenance for, and the round's row lists above are advisory only
        # in that mode.
        if not args.dry_run:
            write_publish_provenance_record(
                succeeded_row_names=succeeded_row_names,
                failed_row_names=failed_row_names,
                skipped_row_names=skipped_row_names,
                rows_by_name={t.name: t for t in parsed_rows.values()},
                round_pinned_shas=round_pinned_shas,
            )

        print("===============================")
        if mirror_expansion is not None:
            mirror_key, requested_row_name, sibling_names = mirror_expansion
            print(
                f"Mirror publish: '{mirror_key}' ({len(sibling_names)} rows, "
                f"requested via row name '{requested_row_name}')."
            )
        # HEADLINE STATES THE VERDICT, not just the count. A bare "Done. N
        # target(s) processed." reads as success to both a human skimming and
        # a log scanner, even on a run where a row fail-closed -- the row
        # detail sat 4 lines further down under "Rows FAILED". Measured cost
        # of that shape (2026-08-30): the claude-klabauter toplevel row had
        # been refusing its payload parity gate since 810d64a1a1 -- the
        # creating commit of the test whose call was always-red -- while the
        # other 9 rows succeeded every round. Nothing looked broken, the
        # mirror silently stopped committing, and every fix synced into it
        # stranded unpublished for as long as it took someone to read past
        # the headline. Three separate rows fail-closed this way in one
        # evening. The exit code was always correct; the first line was not.
        headline = (
            f"FAILED. {totals.processed} target(s) processed, "
            f"{len(failed_row_names)} row(s) fail-closed."
            if failed_row_names
            else f"Done. {totals.processed} target(s) processed."
        )
        print(headline)
        print(f"  Files synced:   {totals.synced}")
        print(f"  Files deleted:  {totals.deleted}")
        print(f"  Warnings:       {totals.warnings}")
        # Row-outcome summary (mid-first-row publish-run death fix) — states
        # which rows actually completed vs. failed, every run, so "fewer rows
        # processed than requested" is never silently indistinguishable from
        # "every requested row succeeded." `requested_names` is the exact
        # requested set when `--target` filtered; otherwise every resolved row
        # this invocation reached counts (`succeeded_row_names + failed_row_names`).
        expected_rows = requested_names or (succeeded_row_names + failed_row_names + skipped_row_names)
        # A skipped row (`--delta`, unchanged since last publish) is neither
        # succeeded nor failed, but leaving it out of this line entirely
        # reproduces the exact shape of the exit-code defect this repo fixed
        # (`0491...`/542c9750e55a`: exits 0 while printing "Rows succeeded:
        # 0/1" with nothing distinguishing a clean skip from a silent drop).
        # Naming the skip count here — not just on the "--delta: ... —
        # skipping." line above — makes the summary block self-consistent
        # even when read in isolation from the per-row output above it.
        succeeded_paren_parts = []
        if succeeded_row_names:
            succeeded_paren_parts.append(", ".join(succeeded_row_names))
        if skipped_row_names:
            succeeded_paren_parts.append(f"{len(skipped_row_names)} skipped, unchanged")
        succeeded_paren = f" ({'; '.join(succeeded_paren_parts)})" if succeeded_paren_parts else ""
        print(f"  Rows succeeded: {len(succeeded_row_names)}/{len(expected_rows)}{succeeded_paren}")
        if failed_row_names:
            print(f"  Rows FAILED:    {len(failed_row_names)} ({', '.join(failed_row_names)})", file=sys.stderr)
        if failed_row_names and succeeded_row_names:
            # Neither "succeeded" nor "everything failed" — some of the
            # requested set landed and some did not. Say so in exactly these
            # words, unmissable, not left to be inferred by diffing the two
            # counts above (the PM-hit defect: a failed-row summary line that
            # still read, at a glance, like an overall success).
            partial_scope = (
                f"mirror '{mirror_expansion[0]}'" if mirror_expansion is not None else "this publish"
            )
            print(
                f"  STATUS: PARTIAL — {partial_scope} is now PARTIALLY synced "
                f"({len(succeeded_row_names)} row(s) landed, {len(failed_row_names)} did not).",
                file=sys.stderr,
            )
        # Percolate-push next-step nudge (real incident, 2026-08-20) — a
        # round commits its dest(s) locally but never pushes them:
        # `coordinator-auto-push` (coordinator_core/hooks/auto_push.py)
        # declines any non-`work/*` branch by doctrine, and a publish lands
        # on `candidate` regardless of whether the dest is a mirror or a
        # plain `repo:`-sigil row, so the round itself is the last place
        # that still knows the target name. Only on a clean round (no
        # failures) — a
        # PARTIAL round's push-or-not is an EM judgment call, not a default
        # this line should nudge, so the PARTIAL branch above stays silent
        # on it.
        if not args.dry_run and succeeded_row_names and not failed_row_names:
            # Grouped by DEST, never per row. `mirror_expansion` is set only
            # when a single bare row name expanded to its mirror, so the
            # ordinary no-argument publish leaves it None -- and keying off
            # it alone printed one line per row (nine, for klabauter) naming
            # eight sub-rows nobody should invoke. That is the "noise people
            # skim past" failure the message register exists to prevent, so
            # the grouping key is the row's dest sigil: every row sharing a
            # `publish-mirror:<key>` sigil collapses to ONE line naming that
            # mirror key, which is the invocation that actually pushes them.
            # A row with no mirror sigil is its own dest and keeps its own
            # line. Observed live, 2026-08-20.
            # NEVER the mirror KEY: `publish.mirrors.<key>` keys are not
            # registered percolate targets (`claude_klabauter` -> percolate-
            # push MISSING_TARGET_ENTRY, observed live). The sigil groups
            # rows; the emitted token must be one of the grouped ROW NAMES,
            # every one of which resolves to that shared dest -- that is what
            # sharing a sigil means. Shortest-then-lexicographic picks the
            # mirror's base row (`claude-klabauter` over its `-bin`/`-lib`
            # siblings) deterministically.
            _sigils = raw_dest_sigil_by_name(setup_dir)
            _rows_by_group: "dict[str, List[str]]" = {}
            for _row_name in succeeded_row_names:
                _sigil = _sigils.get(_row_name) or ""
                _group = _sigil if _sigil.startswith("publish-mirror:") else f"row:{_row_name}"
                _rows_by_group.setdefault(_group, []).append(_row_name)
            _push_targets = [
                min(_names, key=lambda n: (len(n), n)) for _names in _rows_by_group.values()
            ]
            for _push_target in _push_targets:
                print(
                    f"Next step: this round is committed locally, not pushed. "
                    f"Run `percolate-push {_push_target}` to push it."
                )
        # C14 (docs/plans/2026-08-15-klabauter-release-channels.md) —
        # candidate-to-main divergence report, after the round lands. Skipped
        # under --dry-run: nothing landed to report on, and this run's own
        # dest roots may not even exist yet in that mode. Runs over every
        # distinct dest repo root this invocation reached (`end_of_run_check_
        # roots`, populated unconditionally in the row loop above), not just
        # klabauter by name — the underlying check is generic over any
        # declared `publish.mirrors.<key>.track_ref` (see that function's own
        # docstring).
        if not args.dry_run:
            for _divergence_root in dict.fromkeys(end_of_run_check_roots):
                report_candidate_divergence(_divergence_root)
        if args.dry_run:
            print("  (dry-run — no changes were made)")
        if args.dry_run:
            # Never exit 0 having processed fewer rows than requested — a row
            # that raised (SystemExit or otherwise) is reported above and this
            # is the run-level consequence of that report. Applies under
            # --dry-run too (§ main()'s exit-code-contract docstring) — a
            # previewed row can fail its own preconditions independently of
            # --dry-run, and this driver must never exit 0 while its own
            # "Rows FAILED" line, just printed above, says otherwise.
            # End-of-run gates never run under --dry-run (see `dispatch_end_
            # of_run_identity_check`'s own "Never called under --dry-run"
            # note), so there is nothing further to aggregate for this branch.
            _print_round_timing_summary(round_timings, _round_wall_start)
            return 1 if failed_row_names else 0

        # 2026-08-14 aggregate-instead-of-abort fix: this used to be an early
        # `return 1` on `failed_row_names`, which meant a round with a
        # failing row NEVER reached the end-of-run gates below — a gate
        # defect coexisting with a row failure only ever surfaced on the
        # NEXT round, after the row failure was fixed, costing one extra
        # round to discover per defect class. The gates read real,
        # already-on-disk destination content (`end_of_run_check_roots`,
        # populated for every row this run reached, success or failure — see
        # the row loop above), so running them regardless of `failed_row_
        # names` reports every problem in a single round instead of one
        # class at a time. No gate's own verdict logic changed — only
        # whether/when it runs.
        # § chunk C3.5 (docs/plans/2026-08-23-rebuild-the-percolate-round-as-
        # six-steps.md) — persist ONE `RoundManifest` per repo root this run
        # actually wrote to, using C2's own shape (`coordinator_core.percolate.
        # manifest`) rather than a second one. This is the step that WROTE the
        # bytes (`end_of_run_changed_by_repo_root`/`end_of_run_removed_by_
        # repo_root`, folded above from `process_target`'s `changed_files_
        # sink`/`removed_files_sink` — both themselves sourced from
        # `_report_published_diff`'s honest staging-vs-dest comparison, never
        # a re-parse of this driver's own printed report), so this is the
        # correct place to record what it did — independent of the end-of-run
        # gates below, which verify the result rather than produce it. A repo
        # root with at least one row whose changed-set was undeterminable
        # (`end_of_run_changed_undetermined_roots`) gets NO manifest — a
        # manifest that silently under-reports its own added/updated set is
        # worse than one that does not exist yet (fail wide, never narrow, §
        # `PhaseResult.changed_files`'s own contract). `declared_payload` (§ C1,
        # docs/dispatch-briefs/2026-08-26-a-refused-round-strands-its-payload-
        # forever/C1.md) is sourced from `end_of_run_visited_by_repo_root` --
        # the same per-row `visited_files_sink` enumeration `dispatch_end_of_
        # run_unscanned_published_check` already reads, itself a cheap path
        # enumeration (`dispatch_percolate_post_rsync`/`dispatch_percolate_
        # inject`'s `visited_sink`), never a re-derived whole-payload AST walk
        # (§ `payload_parity`'s own docstring: 3.27s against a 500ms ceiling).
        import uuid as _uuid  # noqa: PLC0415 - lazy, this round-id generation is the only user

        from coordinator_core.percolate.manifest import RoundManifest as _RoundManifest
        from coordinator_core.percolate.manifest import write_manifest as _write_manifest
        from coordinator_core.percolate.round import default_manifest_path as _default_manifest_path
        from coordinator_core.wire_paths import rel_id as _rel_id

        # § chunk C4 (state/dispatch-briefs/2026-08-26-payload-parity-asks-an-
        # index-not-the-payload/C4.md) — each round updates
        # `coordinator_core.percolate.token_index`'s on-disk index from the
        # SAME `_root_changed`/`_root_removed` sets the manifest above is
        # built from (never a hand-rolled second delta — a probe's exactness
        # result is a result about THOSE sets). One "invalidate this root"
        # call covers all three branches AC8 names: an undetermined root, a
        # refused row (never swapped, contributes nothing, needs no special
        # case here), and a `PublishSwapPartial(content_swapped=True)` root
        # (`end_of_run_token_index_invalidate_roots`, populated at the row
        # exception handler above since that row's own delta never reaches
        # `end_of_run_changed_by_repo_root`).
        _manifest_round_id = f"publish-{_uuid.uuid4().hex}"
        for _manifest_root in dict.fromkeys(end_of_run_check_roots):
            # § chunk C4 (AC8) — one named disposition per root, both
            # invalidating branches routed through the same single call.
            _token_index_action = _token_index_action_for_root(
                _manifest_root,
                invalidate_roots=end_of_run_token_index_invalidate_roots,
                undetermined_roots=end_of_run_changed_undetermined_roots,
            )
            if _token_index_action == "invalidate":
                _invalidate_token_index(_manifest_root)
            if _manifest_root in end_of_run_changed_undetermined_roots:
                continue
            _root_changed = end_of_run_changed_by_repo_root.get(_manifest_root) or set()
            _root_removed = end_of_run_removed_by_repo_root.get(_manifest_root) or set()
            _root_declared = end_of_run_visited_by_repo_root.get(_manifest_root) or set()
            # § AC1, docs/dispatch-briefs/2026-08-26-open-the-
            # percolate-removal-side/C1.md — the row scope a removal-side
            # derivation must intersect against, sourced from the SAME
            # `published_dest_dirs_sink` accumulator the unscanned-published
            # guard already reads (§ its own comment above), never re-derived.
            _root_published_dest_dirs = (
                end_of_run_published_dest_dirs_by_repo_root.get(_manifest_root) or set()
            )
            # A no-change round MUST still write its manifest when the row
            # declared a payload. The changed/removed-only guard that used to
            # stand here is precisely what strands a refused round's bytes: the
            # residue compares byte-equal forever after, so `_root_changed` and
            # `_root_removed` are both empty on every subsequent round, no
            # manifest is written, and the commit leg is handed nothing to name.
            # `declared_payload` is the whole point of the third set -- it is
            # non-empty on exactly the rounds the other two are empty on.
            if not _root_changed and not _root_removed and not _root_declared:
                continue
            # § AC2 — `_root_declared` (`end_of_run_visited_by_repo_root`) only
            # names what the percolation-surface walk SCANNED
            # (`include_extensions`/`narrow_to_include_extensions`-eligible),
            # not everything the row actually published -- a payload file
            # whose extension is not transform-eligible (e.g. a binary) is
            # tracked at dest HEAD but absent from that scan. Widen past the
            # scan surface by enumerating every path already on disk under
            # THIS run's own published dest dirs directly -- `os.walk`-class
            # path enumeration of directories already known, no per-path
            # spawn, no content read (§ `payload_parity`'s 3.27s-at-500ms-
            # ceiling anti-scope, binding here too).
            #
            # NARROW, after the widening above and never before it: a path
            # THIS round deleted as absent from source is the opposite of a
            # declared payload path -- the row's own claim is that it does not
            # belong -- yet it reaches both operands. The percolation-surface
            # scan and the orphan sweep (`publish_sync :: sync_mirror`'s
            # `REMOVE DIR:` leg) are separate passes over the same tree, so a
            # path one row swept can still be scanned under a sibling row's
            # `dest_dir`, and can still be on disk under a sibling
            # `published_dest_dirs` entry for `_walk_published_payload` to
            # name. Left in, the overlap is silently self-defeating rather
            # than loud: the removal rule is `(head_tree n row_scope) -
            # declared_payload` (§ `percolate-round.py ::
            # _pathspec_from_manifest`), so exactly the paths the round most
            # explicitly intends to delete are the ones it protects. Measured
            # on the `coordinator-claude` mirror 2026-08-26 (cross-repo/inbox/
            # 2026-08-26-doe-claude-em-coordinator-claude-remeasured-declared-
            # payload-protects-the-removals.md): the retired `whoami/` package
            # sat in `declared_payload` and `removed` at once, 23 of that
            # mirror's 67 outstanding removals.
            _root_declared_paths = (
                set(_root_declared) | _walk_published_payload(_root_published_dest_dirs)
            ) - _root_removed
            _round_manifest = _RoundManifest(
                round_id=_manifest_round_id,
                added_or_updated=frozenset(
                    _rel_id(p, _manifest_root) for p in _root_changed
                ),
                removed=frozenset(_rel_id(p, _manifest_root) for p in _root_removed),
                declared_payload=frozenset(
                    _rel_id(p, _manifest_root) for p in _root_declared_paths
                ),
                published_dest_dirs=frozenset(
                    _rel_id(p, _manifest_root) for p in _root_published_dest_dirs
                ),
            )
            _write_manifest(
                _round_manifest,
                _default_manifest_path(_manifest_root, _manifest_round_id),
            )
            # § chunk C4 — reuse the SAME `_root_changed`/`_root_removed` sets
            # the manifest just above was built from, never a re-derived
            # delta. Skipped for a root this round already invalidated
            # (§ `end_of_run_token_index_invalidate_roots` above) — folding a
            # partial delta on top of a just-deleted index would only cover
            # the delta, not the full tree, defeating the invalidation.
            if _token_index_action == "update":
                _update_token_index_from_delta(_manifest_root, _root_changed, _root_removed)

        # All four legs always run (never short-circuited by an earlier one's
        # failure) so a single run surfaces every defect it can find, not just
        # the first.
        deduped_roots = list(dict.fromkeys(end_of_run_check_roots))
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_identity_check"):
            identity_ok = dispatch_end_of_run_identity_check(
                engine_ctx,
                deduped_roots,
                target_filtered=bool(args.target),
                percolate_root=percolate_root,
                rows_by_repo_root=end_of_run_rows_by_repo_root,
                skipped_row_names=skipped_row_names,
            )
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_install_doc_payload_check"):
            install_doc_ok = dispatch_end_of_run_install_doc_payload_check(
                deduped_roots,
                target_filtered=bool(args.target),
            )
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_unscanned_published_check"):
            unscanned_ok = dispatch_end_of_run_unscanned_published_check(
                end_of_run_row_sections,
                target_filtered=bool(args.target),
                visited_files_by_repo_root=end_of_run_visited_by_repo_root,
                published_dest_dirs_by_repo_root=end_of_run_published_dest_dirs_by_repo_root,
            )
        # § chunk C4B (AC3) — wires C4's `run_function_gate` into the driver.
        # FAIL-HARD unconditionally (see that function's own docstring for the
        # judgement-call rationale) — engine_ctx.engine_claude_klabauter is narrowed non-None by
        # the same `not dry_run` guard the other three legs rely on.
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_function_gate"):
            function_gate_ok = dispatch_end_of_run_function_gate(
                engine_ctx,
                deduped_roots,
                target_filtered=bool(args.target),
            )
        # § chunk C3 (AC3/AC4) — wires C2's `run_entrypoint_gate` into the
        # driver. FAIL-HARD unconditionally, same shape as `function_gate_ok`
        # immediately above; a distinct, complementary check (§ that
        # function's own docstring) — neither leg subsumes the other.
        # § chunk C4 (docs/plans/2026-08-16-percolate-round-timing-and-
        # changed-only.md) — a repo root in `end_of_run_changed_undetermined_
        # roots` maps to `None` (undeterminable, § `dispatch_end_of_run_
        # entrypoint_gate`'s own per-root fallback), never to its partial
        # `end_of_run_changed_by_repo_root` union — fail WIDE, not narrow.
        end_of_run_changed_files_by_repo_root: "dict[Path, Optional[set[Path]]]" = {
            root: (None if root in end_of_run_changed_undetermined_roots else changed)
            for root, changed in end_of_run_changed_by_repo_root.items()
        }
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_entrypoint_gate"):
            entrypoint_gate_ok = dispatch_end_of_run_entrypoint_gate(
                engine_ctx,
                deduped_roots,
                target_filtered=bool(args.target),
                changed_files_by_repo_root=end_of_run_changed_files_by_repo_root,
                changed_only=bool(args.changed_only) and not bool(args.full_sweep),
            )
        # Review: staff-eng (MAJOR-2, slice-D-drift-store.md) wired the output
        # functional-identifier drift detector into this sequence, because
        # nothing called it and a scrub that renamed a wire identifier shipped
        # unnoticed.
        #
        # NOT CALLED, deliberately, pending a discriminator respec. The leg and
        # its tests are retained and correct; what is wrong is what the detector
        # discriminates on. Measured 2026-08-08 over all 7 targets
        # (docs/research/spike-verdicts/2026-08-08-drift-gate-discriminator-
        # position-validity.md): 7236 reported pairs, 0 defects among them, and
        # the SyntaxError-across-15-files defect this gate exists to catch is
        # NOT reportable by it under any discriminator -- both sides of that pair
        # are classified 'mention' by _extract_functional_tokens and never enter
        # the candidate stream. Enabling it therefore blocks every publish while
        # detecting nothing. Re-enable only once extraction is position-aware.
        drift_check_ok = True
        # § chunk C4 (AC4/AC6) — wires C1's `argv_parity_report` into the
        # driver as an end-of-run leg, over the same deduplicated
        # destination roots as the four legs above. FAIL-HARD
        # unconditionally (see that function's own docstring for the
        # judgement-call rationale); target_filtered is still passed
        # through for call-site symmetry and the docstring's own record of
        # why severity does not vary on it here.
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_argv_parity_gate"):
            argv_parity_ok = dispatch_end_of_run_argv_parity_gate(
                deduped_roots,
                target_filtered=bool(args.target),
            )
        # § chunk C3 (docs/plans/2026-08-28-a-dropped-module-must-not-leave-
        # its-test-behind.md) — wires C2's `run_assembled_mirror_gate` into
        # the driver as an end-of-run leg, over the same `deduped_roots` /
        # `end_of_run_rows_by_repo_root` shape as the legs above. FAIL-HARD
        # unconditionally (see that function's own docstring for the
        # judgement-call rationale, mirroring `argv_parity_ok` immediately
        # above); a declared exemption in `setup/publish-allowlist-
        # declarations.yaml`'s `assembled_mirror_gate_exemptions` is the
        # only way past a refusal -- no override flag.
        with _time_phase(round_timings, "<round>", "dispatch_end_of_run_assembled_mirror_gate"):
            assembled_mirror_gate_ok = dispatch_end_of_run_assembled_mirror_gate(
                deduped_roots,
                rows_by_repo_root=end_of_run_rows_by_repo_root,
                target_filtered=bool(args.target),
            )
        gates_ok = (
            identity_ok
            and install_doc_ok
            and unscanned_ok
            and function_gate_ok
            and entrypoint_gate_ok
            and drift_check_ok
            and argv_parity_ok
            and assembled_mirror_gate_ok
        )
        if not gates_ok:
            print(
                "publish.py: FATAL — end-of-run check(s) failed; treat this run's "
                "published bytes as unverified (AC15 fail-closed).",
                file=sys.stderr,
            )

        # § C1 — printed once here, ahead of every return below it (row
        # failure, gate failure, or clean success): all three return points
        # from here down are sequential, not alternative branches, so one
        # placement covers all of them without duplicating the summary print.
        _print_round_timing_summary(round_timings, _round_wall_start)

        # Checked AFTER the gates above run (2026-08-14 aggregate-instead-of-
        # abort fix), not before — see this branch's `--dry-run` counterpart
        # up top for the identical row-failure semantics under --dry-run.
        # The exit code a row failure produces has not moved: a failing row
        # still refuses at exit 1 even when every gate above happened to
        # pass, or when a gate ALSO failed — a row failure and a gate
        # failure are reported together in this same round either way, but
        # the row failure keeps priority for the exit code, unchanged from
        # before this fix.
        if failed_row_names:
            # Never exit 0 having processed fewer rows than requested — a row
            # that raised (SystemExit or otherwise) is reported above and this
            # is the run-level consequence of that report.
            return 1

        if not gates_ok:
            # Exit 2, not 1 (§ main()'s exit-code-contract docstring):
            # every requested row's bytes landed at this point (`failed_row_
            # names` is empty, checked immediately above) — a POST-publish
            # verification gate failing is a distinct outcome from a row
            # failing, and a caller must be able to tell "bytes did not
            # land" (1) from "bytes landed, but verification did not
            # complete" (2) from the exit code alone.
            return 2

        # Successful conclusion of the percolation — every requested row
        # landed and every end-of-run gate passed. This is the ONLY point
        # from which the commit runs (§ `_commit_published_dests`'s own
        # negative-spec block): both non-zero returns above are ahead of it,
        # and `--dry-run` returned further up.
        if args.commit:
            print("=== publish.py — commit ===")
            if not _commit_published_dests(
                end_of_run_published_dest_dirs_by_repo_root,
                succeeded_row_names=succeeded_row_names,
                round_pinned_shas=round_pinned_shas,
            ):
                # Exit 3, not 0: the bytes landed and verified, but the
                # destination is still dirty — which is precisely the state
                # the next `percolate-round` reads as a crashed predecessor.
                # Reporting it as success is what let that confusion exist.
                return 3

        return 0
    finally:
        publish_lock_stack.close()


if __name__ == "__main__":
    sys.exit(main())
