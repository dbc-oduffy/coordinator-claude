"""cc_invoke — Python-side transport for coordinator_core.invoke.

Port of: coordinator-core-invoke.sh (DoE c6d97219, 2026-07-22) — the bash transport's
fail-closed timeout/nonzero-exit/empty-stdout ladder and DEC-1..3 op-timeout budget
logic are mirrored here deliberately; several comments below note specific behavioral
parity points the port preserved.

Purpose: spawns `sys.executable -m coordinator_core.invoke <op> <params_json> --repo <repo_root>`
with a timeout cap; applies a fail-closed timeout/nonzero-exit/empty-stdout ladder,
then parses the
{jsonrpc,id,result} envelope that is coordinator_core.invoke's default (non---bare)
response shape (see DR-215 ref below). On the route() path, the engine root is resolved ONCE via the native
_resolve_claude_klabauter_root ladder (env var → pointer file → coordinator_core.engine_root,
no bash subprocess anywhere) — forwarded to cc_invoke() via _claude_klabauter_root for both the
find_spec gate and the subprocess env (single resolution source).

Public API:
    resolve_colocated_claude_klabauter_root(script_file) -> str
        Self-location-first engine-root resolution for a CLI that lives INSIDE the
        engine checkout (coordinator/bin/*.py). Tries Path(script_file)'s
        parents[2] first (probed against coordinator_core/ + pyproject.toml markers);
        falls back to _resolve_claude_klabauter_root()'s machine-local registry ladder only
        when that probe misses (the published/vendored-outside-the-checkout case).

    cc_invoke(op, params, repo_root) -> dict
        Returns the bare result dict on success (jsonrpc/id/result wrapper stripped).
        Raises RuntimeError on ANY transport failure (timeout / ImportError / empty stdout /
        bad envelope / op-error envelope) — except a structural contract-pin failure
        (engine rc=2), which raises the distinct StructuralPinError subclass instead.
        NEVER returns legacy after a native attempt. Uses the non-bare envelope-parse
        call convention (params via --params-file, ARG_MAX-immune — see cc_invoke's
        own docstring's Params transport note; NOT positional argv).

    cc_invoke_bare(op, params, repo_root) -> dict
        The shared Python promotion of the retired bash cc_invoke (see module Port of
        note): the --bare
        fail-closed ladder + the DEC-1..3 per-op timeout-budget logic, moved OUT of the
        shell transport so downstream facades can `from cc_invoke import cc_invoke_bare`
        instead of each inlining a local mirror of the shell --bare ladder (the campaign
        anti-goal). Spawns coordinator_core.invoke with --bare (engine emits the bare
        result object directly) and --params-file (ARG_MAX-immune on Windows/msys), with a
        per-op timeout ceiling resolved once-per-process from the engine's op-budget dump.
        Shares the timeout/nonzero-exit/empty-stdout fail-closed rungs with cc_invoke() via
        _raise_on_process_failure — one ladder, two call conventions. Returns the bare
        result dict; raises RuntimeError on any transport failure, or StructuralPinError
        (a RuntimeError subclass) specifically on a structural contract-pin failure
        (engine rc=2).

    route(op, params, repo_root, legacy_fn)
        State-1 seam-absent (find_spec("coordinator_core.invoke") returns None with the engine
        root on sys.path) → call and return legacy_fn(). No native spawn attempted.
        State-2 seam-present → cc_invoke(op, params, repo_root); propagate result or exception.
        Transport failure on the native path → raise (HARD error, never fall to legacy_fn).

    route_mutation(op, params, repo_root, legacy_fn)
        Mutation-aware sibling of route(): calls route(), then raises RouteMutationError
        if the returned dict carries a non-zero 'exit_code', a non-empty 'failed' list, or
        a non-empty string 'error' with exit_code absent/0 — the engine repo's op-level refusals
        live INSIDE the result payload with no top-level 'error' key at the ENVELOPE level,
        so bare route() would return them unraised. Python sibling of the shell transport's
        strangle_route_mutation (Port of: strangler-facade.sh, DoE c6d97219, 2026-07-22).

Spec backlink: DoE-claude:pln-strang-08-arm-the-doe-queue-fa-36567b § C1
DR-215 ref: coordinator_core/invoke/__main__.py's default (non---bare) response IS the
            {jsonrpc,id,result} envelope this module's cc_invoke() parses (--bare is
            opt-in server-side) — the envelope-parse convention is verified against the
            real engine's default response shape, not just this module's own fake test
            harness. The retired bash cc_invoke (Port of note, top of module) was the
            byte-oracle for the --bare/--params-file ladder mirrored by cc_invoke_bare(),
            not for this non-bare envelope-parse function.

Negative-spec (retired transport patterns — DO NOT reintroduce):
    - The coordinator_core client-module seam is retired (DR-215); this module does NOT
      import or use it.
    - Unix domain sockets are retired (DR-215); this module does NOT open one.
    - IPC authentication tokens are retired (DR-215); this module does NOT read one.
    - This is a TWO-STATE router (seam-present / seam-absent); there is no daemon-aware
      third state IN THIS ROUTER, and none should be added here. DR-315 (2026-08-15)
      authorizes a demand-driven warm engine process on the seam-present side of this
      same two-state split — that is a property of what coordinator_core.invoke's own
      process does once seam-present dispatch reaches it (a client-side pipe-first,
      spawn-on-FileNotFoundError decision inside the engine's own entry paths), not a
      third state this router discriminates on. route()'s State-1/State-2 shape is
      unchanged by DR-315 and stays two states.
    - find_spec is an INTENTIONAL improvement over the retired shell facade's full-import
      probe; do NOT replace it with an execute-import to "match" the old bash behavior.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, cast

GENERATES = []  # writes only tempfile.mkstemp() params files (cc_invoke + cc_invoke_bare), always unlinked; no tracked artifact


class StructuralPinError(RuntimeError):
    """Marks a non-self-healing structural contract-pin failure (engine rc=2 /
    JSON-RPC -32001), distinct from a generic transport failure.

    Raised by _raise_on_process_failure when the invoke process exits 2 — the
    engine's own discriminator between "structural pin broken, will not
    self-heal on retry" (rc=2, JSON-RPC STRUCTURAL_PIN_ERROR = -32001 per
    coordinator_core/ipc.py) and any other op error (rc=1, the plain
    RuntimeError fallthrough). Subclasses RuntimeError, so an existing
    `except RuntimeError` caller still catches it unchanged; callers that need
    to react differently to a structural pin catch StructuralPinError first.
    """


# ---------------------------------------------------------------------------
# Lazy op registration is unconditional as of 2026-08-22 (the
# import-path-costs-nothing sprint): coordinator_core.ops never eagerly
# imports its op modules at package-init time, so this seam no longer needs
# to arm anything before `from coordinator_core.ops.<name> import main` — the
# ~108ms eager op-module load this used to kill on the cold-trampoline path
# simply no longer happens by default. Formerly armed `sys._coordinator_core_
# lazy_ops` here (via the now-retired two-channel flag); see
# coordinator_core/ops/__init__.py.
# Spec backlink: DoE-claude:pln-decouple-coordinator-s-own-bin-42d50a § C8
# ---------------------------------------------------------------------------


def _no_console_kw(claude_klabauter_root: str) -> dict:
    """Splat-ready Windows console-suppression kwarg for a `coordinator_core.invoke`
    child spawn. ``claude_klabauter_root`` is already resolved by every call site here (the
    engine spawn itself), so this is a plain function-local coordinator_core import
    (no seam violation — see the module-top note above) rather than a fresh
    resolution. Falls back to the same suppression kwargs computed inline (zero
    imports beyond ``subprocess``) on any import failure, rather than silently
    dropping console suppression — a resolution failure must never turn a quiet
    spawn into a visible console window (Review: code-reviewer P1 — this was the
    most fanned-out `_no_console_kw`-shaped helper in coordinator/bin/ still
    fail-opening to bare ``{}``, matched here to the pattern ccbdbecc2 applied to
    sweep-boot.py/standup.py/render-project-tracker/refresh-plugin-live-install.py).

    The fallback reproduces the primitive's POSIX contract exactly -- ``{}`` off
    Windows, not ``{"creationflags": 0}``. Both splat harmlessly into
    ``subprocess.run``, but a caller comparing against ``no_console_creationflags()``
    or testing the mapping's truthiness would see the substitute disagree with the
    thing it substitutes for."""
    try:
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:  # noqa: BLE001 -- fail-open, matches this module's transport posture
        if os.name != "nt":
            return {}
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _no_console_passthrough_kw(claude_klabauter_root: str) -> dict:
    """`_no_console_kw` for a child whose OUTPUT MUST REACH THE OPERATOR.

    Same resolution and fail-open posture as `_no_console_kw` above, plus the
    std fds. Console suppression alone is not enough: with no
    ``stdout=``/``stderr=`` passed, CPython omits ``STARTF_USESTDHANDLES``, so
    the child binds its standard handles to the fresh window-less console
    ``CREATE_NO_WINDOW`` allocates instead of inheriting this process's -- and
    everything it prints is lost. Passing the fds explicitly restores the
    inheritance. Canonical implementation, kept in sync by hand because this
    module fails open without coordinator_core:
    ``coordinator_core.win_portability.no_console_passthrough_kwargs``.

    Real fds, not ``sys.stdout``/``sys.stderr``: the child inherits OS handles,
    and the fd is what a redirection actually moved. A stream with no fd
    (``pythonw``, a captured object) contributes nothing and degrades to plain
    inheritance rather than raising.
    """
    kwargs = dict(_no_console_kw(claude_klabauter_root))
    for key, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            fd = stream.fileno()
        except (AttributeError, ValueError, OSError):
            continue
        if fd >= 0:
            kwargs[key] = fd
    return kwargs


def child_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return an env dict safe to pass as `env=` to a spawned child that is
    NOT itself a coordinator_core.invoke dispatch.

    No longer strips COORDINATOR_CORE_LAZY_OPS: this module never writes it
    into `os.environ` (lazy op registration is unconditional now — see
    coordinator_core/ops/__init__.py), so the only way a child inherits the
    key is an operator's own export, which this function has always left
    alone.

    `overrides`, if given, is applied on top (last-write-wins) after the
    settings-home propagation below — for a caller that wants to add its own
    env vars to the same spawn without a second dict-merge step.

    Callers that DO want a var to reach the child (nested
    coordinator_core.invoke dispatch) should not use this — see
    `_build_subprocess_env`, which builds that env explicitly instead.

    AC11 (pln-the-machine-local-registry-rea-50be37 § C5): also propagates
    COORDINATOR_SETTINGS_HOME via `_settings_home_env` (never overwriting an
    already-set child value), same rationale as `_build_subprocess_env` —
    this spawns children too (e.g. `_machine_local_get`'s registry-read
    subprocess), and they should hit rung 0 instead of re-resolving via CLI.
    """
    env = _settings_home_env(dict(os.environ))
    if overrides:
        env.update(overrides)
    return env


# ---------------------------------------------------------------------------
# DEC-1..3 op-timeout-budget session cache (module-global, mirrors the shell
# transport's _CC_OP_TIMEOUTS_* session vars). Populated at most ONCE per Python
# process by _resolve_op_timeouts — a facade process is short-lived, so this is
# the per-process analogue of the shell's per-shell-session cache.
#   _OP_TIMEOUTS_STATE: None (unresolved) | "ok" | "absent" | "error"
# Mirrors the retired bash transport's _cc_resolve_op_timeouts (DEC-1..3).
# ---------------------------------------------------------------------------
_OP_TIMEOUTS_STATE: str | None = None
_OP_TIMEOUTS_MAP: dict[str, float] = {}
_OP_TIMEOUTS_BREADCRUMB_SHOWN: bool = False


def _reset_op_timeout_cache() -> None:
    """Reset the DEC-1..3 op-timeout session cache — test-only seam.

    The cache is a per-process singleton (resolved once); tests exercising distinct
    dump outcomes in the same process must reset it between cases.
    """
    global _OP_TIMEOUTS_STATE, _OP_TIMEOUTS_MAP, _OP_TIMEOUTS_BREADCRUMB_SHOWN
    _OP_TIMEOUTS_STATE = None
    _OP_TIMEOUTS_MAP = {}
    _OP_TIMEOUTS_BREADCRUMB_SHOWN = False


# ---------------------------------------------------------------------------
# Engine-root resolution — native Python ladder, no bash subprocess.
# _resolve_claude_klabauter_root() below is a from-scratch reimplementation mirroring
# coordinator-claude-klabauter-root.sh's four-rung discovery chain; it does not shell out
# to that script. The bash file remains on disk pending its own delete+repoint
# (Plan C de-bash wave R — see state/debt-backlog/ for the tracked entry); this
# comment previously claimed the opposite (subprocess-into-bash) and drifted
# from the code four lines below it.
# Review: code-reviewer — stale docstring at cc_invoke.py:116-119 contradicted
# _resolve_claude_klabauter_root()'s own docstring ("no bash subprocess anywhere in the
# ladder"); corrected to describe the native ladder it introduces.
# ---------------------------------------------------------------------------

_MLIR_MODULE = None


def _machine_local_impl_resolver():
    """Lazily import machine_local_impl_resolve, self-locating its own
    sys.path entry so this module stays standalone-invocable regardless of
    whether a caller already inserted coordinator/bin/lib. Cached after first
    call. Deliberately function-local (not a module-top import) — mirrors this
    module's own documented "no non-stdlib import above the LAZY_OPS line"
    discipline, even though machine_local_impl_resolve is not coordinator_core.
    """
    global _MLIR_MODULE
    if _MLIR_MODULE is None:
        _lib_dir = os.path.dirname(os.path.abspath(__file__))
        if _lib_dir not in sys.path:
            sys.path.insert(0, _lib_dir)
        import machine_local_impl_resolve as _mlir

        _MLIR_MODULE = _mlir
    return _MLIR_MODULE


def _claude_home() -> str:
    """Return the ~/.claude root, honoring CLAUDE_HOME for test isolation.

    Mirrors gen-claude-klabauter-root-pointer.py::_claude_home — this is the install root
    that hosts the machine-local Python reader (bin/_machine_local.py), distinct
    from the settings-home used for the rung-1.5 pointer file. Delegates to
    machine_local_impl_resolve.claude_home() (shared resolver — see that
    module's docstring).
    """
    return _machine_local_impl_resolver().claude_home()


# Cross-reference (C11, pln-an-engine-root-is-not-named-for-the-repo-...):
# coordinator_core/engine_root.py's `coordinator_engine_root_env`/
# `coordinator_engine_root_env_exports` (C10) are the dual-read/dual-write seam
# for this rename everywhere coordinator_core CAN be imported. This module sits
# on the far side of the same one-way no-import boundary as
# `_REGISTRY_READ_TIMEOUT_TOKEN` (imported from engine_bootstrap below) — its
# own engine-root-resolution ladder exists to LOCATE coordinator_core in the
# first place, so it cannot depend on importing coordinator_core.engine_root
# to do it — this literal is duplicated by hand in engine_root.py for the
# same reason, not an oversight.
_ENGINE_ROOT_OLD_VAR = "CLAUDE_KLABAUTER_ROOT"

_IN_PROCESS_REGISTRY_MEMO: dict[str, str | None] = {}


def _machine_local_get_in_process(key: str) -> str | None:
    """Read a machine-local registry key WITHOUT spawning `_machine_local.py`.

    Same answer as `_machine_local_get`, reached by importing the impl module
    and calling its `resolve_one` — the accessor `cmd_get` itself delegates to,
    so single-read semantics cannot diverge between the two paths (including
    the `repos.<slug>` 4-rung sibling ladder, which `resolve_one` routes
    internally when `layers=None`).

    WHY THIS EXISTS. Every CLI invocation is a fresh process, so a per-process
    memo never survives to a second call — the only way to stop paying for this
    read is to not spawn for it. Measured 2026-08-20: 0.012s in-process (import
    plus resolve) against 0.076s min / 0.219s median for the subprocess on a box
    at its stated 50-70 concurrent-LLM load norm, where spawn cost is dominated
    by contention rather than by the reader's work.

    CATCHES `SystemExit` DELIBERATELY, and this is the whole reason the fallback
    exists. `_machine_local.py` exits at MODULE TOP on an operational failure
    (its version guard, malformed TOML) — see `cmd_get`'s own docstring. Under a
    subprocess that is a non-zero rc the caller maps to `None`; imported
    in-process it would terminate the CALLING CLI. Returning `None` here routes
    such a box back to the subprocess path, which reports the same operational
    failure the same way it does today.

    Returns `None` on ANY failure — the caller treats that as "ask the
    subprocess", never as "the key is absent".

    Negative-spec: does NOT re-implement the resolution ladder, the TOML layer
    stack, or the sibling-repo scan; it calls the impl's own `resolve_one`.
    Does NOT replace `_machine_local_get` — that function keeps the
    `_RegistryReadTimeout` contract the operator-facing resolution ladder
    discriminates on, which has no in-process analogue.
    """
    if key in _IN_PROCESS_REGISTRY_MEMO:
        return _IN_PROCESS_REGISTRY_MEMO[key]
    value: str | None = None
    try:
        impl = _machine_local_impl_resolver().machine_local_impl_path(env_override=None)
        if os.path.isfile(impl):
            spec = importlib.util.spec_from_file_location("_cc_machine_local_impl", impl)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                rc, resolved = module.resolve_one(key, layers=None)
                if rc == 0 and resolved:
                    value = str(resolved).strip() or None
    except SystemExit:
        value = None
    except Exception:  # noqa: BLE001 - best-effort fast path; the caller falls back
        value = None
    _IN_PROCESS_REGISTRY_MEMO[key] = value
    return value


# ---------------------------------------------------------------------------
# Engine-root resolution — split into the sibling `engine_bootstrap` module
# (docs/plans/2026-08-21-the-cli-bootstrap-tax-dies-at-the-interpreter-floor.md
# § C2): `_resolve_engine_root` (+ its nested `_delegate_to_gate`) and every
# helper/constant EXCLUSIVE to it now live there, os+sys-only at module top,
# so a caller that needs only the bootstrap need not pay this module's own
# 27-module import cost. `_machine_local_get`, `_machine_local_impl_resolver`,
# `_walk_up_to_checkout`, and the resolution constants/exceptions moved
# alongside it because `_resolve_engine_root`'s bare-name references to them
# bind against THAT module's globals now — imported back here so every OTHER
# function in THIS file that also references them (route(), engine_source_root(),
# _state1_remediation_message(), resolve_engine_root(), _machine_local_get_in_process())
# keeps resolving them through cc_invoke's own globals, unchanged.
#
# `_resolve_claude_klabauter_root = _resolve_engine_root` immediately below is a PLAIN
# NAME ALIAS, never a wrapper — see that assignment's own comment and
# engine_bootstrap.py's module docstring condition (b)/(c)/(d).
# ---------------------------------------------------------------------------
# `engine_bootstrap` is a SIBLING module, so this bare-name import resolves
# only while this file's own directory is on `sys.path`. That holds for the
# CLI entrypoints, which put it there -- and NOT for the several callers that
# load this module BY PATH via `importlib.util.spec_from_file_location`, a
# loader that deliberately does not touch `sys.path`. Those callers got a
# bare `ModuleNotFoundError: engine_bootstrap` the moment the split landed
# (2026-08-21), from a file that had always been by-path loadable.
#
# Self-locating rather than requiring every by-path caller to prepend the
# directory itself: the requirement would be invisible at every call site and
# rediscovered the same way each time. Appended, never prepended, so this can
# never shadow an earlier entry a caller chose deliberately.
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

from engine_bootstrap import (  # noqa: E402 -- see module-top note on this file's own lazy-op seam
    _MACHINE_LOCAL_READ_TIMEOUT_SECS,
    _CLAUDE_KLABAUTER_ROOT_REMEDIATION,
    _REGISTRY_READ_TIMEOUT_TOKEN,
    _RegistryReadTimeout,
    _ENGINE_ROOT_NEW_VAR,
    _machine_local_get,
    _machine_local_impl_resolver,
    _resolve_engine_root,
    _walk_up_to_checkout,
)




# Back-compat alias for the C17 rename (docs/plans/2026-08-20-an-engine-root-
# is-not-named-for-the-repo.md § C17): `_resolve_claude_klabauter_root` is the
# pre-rename spelling. This is a PLAIN NAME ALIAS, not a wrapper function --
# both names reference the exact same function object, so
# `inspect.getsource(_resolve_claude_klabauter_root)` call-site guards and
# `unittest.mock.patch.object(module, "_resolve_claude_klabauter_root")` callers
# elsewhere in this tree keep working unchanged: every bare call site in
# THIS module still spells the call `_resolve_claude_klabauter_root()`, so a patch on
# that name intercepts it (Python resolves a bare name against module
# globals at call time, not at def time). Bucket-4 callers
# (docs/reference/engine-vs-locator-resolver-routing.md, ENGINE verdict,
# ~53 files) that import this name directly also keep working. Remove only
# once every caller — internal and external — has been routed to
# `_resolve_engine_root` directly.
_resolve_claude_klabauter_root = _resolve_engine_root

# Dual-read window for the engine-root rename (docs/plans/2026-08-20-an-engine-
# root-is-not-named-for-the-repo.md). The PUBLISHED engine is transformed on the
# way out -- every `claude-klabauter` identifier becomes `claude_klabauter` -- but it still
# imports THIS module from the live tree, which is not transformed. So a published
# workstream_complete asks for `_resolve_claude_klabauter_root` and finds only
# `_resolve_claude_klabauter_root`, and the ceremony tail dies on ImportError for every
# session on the box. Exporting both names costs nothing and closes that window.
# In the mirror this line transforms into a self-assignment, which is a harmless
# no-op. Remove it only once no published engine references the old spelling.
_resolve_claude_klabauter_root = _resolve_claude_klabauter_root
def resolve_colocated_claude_klabauter_root(script_file: str) -> str:
    """Resolve the engine root for a CLI that lives INSIDE the engine checkout itself.

    Self-location-first ladder for scripts under coordinator/bin/ (e.g. the
    distill-*.py CLIs): those scripts need to find their OWN repo root, which
    `Path(__file__)` answers with zero external dependency and can never be
    "unset" — unlike `_resolve_claude_klabauter_root`'s machine-local registry lookup,
    which exists to resolve a *different* repo across a repo boundary and is a
    manufactured fail-hard dependency for a co-located script.

    Rung 1: `Path(script_file).resolve().parents[2]` — for a script at
            coordinator/bin/X.py, parents[0]=coordinator/bin, parents[1]=coordinator,
            parents[2]=the engine root. Accepted only if it probes as a real
            engine checkout (has BOTH a coordinator_core/ directory AND a
            pyproject.toml — the same two-marker probe on every caller, so a
            change here can't silently diverge across the six distill CLIs).
    Rung 2: `_resolve_claude_klabauter_root()` (machine-local registry ladder) — only reached
            when rung 1's probe misses, i.e. the script has been published/vendored
            to a location outside its own engine checkout (the case the previous
            registry-only resolution was actually trying to cover).

    Raises RuntimeError (via _resolve_claude_klabauter_root's own fail-loud remediation text)
    if BOTH rungs miss.
    """
    _candidate = Path(script_file).resolve().parents[2]
    if (_candidate / "coordinator_core").is_dir() and (_candidate / "pyproject.toml").is_file():
        return str(_candidate)
    return _resolve_claude_klabauter_root()


# `_walk_up_to_checkout` moved to engine_bootstrap.py (imported above) — it is
# a dependency of BOTH `_resolve_engine_root` (Rung 3, now defined there) and
# `resolve_engine_root` below (still defined here, on the LOCATOR axis), so it
# lives in the sibling module and both sides import the one function object.


def resolve_engine_root(script_file: str) -> str:
    """Resolve the engine checkout for a co-located CLI, override-first.

    The ladder every ``coordinator/bin`` entrypoint should use to find the
    engine it is about to import from:

      Rung 1: ``COORDINATOR_ENGINE_ROOT`` in the environment, when it names a
              real directory — the explicit operator/test-harness override.
              (Pre-C14 this rung read ``CLAUDE_KLABAUTER_ROOT``; the dual-read window
              closed and the old name is no longer consulted here — see
              ``_ENGINE_ROOT_NEW_VAR``/``_ENGINE_ROOT_OLD_VAR``'s module-level
              note.)
      Rung 2: self-location — ``_walk_up_to_checkout(script_file)``, the
              nearest enclosing checkout at any depth.
      Rung 3: ``_resolve_claude_klabauter_root()``'s remaining rungs — the
              ``<settings-home>/machine-local/.claude-klabauter-root`` pointer file, then
              the machine-local ``repos.claude_klabauter`` registry key.

    Distinct from ``resolve_colocated_claude_klabauter_root`` in rung ORDER, and the
    difference is load-bearing: that function probes self-location BEFORE the
    environment, so a caller pointing a script at a different engine checkout
    via ``COORDINATOR_ENGINE_ROOT`` is silently served the one the script
    happens to sit in. Its existing callers are pinned to that ordering, so
    this is a new function rather than a change of semantics underneath them.

    Relative to the bare ``_resolve_claude_klabauter_root()`` this replaces at ~26 call
    sites, rung 1 is NOT byte-identical. Both still consult
    ``COORDINATOR_ENGINE_ROOT`` first and both still let it outrank every
    other rung — but unlike ``_resolve_claude_klabauter_root``, which returns any
    non-empty env value verbatim, this rung 1 is gated on
    ``os.path.isdir(env_root)``: a set-but-nonexistent
    ``COORDINATOR_ENGINE_ROOT`` (e.g. stale after a cross-platform sync —
    ``~/.claude`` is shared between machines whose absolute paths differ, so a
    value baked on one box can name nothing on the other) falls through to
    self-location instead of being honored. This is deliberate: silently
    trusting a nonexistent root would reintroduce the ModuleNotFoundError this
    function exists to remove. The consequence for a caller relying on the old
    verbatim-return behavior — e.g. a test harness that deliberately pins a
    broken ``COORDINATOR_ENGINE_ROOT`` to assert on the resulting failure — is
    that it will no longer get that broken root back; it gets self-location's
    answer (or the registry ladder's) instead.

    Otherwise: self-location is consulted ahead of the pointer file and the
    registry. That is what makes a script inside an engine checkout work on an
    install whose machine-local registry was never populated, which is the
    portability defect this exists to close: before it, a hand-set
    ``PYTHONPATH`` was the only remaining answer.

    Note the one behavior change that follows: on a box whose pointer file or
    registry names a DIFFERENT checkout than the one the script lives in, the
    script now uses its own. That is the intended reading of "co-located" and
    matches what ``resolve_colocated_claude_klabauter_root``'s callers already do; an
    operator who genuinely wants the other tree sets
    ``COORDINATOR_ENGINE_ROOT`` to an EXISTING directory, which still outranks
    everything.

    Raises RuntimeError (via ``_resolve_claude_klabauter_root``'s fail-loud remediation
    text) when every rung misses.

    A caller that must fail loud when the engine is unresolvable belongs on
    THIS function, not on ``ensure_engine_on_path`` — see that function's
    docstring for why the degrading form is the wrong choice there.
    """
    # C14 closed the dual-read window: the NEW name only (see
    # _ENGINE_ROOT_NEW_VAR/_ENGINE_ROOT_OLD_VAR's module-level note above).
    env_root = os.environ.get(_ENGINE_ROOT_NEW_VAR) or ""
    if env_root and os.path.isdir(env_root):
        return env_root
    walked = _walk_up_to_checkout(script_file)
    if walked:
        return walked
    return _resolve_claude_klabauter_root()


def _front_insert_on_path(root: str) -> str:
    """Shared ``if root not in sys.path: sys.path.insert(0, root)`` body.

    The one insert primitive every path-mutating resolver wrapper in this
    module (``ensure_engine_on_path``, ``require_engine_on_path``,
    ``require_colocated_engine_on_path``) calls through, so the front-insert
    behavior — an explicit ``COORDINATOR_ENGINE_ROOT`` outranking an ambient editable
    install of ``coordinator_core`` — lives in exactly one place. Returns
    ``root`` unchanged, so callers can end on ``return _front_insert_on_path(root)``.
    """
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def ensure_engine_on_path(script_file: str) -> str | None:
    """Resolve the engine root via ``resolve_engine_root`` and put it on ``sys.path``.

    The one-line form of the ``resolve → if not in sys.path → insert`` dance
    that was hand-rolled at every engine-touching seam in ``coordinator/bin``.
    Inserts at the FRONT, so an explicit ``COORDINATOR_ENGINE_ROOT`` outranks an ambient
    editable install of ``coordinator_core``.

    Best-effort by design: returns None instead of raising when every rung
    misses, because the callers are CLIs that degrade gracefully on an
    engine-less install (a scaffold that needs no engine must not die on a
    resolution failure). A caller that genuinely requires the engine should
    call ``require_engine_on_path`` directly and let the RuntimeError fly.

    Catches both ``RuntimeError`` (every rung missed) and ``OSError``
    (a filesystem probe along the way — e.g. a broken junction or an
    inaccessible ancestor that ``_walk_up_to_checkout`` couldn't shield
    itself, or a registry/pointer-file read failure) so the "never raises"
    contract above actually holds; narrowing to ``RuntimeError`` alone let a
    raw ``OSError`` from a filesystem edge case escape past this best-effort
    boundary.

    Returns the resolved root, or None when unresolvable.
    """
    try:
        root = resolve_engine_root(script_file)
    except (RuntimeError, OSError):
        return None
    if not root:
        return None
    return _front_insert_on_path(root)


def require_engine_on_path(script_file: str) -> str:
    """Resolve the engine root via ``resolve_engine_root`` and put it on ``sys.path``, fail-loud.

    Env-first ladder (``resolve_engine_root``'s own rung order: an existing-directory
    ``COORDINATOR_ENGINE_ROOT`` first, then self-location, then the pointer-file/registry rungs) — so
    an explicit operator override outranks self-location here, unlike
    ``require_colocated_engine_on_path`` below.

    Catches NOTHING: a ``RuntimeError`` from ``resolve_engine_root`` (every rung missed)
    or an ``OSError`` from a filesystem probe along the way propagates straight to the
    caller. Use this over ``ensure_engine_on_path`` when the caller genuinely requires the
    engine and an unresolvable root should be a hard failure, not a silent None.

    Returns the resolved root.
    """
    root = resolve_engine_root(script_file)
    return _front_insert_on_path(root)


def require_colocated_engine_on_path(script_file: str) -> str:
    """Resolve the engine root via ``resolve_colocated_claude_klabauter_root`` and put it on ``sys.path``, fail-loud.

    Self-location-first ladder: ``resolve_colocated_claude_klabauter_root``'s rung 1 probes
    ``Path(script_file)``'s own ``parents[2]`` as a candidate engine checkout BEFORE
    consulting the environment — while its two-marker probe hits, an explicit
    ``COORDINATOR_ENGINE_ROOT`` is never even consulted. Only when that self-location probe misses
    does resolution fall through to ``_resolve_claude_klabauter_root()``'s ladder, where
    ``COORDINATOR_ENGINE_ROOT`` is rung 1.

    Catches NOTHING: a ``RuntimeError`` from ``resolve_colocated_claude_klabauter_root`` (both
    rungs missed) or an ``OSError`` from a filesystem probe along the way propagates
    straight to the caller.

    Returns the resolved root.
    """
    root = resolve_colocated_claude_klabauter_root(script_file)
    return _front_insert_on_path(root)


def require_dispatch_engine_on_path() -> str:
    """Resolve the DISPATCH engine root and put it on ``sys.path``, fail-loud.

    The collapse target for the inline bootstrap preamble that ~200 CLIs under
    ``coordinator/bin`` carry verbatim::

        claude_klabauter_root = _resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)

    NOTE THE MISSING PARAMETER, because it is the whole point. Every other
    ``*_on_path`` wrapper in this module takes ``script_file`` and resolves on the
    LOCATOR axis — "where is the source checkout", answered by walking up from the
    calling file. This one takes nothing, because the DISPATCH answer — "which
    engine executes" — is a property of the box, not of the caller's location. A
    signature that cannot accept a script path cannot silently be handed one.

    WHY NOT REUSE ``require_engine_on_path``. It is the same shape one axis over
    and adopting it here looks like the obvious collapse, but on a conformant box
    with both env vars unset the two ladders return DIFFERENT ROOTS:
    ``_resolve_claude_klabauter_root()`` reaches the published mirror through the
    pointer-file/registry rung, while ``resolve_engine_root()`` reaches the live
    working tree through its self-location rung. Routing the inline copies onto the
    locator seam therefore repoints every one of them from the published engine to
    the working tree — a fleet-wide behaviour change wearing a collapse commit's
    label. Measured and reverted once already; see the plan's delivery notes.

    So this is a SECOND seam on a DIFFERENT axis, not a duplicate of the first. The
    duplication C16 forbids is two seams answering the same question.

    Catches NOTHING, matching the inline body it replaces: a ``RuntimeError`` from
    ``_resolve_claude_klabauter_root()`` (every rung missed) propagates to the caller, whose
    own ``except RuntimeError`` remediation path is usually the reason it is there.

    Returns the resolved dispatch root, so a caller that also needs to hand it to
    ``cc_invoke`` can end on ``root = require_dispatch_engine_on_path()``.

    Spec backlink: docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md
    (C16), and docs/reference/engine-root-env-var-routing.md for which call sites
    are on which axis.
    """
    return _front_insert_on_path(_resolve_claude_klabauter_root())


# ---------------------------------------------------------------------------
# Seam gate — disk-presence check via find_spec. Note: find_spec on a dotted name
# imports the parent package (coordinator_core) as a side-effect — sys.path is
# restored after the probe, sys.modules is not. Intentional improvement over the
# retired shell facade's full-import probe: a broken-but-present
# engine routes native → ImportError → hard error rather than silently falling to
# legacy.
# ---------------------------------------------------------------------------

def _seam_present(claude_klabauter_root: str) -> bool:
    """Return True if coordinator_core.invoke is importable from claude_klabauter_root.

    Uses importlib.util.find_spec — disk-presence check with a sys.modules side-effect.
    Temporarily injects claude_klabauter_root onto sys.path for the probe; restores sys.path on exit.

    Note: find_spec on a dotted name ("coordinator_core.invoke") imports the parent
    package coordinator_core as an internal step when it is not already in sys.modules —
    coordinator_core may remain in sys.modules after this call. Only sys.path is restored.

    Negative-spec: does NOT execute the module or probe liveness; a broken module
    that find_spec can locate routes to the native path and raises hard on import.
    """
    # find_spec on a dotted name imports the parent pkg as a side-effect; sys.modules
    # is not restored, only sys.path (see the docstring above).

    # Module-hijack defense-in-depth: the registry-resolved root is trusted, but an
    # un-validated relative or non-directory path on sys.path[0] is the hijack vector —
    # treat it as seam-absent and route to the safe legacy default.
    if not os.path.isabs(claude_klabauter_root) or not os.path.isdir(claude_klabauter_root):
        return False

    _injected = claude_klabauter_root not in sys.path
    if _injected:
        sys.path.insert(0, claude_klabauter_root)
    try:
        spec = importlib.util.find_spec("coordinator_core.invoke")
        return spec is not None
    except (ModuleNotFoundError, ValueError):
        return False
    finally:
        if _injected:
            try:
                sys.path.remove(claude_klabauter_root)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Shared transport helpers — used by BOTH cc_invoke() (envelope-parse convention)
# and cc_invoke_bare() (--bare convention) so the fail-closed ladder lives once.
# ---------------------------------------------------------------------------

def _should_pass_repo(op: str, claude_klabauter_root: str | None = None) -> bool:
    """Return whether `--repo` should be spawned on argv for `op`.

    DR-279 (docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md) made
    coordinator_core.invoke exit non-zero when --repo is passed to a "none"-scoped
    op, but this module passed --repo unconditionally on every op — every
    none-scoped op invoked through cc_invoke died. Mirrors
    coordinator_core/invoke/__main__.py's own gate exactly (`args.op not in
    WORKTREE_SCOPED_OPS` refuses --repo): WORKTREE_SCOPED_OPS is the authoritative
    frozenset of ops whose scope is "common_dir" or "show_top" (derived from
    coordinator_core.op_scopes.OP_KEY_SCOPE); every other op — "none"/"central"
    scoped, OR simply absent from the table (OP_KEY_SCOPE.get(op, "none") in
    __main__.py) — refuses --repo the same way. Read from the table rather than
    hardcoding an op list, so this wrapper and the engine's own refusal can never
    drift apart again.

    Review: code-reviewer (P3) — a bare `from coordinator_core.op_scopes import
    ...` here relies on coordinator_core already being importable from the
    CALLING process's ambient sys.path, which is NOT guaranteed: a caller script
    living at coordinator/bin/*.py (e.g. coordinator-workflow-scaffold.py) has
    only coordinator/bin/lib on sys.path, not the engine root itself, so the
    import raised ImportError every time and this function silently fell open
    (returned True) on EVERY call — reintroducing the exact DR-279 bug this
    module exists to fix, for exactly the callers most likely to hit it. Mirrors
    `_seam_present()`'s own temporary sys.path injection: try the ambient import
    first (covers callers that already have coordinator_core importable, zero
    added cost), and only on failure try again with `claude_klabauter_root` (resolved by
    the caller, or freshly resolved here if not supplied) temporarily inserted
    onto sys.path. Still fails OPEN (returns True) if BOTH attempts fail — cc_invoke
    is on the hot path for many callers, and a broken resolution here must never
    crash the transport.
    """
    try:
        from coordinator_core.op_scopes import WORKTREE_SCOPED_OPS

        return op in WORKTREE_SCOPED_OPS
    except Exception:
        pass

    try:
        _root = claude_klabauter_root if claude_klabauter_root is not None else _resolve_claude_klabauter_root()
    except RuntimeError:
        return True

    if not os.path.isabs(_root) or not os.path.isdir(_root):
        return True

    _injected = _root not in sys.path
    if _injected:
        sys.path.insert(0, _root)
    try:
        from coordinator_core.op_scopes import WORKTREE_SCOPED_OPS

        return op in WORKTREE_SCOPED_OPS
    except Exception:
        return True
    finally:
        if _injected:
            try:
                sys.path.remove(_root)
            except ValueError:
                pass


def none_scoped_repo_refusal(prog: str, op: str) -> str:
    """Shared refusal text for a caller CLI's own `--repo` flag on a
    scope="none" op.

    D2+D3+D4 (docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md § C16): a
    scope="none" op is never repo-targeted at the wire — `_should_pass_repo`
    above suppresses forwarding `--repo` on argv for it, and `cc_invoke_bare`
    always spawns with `cwd=claude_klabauter_root`, so a caller-computed root is
    discarded before the child process starts regardless of how it was
    obtained. A caller-facing `--repo` flag on such an op must therefore
    refuse loud (DR-279's shape, docs/decisions/DR-279-repo-on-a-none-scoped-
    op-fails-loud.md) rather than accept/require/isdir-validate/git-resolve a
    value that is never transmitted. `coordinator-compute-layer-scaffold.py`
    is the reference implementation this message text mirrors verbatim
    (same author, same op scope, this was its own inline refusal before
    being promoted here).
    """
    return (
        f"{prog}: --repo is meaningless for {op} (scope=\"none\"): this op "
        "accesses no repo-specific state and never reads repo_root, so "
        "--repo would silently no-op. Omit --repo. See "
        "docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md."
    )


def _locator_axis_export() -> dict[str, str]:
    """C18: the LOCATOR-axis export, added alongside the dispatch variable.

    Spec: docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md § C18.
    Axis definition: docs/decisions/DR-326.

    `COORDINATOR_ENGINE_ROOT` in the child env carries the DISPATCH answer -- which engine
    executes -- because that is what `_resolve_claude_klabauter_root()` returns and what
    this process is about to run. A grandchild asking the LOCATOR question
    ("where is the source checkout?") reads the same variable and is handed a
    published mirror. Two facts, one variable.

    NEGATIVE SPEC -- ADDITIVE ONLY. This returns ONLY the locator key. It never
    touches `CLAUDE_KLABAUTER_ROOT`, `COORDINATOR_ENGINE_ROOT`, or `PYTHONPATH`, so the
    dispatch variable's meaning and value are byte-identical to before this
    landed and a child that ignores the new key behaves exactly as it does
    today. That property is what makes a semantic split landable across four
    version-skewed parties (live tree, published mirror, deployed settings home,
    sibling repos) -- it turns "four parties x two meanings" into "four parties
    x two variables".

    Resolves through `_machine_local_get`, NOT through `_resolve_claude_klabauter_root()`:
    the registry's `repos.claude_klabauter` IS the locator answer, whereas the
    ladder deliberately prefers the published engine. Returns `{}` when the key
    is unset or the lookup fails -- a box with no registered checkout must keep
    spawning children exactly as it does now, so this is best-effort by design
    and never raises into the spawn path.

    In-process first (`_machine_local_get_in_process`), subprocess only on its
    miss. This function runs on EVERY `cc_invoke()` and `cc_invoke_bare()`, so
    the subprocess it used to take unconditionally was a per-invocation,
    fleet-wide process spawn for one unchanging key. The value is byte-identical
    on both paths -- `resolve_one` is the accessor the spawned `cmd_get` itself
    calls -- so the additive-only property above is unchanged.
    """
    source_root = _machine_local_get_in_process("repos.claude_klabauter")
    if not source_root:
        try:
            source_root = _machine_local_get("repos.claude_klabauter")
        except Exception:
            return {}
    if not source_root:
        return {}
    return {"COORDINATOR_ENGINE_SOURCE_ROOT": source_root}


def _build_subprocess_env(claude_klabauter_root: str) -> dict[str, str]:
    """Build the subprocess env for a coordinator_core.invoke spawn.

    Passes os.environ through, sets COORDINATOR_ENGINE_ROOT, and prepends it to PYTHONPATH only if
    not already present (idempotency fence — mirrors _cc_resolve_deps() in the shell
    transport). Shared by cc_invoke(), cc_invoke_bare(), and the op-budget dump spawn.

    AC11 (pln-the-machine-local-registry-rea-50be37 § C5): also propagates
    COORDINATOR_SETTINGS_HOME into the child env via `_settings_home_env`, so a
    child that itself resolves settings-home (directly, or by invoking a shell
    resolver that tries the `coordinator-settings-home` CLI before its disk
    fallback) hits rung 0 and skips that CLI call.

    C14 (dual-write window CLOSED): sets `COORDINATOR_ENGINE_ROOT` ONLY —
    the same new-name-only shape as
    `coordinator_core.engine_root.coordinator_engine_root_env_exports`,
    duplicated by hand here rather than imported (see the module-level literal
    duplication note above this function's neighbours) and pinned equal to it
    by test. Until C14 this set both names so a child running from a pre-rename
    tree still resolved; continuing to export the old name is precisely what
    kept stale readers working and the precondition open. This routes the NAME
    only — it still answers the DISPATCH question (which engine executes), the
    axis split (C18) is not this function's concern.
    """
    env: dict[str, str] = _settings_home_env(
        {**os.environ, _ENGINE_ROOT_NEW_VAR: claude_klabauter_root},
        claude_klabauter_root,
    )
    env.update(_locator_axis_export())
    existing_pp = env.get("PYTHONPATH", "")
    _sep = os.pathsep
    if f"{_sep}{claude_klabauter_root}{_sep}" not in f"{_sep}{existing_pp}{_sep}":
        env["PYTHONPATH"] = f"{claude_klabauter_root}{_sep}{existing_pp}" if existing_pp else claude_klabauter_root
    return env


def _settings_home_env(base_env: dict[str, str], claude_klabauter_root: str | None = None) -> dict[str, str]:
    """Return `base_env` with COORDINATOR_SETTINGS_HOME set to the resolved
    settings-home root, UNLESS `base_env` already carries the key.

    AC11 (pln-the-machine-local-registry-rea-50be37 § C5): the actual spawn seam
    that builds child env for claude-klabauter-owned fan-outs. `coordinator_core._settings_home
    .settings_home()` is a pure env/home read with zero external calls (no CLI
    spawn), so this is re-derived fresh on every call — there is no per-process
    cache to go stale across a long-lived warm engine or EM session, which
    trivially satisfies "re-derive per op-dispatch, not per process".

    Precedence: an explicitly-set child value (differently-rooted tenant, a test
    harness redirecting it, a deliberately-scoped operator shell) is NEVER
    overwritten — this only fills a gap the child env does not already carry.

    Import is function-local, matching this module's convention (see the
    eager-op-registration seam note above): no coordinator_core import sits
    above that seam at module top. `claude_klabauter_root` is inserted onto `sys.path`
    only for the duration of the import, mirroring `_is_worktree_scoped_op`'s
    own inject/finally-remove pattern — this function must never crash the
    transport, so a resolution failure falls back to `base_env` unchanged.
    """
    if base_env.get("COORDINATOR_SETTINGS_HOME"):
        return base_env

    # C14 closed the dual-read window: the NEW name only (see
    # _ENGINE_ROOT_NEW_VAR/_ENGINE_ROOT_OLD_VAR's module-level note above).
    _root = claude_klabauter_root if claude_klabauter_root is not None else os.environ.get(_ENGINE_ROOT_NEW_VAR)
    _injected = bool(_root) and _root not in sys.path
    if _injected:
        sys.path.insert(0, _root)
    try:
        from coordinator_core import _settings_home

        return _settings_home.settings_home_child_env(base_env)
    except Exception:
        return base_env
    finally:
        if _injected:
            try:
                sys.path.remove(_root)
            except ValueError:
                pass


_IMPORT_ERROR_TOKENS = ("importerror", "modulenotfounderror", "no module named")

#: Cap on the raw-stdout tail `_op_error_detail` falls back to when the child's
#: stdout is not a parseable JSON-RPC envelope. A traceback or a debug dump can
#: run to megabytes; the raised message has to stay readable in a terminal.
_OP_ERROR_DETAIL_CAP = 2000


def _op_error_detail(stdout_text: str) -> str:
    """Recover the engine's own failure text from a nonzero-exit child's STDOUT.

    ``coordinator_core.invoke`` splits its two failure channels by ORIGIN, not by
    severity, and the split is easy to misread as "errors go to stderr":

      - A PRE-dispatch failure (bad args, unresolvable repo_root) goes through
        ``_fatal_stderr``, which writes its JSON-RPC error envelope to **stderr**
        and exits 1.
      - A dispatch that COMPLETED with an op-level error is an ordinary JSON-RPC
        response: ``main()`` prints it to **stdout** and exits 1 via
        ``_exit_code_for_response``. Stderr is typically empty.

    ``_raise_on_process_failure`` only ever read stderr, so the entire second
    class — every op-level refusal, every exception escaping a handler, an
    unknown method — reached the operator as a bare
    ``invoke process exited 1 (op=X) — op or dispatch error`` followed by an
    empty ``stderr:`` line, with the reason nowhere: it was sitting on stdout,
    discarded unread. That is how ``ceremony.wsc_tail`` failed on doe-claude-em's
    Windows box with no recoverable diagnosis
    (``cross-repo/inbox/2026-08-07-doe-claude-em-windows-ceremony-cli-coordinator-core-import-break.md``),
    and why that one item's symptom looked unlike its two siblings' — those died
    in the trampoline process itself and printed a real traceback, while this one
    died behind the transport's blind side.

    Returns an indented ``  op error: ...`` line for a JSON-RPC error envelope, a
    capped ``  op stdout: ...`` line for anything else non-empty, or ``""`` when
    stdout carries nothing. Never raises — this runs on a path that is already
    failing and must not acquire a second failure mode of its own.

    To reproduce the stdout-borne error envelope this recovers, without firing a
    mutating op at a live tree: ``docs/reference/transport-failure-probes.md``
    (``diagnostics.always_refuses`` is the write-free probe for this shape).
    """
    text = (stdout_text or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict):
            return (
                f"  op error: code={err.get('code', '?')!r} "
                f"message={err.get('message', '?')!r}"
            )
        if err:
            return f"  op error: {err!r}"
    return f"  op stdout: {text[:_OP_ERROR_DETAIL_CAP]}"


def _raise_on_process_failure(
    rc: int,
    stdout_text: str,
    stderr_text: str,
    op: str,
    claude_klabauter_root: str,
) -> None:
    """Fail-closed rungs (2) and (3) of the shell ladder — nonzero exit and empty stdout.

    Rung (1), the timeout branch, is handled at each caller's subprocess.run try/except
    (both catch TimeoutExpired) since the timeout value is caller-local. Raises
    RuntimeError (or its StructuralPinError subclass) on failure; returns None when the
    process succeeded with output.

    (2) Nonzero exit → distinguish, in precedence order: ImportError on stderr
        (engine-won't-start) > rc==2 structural contract-pin failure
        (StructuralPinError, non-self-healing) > ImportError recovered from the
        stdout error envelope > generic op-level error. EVERY rung now carries
        ``_op_error_detail``'s recovery of the child's stdout — see that
        function for the channel split this ladder used to be blind to.
    (3) Empty stdout → invoke always produces output on success.

    Negative-spec: the stdout-borne ImportError rung is deliberately ranked BELOW
    the rc==2 structural-pin rung, not folded into the stderr sniff above it. The
    pre-existing precedence — which rung an input lands on: stderr-ImportError >
    rc==2 > generic — is load-bearing and stays identical; widening the top sniff
    to stdout would let a structural-pin message that merely mentions a module
    name get reclassified as an install failure, losing the engine's own
    non-self-healing discriminator. (The raised message TEXT for rungs 1/2 is not
    byte-identical to before this change — `_op_error_detail`'s recovered detail
    is now appended to every rung, including these two — only the routing
    precedence is pinned. Review: code-reviewer P3.)

    ``docs/reference/transport-failure-probes.md`` maps each rung above to a
    write-free probe that reaches it — safe to fire at a live, dirty, shared tree
    — and names the three rungs (stderr ImportError, empty stdout, transport
    absent) that no registered op can reach, with the spawn-free unit cases that
    cover them instead.
    """
    if rc != 0:
        detail = _op_error_detail(stdout_text)

        def _engine_wont_start(token_origin: str) -> RuntimeError:
            """Build the engine-won't-start error, naming which channel accused the engine.

            ``token_origin`` is load-bearing rather than cosmetic. Two different rungs
            raise this, and only one of them is strong evidence:

              - ``stderr`` — the engine itself failed to import, and said so on the
                channel it uses for pre-dispatch failures. Trustworthy.
              - ``stdout`` — an ImportError token was recovered from a COMPLETED
                dispatch's own error envelope. That usually means the same thing, but
                it cannot mean it as certainly: the engine demonstrably started (it ran
                a handler far enough to produce an envelope), so an op merely reporting
                a module problem of its own lands here too and gets told to go check
                COORDINATOR_ENGINE_ROOT. Naming the origin is what lets the operator tell those
                apart instead of chasing an install that is fine.

            Narrowing the stdout sniff to remove that false positive was considered and
            declined: it trades a visible-and-labelled misclassification for a silent
            missed one, and this ladder's whole purpose is that failures state what they
            actually know. Reviewed and escalated as s2/F1 (2026-08-07).
            """
            lines = [
                f"cc_invoke: engine will not import/start (op={op}, rc={rc})",
                "  ImportError — verify COORDINATOR_ENGINE_ROOT and coordinator_core installation:",
                f"    COORDINATOR_ENGINE_ROOT={claude_klabauter_root!r}",
                f"    ImportError token seen on: {token_origin}",
            ]
            if token_origin == "stdout":
                lines.append(
                    "    NOTE: recovered from the op's OWN error envelope, not from engine "
                    "startup — the engine did start, so if the op merely reported a module "
                    "problem of its own, this classification is wrong; read the op error below."
                )
            lines.append(f"    stderr: {stderr_text.strip()}")
            message = "\n".join(lines)
            return RuntimeError(f"{message}\n{detail}" if detail else message)

        if any(tok in stderr_text.lower() for tok in _IMPORT_ERROR_TOKENS):
            raise _engine_wont_start("stderr")
        if rc == 2:
            message = (
                f"cc_invoke: structural contract-pin failure (op={op}, rc=2) — "
                "non-self-healing, will recur on retry\n"
                f"  stderr: {stderr_text.strip()}"
            )
            raise StructuralPinError(f"{message}\n{detail}" if detail else message)
        if any(tok in detail.lower() for tok in _IMPORT_ERROR_TOKENS):
            raise _engine_wont_start("stdout")
        message = (
            f"cc_invoke: invoke process exited {rc} (op={op}) — op or dispatch error\n"
            f"  stderr: {stderr_text.strip()}"
        )
        raise RuntimeError(f"{message}\n{detail}" if detail else message)

    if not stdout_text.strip():
        raise RuntimeError(
            f"cc_invoke: empty stdout from invoke (op={op}) — invoke produced no output"
        )


#: Additive client-side allowance over the engine's OWN published budget, covering the
#: only part of the wait that budget does not: the child's cold interpreter start plus
#: the `coordinator_core` import it pays before its dispatch clock starts. Sized from
#: what that costs, not from the 10s it replaced — the engine's measured cold-start
#: floor is 57.1ms (CoV 1.5%, `docs/wiki/misc-harvest-2026-08-06-13h-corrected.md`), and
#: a spawn under the declared 50-70-concurrent-LLM load norm runs 0.076s min / 0.219s
#: median (`_machine_local_get_in_process`'s own 2026-08-20 measurement). 2s is ~34x the
#: unloaded floor and ~9x the loaded median, and is simultaneously the ceiling CLAUDE.md
#: § Load norm puts on any single process: budgeting a client margin above 2s would be
#: budgeting for a defect rather than for a cold start.
_CLIENT_START_MARGIN_SECS = 2

#: The wait when the engine publishes no budget at all — an engine too old for
#: `--dump-op-timeouts` ("absent"), or a dump that failed/was malformed ("error"). Not a
#: floor under the derived ceiling: on the "ok" branch the engine's budget is the sole
#: term, and this constant is not consulted.
_NO_BUDGET_FALLBACK_SECS = 10

#: Bound on the one-shot `--dump-op-timeouts` probe. Its own cold start is the whole cost
#: of that spawn, so it is bounded by the same fallback the probe's failure resolves to.
_DUMP_PROBE_TIMEOUT_SECS = _NO_BUDGET_FALLBACK_SECS


def _resolve_op_timeouts(claude_klabauter_root: str, env: dict[str, str], probe_timeout: int) -> None:
    """Resolve the engine's per-op timeout budget map ONCE per process (DEC-1..3).

    Spawns `coordinator_core.invoke --dump-op-timeouts` (capped at `probe_timeout`) and feature-
    detects three outcomes into _OP_TIMEOUTS_STATE, faithfully porting the shell
    transport's _cc_resolve_op_timeouts DEC-2a/2b split:
      "ok"     — dump succeeded; _OP_TIMEOUTS_MAP holds the {op: secs} map (incl. the
                 required "__default__" key).
      "absent" — dump surface not present (older engine repo; argparse "unrecognized" on
                 stderr) — DEC-2a, silent, expected.
      "error"  — surface present but the call failed (timeout / nonzero for another
                 reason / empty / malformed / missing "__default__") — DEC-2b, still
                 falls back to `_NO_BUDGET_FALLBACK_SECS` but earns a once-per-process
                 breadcrumb.

    The DEC-1 dump surface ships server-side today, so the probe always runs — once
    per process, memoized via the `_OP_TIMEOUTS_STATE is not None` guard above, so it
    never doubles the per-op subprocess/CreateProcess spawn count (the single most
    expensive syscall path on Windows) beyond that one-time cost. Older engine
    checkouts that predate the dump surface fall through the DEC-2a "absent" branch
    below (argparse "unrecognized" detection on stderr) — that is the graceful-
    degradation path this function preserves, not a feature flag.
    """
    global _OP_TIMEOUTS_STATE, _OP_TIMEOUTS_MAP
    if _OP_TIMEOUTS_STATE is not None:
        return

    _OP_TIMEOUTS_MAP = {}
    _OP_TIMEOUTS_STATE = "absent"

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "coordinator_core.invoke", "--dump-op-timeouts"],  # popup-safe-env-suppressed
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=probe_timeout,
            env=env,
            cwd=claude_klabauter_root,
            **_no_console_kw(claude_klabauter_root),
        )
    except subprocess.TimeoutExpired:
        # A timeout means the surface responded (or was expected to) and wedged — DEC-2b.
        _OP_TIMEOUTS_STATE = "error"
        return

    if proc.returncode != 0:
        # DEC-2 split: an argparse-style "unrecognized" error is an older engine repo without
        # the dump surface (2a, silent); any other failure shape is a real fault (2b).
        _argparse_absent = any(
            tok in proc.stderr.lower()
            for tok in (
                "unrecognized arguments",
                "unrecognized command",
                "invalid choice",
                "no such option",
                "unknown option",
            )
        )
        _OP_TIMEOUTS_STATE = "absent" if _argparse_absent else "error"
        return

    if not proc.stdout.strip():
        _OP_TIMEOUTS_STATE = "error"
        return

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _OP_TIMEOUTS_STATE = "error"
        return

    # Require a flat {op: number} object carrying the "__default__" key.
    if not isinstance(parsed, dict) or "__default__" not in parsed:
        _OP_TIMEOUTS_STATE = "error"
        return
    coerced: dict[str, float] = {}
    for key, val in parsed.items():
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            _OP_TIMEOUTS_STATE = "error"
            return
        coerced[key] = float(val)

    _OP_TIMEOUTS_MAP = coerced
    _OP_TIMEOUTS_STATE = "ok"


def _op_timeout_ceiling(op: str, claude_klabauter_root: str, env: dict[str, str]) -> int:
    """Per-op timeout ceiling (DEC-1..3): _t = engine_budget(op) + `_CLIENT_START_MARGIN_SECS`.

    The engine's OWN published budget is the only term that varies. The margin is the
    single additive constant covering the client-side cold start the engine's budget
    excludes; falls back to `_NO_BUDGET_FALLBACK_SECS` when the op-budget dump is absent
    or errored (with a once-per-process breadcrumb on error).

    NOTHING IN THE ENVIRONMENT REACHES THIS NUMBER, and that is the point. Both terms
    used to be env knobs — a FLOOR (`CC_INVOKE_TIMEOUT_SECS`) and a MARGIN
    (`CC_INVOKE_CLIENT_MARGIN_SECS`), each unbounded above, each read through a generic
    positive-int reader. A caller in a sibling repo ran a single op with the floor set to
    460 and got a 460s client wait on a shared box; the margin was defended by nothing at
    all. The client's wait now tracks the engine's declared budget and cannot be widened
    from outside the engine.

    Negative-spec (DO NOT reintroduce): no `os.environ` read may re-enter this function
    or `_timeout_exceeded_message`. A narrowing read is not the exception it looks like —
    the same variable that narrows also widens the moment a later edit swaps `min` for
    `max`, which is exactly how the retired FLOOR grew. An op that needs a wider wait
    needs a wider ENGINE budget, declared server-side where a ratchet can see it.

    Ceremony ops need no special case HERE and deliberately do not get one: their 2s
    engine budget arrives through the ordinary `--dump-op-timeouts` read (the engine
    projects every `ceremony.*` op explicitly for exactly this reason), so the formula
    yields 2 + 2 = 4 without knowing anything about ceremonies. The margin still applies
    because it bounds the CLIENT's wait -- cold python startup is the client's problem,
    not the engine's budget -- and collapsing the client wait onto the engine budget
    would kill legitimate cold dispatches. What ceremony ops do get is a different REMEDY
    text; see `_timeout_exceeded_message`.
    """
    global _OP_TIMEOUTS_BREADCRUMB_SHOWN

    _resolve_op_timeouts(claude_klabauter_root, env, _DUMP_PROBE_TIMEOUT_SECS)

    if _OP_TIMEOUTS_STATE == "ok":
        budget = _OP_TIMEOUTS_MAP.get(op, _OP_TIMEOUTS_MAP["__default__"])
        budget_int = int(budget)  # integer-truncate a float budget (e.g. 30.0 -> 30)
        return budget_int + _CLIENT_START_MARGIN_SECS

    if _OP_TIMEOUTS_STATE == "error" and not _OP_TIMEOUTS_BREADCRUMB_SHOWN:
        print(
            f"cc_invoke: op-budget dump failed; waiting {_NO_BUDGET_FALLBACK_SECS}s instead "
            "— an op whose engine budget exceeds that is cut off early",
            file=sys.stderr,
        )
        _OP_TIMEOUTS_BREADCRUMB_SHOWN = True
    return _NO_BUDGET_FALLBACK_SECS


# Stable literal prefix of every TimeoutExpired-derived RuntimeError this module raises
# (both cc_invoke() and cc_invoke_bare()) — the discriminator `is_timeout_error` matches
# on. Kept as a named constant rather than inlined so the two places that must agree on
# it (the builder below and the discriminator) cannot drift independently.
_TIMEOUT_MESSAGE_PREFIX = "cc_invoke: engine timeout after "


def is_timeout_error(exc: BaseException) -> bool:
    """True if `exc` is the TimeoutExpired-derived RuntimeError this module raises.

    Lets a caller distinguish "the op ran past its budget" (never install-related) from
    every other RuntimeError this module's ladder can raise (which may legitimately be
    install-related, e.g. `_engine_wont_start`) WITHOUT re-deriving or duplicating
    `_timeout_exceeded_message`'s text. A caller that appends its own generic "verify
    CLAUDE_KLABAUTER_ROOT / installation" remedy line after any `except RuntimeError` should gate
    that line on `not is_timeout_error(exc)` — see AC7,
    docs/plans/2026-08-08-claim-index-the-commit-gate-never-had.md § C5.
    """
    return isinstance(exc, RuntimeError) and str(exc).startswith(_TIMEOUT_MESSAGE_PREFIX)


def _is_ceremony_op(op: str) -> bool:
    """Client-side mirror of `coordinator_core.ipc.is_ceremony_method`.

    Deliberately a prefix test re-spelled here rather than an import: this module is
    the thin client that runs BEFORE and INSTEAD OF loading the engine — importing
    `coordinator_core.ipc` (which pulls asyncio) to answer a string question would put
    an engine import on the client's own cold path, which is the cost this whole file
    exists to avoid. The duplication is safe because the prefix is the contract: the
    engine budgets by name, so a client that matches by name cannot disagree with it
    about membership, only about the number — and the number is read from the engine's
    own `--dump-op-timeouts`, never guessed here.
    """
    return op.startswith("ceremony.")


def _timeout_exceeded_message(op: str, timeout: int) -> str:
    """Build the TimeoutExpired remedy text — one fact, one alternative, no knob.

    Called AFTER `_op_timeout_ceiling(op, ...)` has already run for this invocation, so
    `_OP_TIMEOUTS_STATE`/`_OP_TIMEOUTS_MAP` are already resolved — no second engine spawn
    here.

    NAMES NO ENV VAR, on any branch. This text used to close by coaching the reader on
    which variable to raise — `CC_INVOKE_TIMEOUT_SECS` for the client wait,
    `COORDINATOR_DISPATCH_TIMEOUT_SECS` for the engine budget — and that advice is what
    the message was actually read for: a timeout became a retry with a bigger number
    instead of a fix, on a box where the retry is itself the load. Naming an override key
    in a guard-shaped message hands the reader the key even when the surrounding sentence
    says it will not work (`docs/wiki/guard-messaging.md` § Register, B6). The client
    ceiling no longer reads the environment at all (see `_op_timeout_ceiling`'s
    negative-spec), so naming those variables would now also be false.

    What survives is the derivation with real numbers — the reader still learns which
    term bound the wait — plus the one remedy that works: reconcile, then make the op
    cheaper. The reconcile line is on EVERY branch, not just ceremony ops: a client-side
    timeout never stops the engine, so any op that mutates may already have landed.

    The degraded branch (dump unavailable) states the ceiling without asserting a budget
    number it could not read.

    The returned text always starts with `_TIMEOUT_MESSAGE_PREFIX` — `is_timeout_error`
    depends on that invariant, on every branch.
    """
    # A ceremony op's budget is a ratchet, not a knob: naming
    # COORDINATOR_DISPATCH_TIMEOUT_SECS here would hand the reader a remedy that
    # provably cannot work (the engine clamps ceremony ops with `min()` AFTER
    # reading that var) and would point them at the one door the ratchet exists
    # to close. The honest remedy for a ceremony breach is the op, not the cap.
    if _is_ceremony_op(op):
        budget_txt = ""
        if _OP_TIMEOUTS_STATE == "ok":
            ceremony_budget = _OP_TIMEOUTS_MAP.get(
                op, _OP_TIMEOUTS_MAP.get("__ceremony_budget__", "")
            )
            if ceremony_budget != "":
                budget_txt = f" against a {ceremony_budget}s ceremony budget"
        return (
            f"{_TIMEOUT_MESSAGE_PREFIX}{timeout}s (op={op}) — "
            f"the ceremony did not complete{budget_txt}\n"
            "  The ceremony budget is a ratchet; no env var widens it. Make the op\n"
            "  cheaper: fewer git spawns, batched pathspecs, a warm path.\n"
            "  The engine does not stop when this client does — a mutating ceremony\n"
            "  may still have committed. Reconcile against real repo state before\n"
            "  re-running.\n"
            "  docs/decisions/DR-348-the-ceremony-budget-is-a-ratchet.md"
        )

    if _OP_TIMEOUTS_STATE == "ok":
        budget = _OP_TIMEOUTS_MAP.get(op, _OP_TIMEOUTS_MAP["__default__"])
        budget_int = int(budget)
        derivation = (
            f"engine budget {budget_int} + {_CLIENT_START_MARGIN_SECS}s client start margin"
        )
    else:
        derivation = "the no-budget fallback (engine op-budget dump unavailable)"
    return (
        f"{_TIMEOUT_MESSAGE_PREFIX}{timeout}s (op={op}) — the op is over budget\n"
        f"  Exceeded {timeout}s = {derivation}.\n"
        "  The client wait is derived from the engine's own budget; nothing outside the\n"
        "  engine widens it. Make the op cheaper: fewer spawns, batched git, a warm path.\n"
        "  The engine does not stop when this client does — a mutating op may still have\n"
        "  landed. Reconcile against real repo state before re-running."
    )


# ---------------------------------------------------------------------------
# Public: cc_invoke(op, params, repo_root) -> dict
# ---------------------------------------------------------------------------

def cc_invoke(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    *,
    _claude_klabauter_root: str | None = None,
    _stderr_sink: list[str] | None = None,
) -> dict[str, Any]:
    """Spawn coordinator_core.invoke and return the bare result dict.

    Fail-closed ladder (rungs 1-3 shared with the retired bash cc_invoke — see the
    module docstring's Port of note; rung 4 is this module's own envelope-parse
    convention — see the module docstring's DR-215 ref):
      (1) Timeout → raise.
      (2) Nonzero process exit → distinguish ImportError (engine-won't-start)
          from op-error → raise either way.
      (3) Empty stdout → raise.
      (4) Parse the JSON-RPC envelope; require top-level 'result' key;
          return the BARE result dict (strips jsonrpc/id/result wrapper).

    Params transport: ALWAYS ``--params-file`` (a tempfile), never argv — matches
    cc_invoke_bare()'s own transport unconditionally, not behind a size threshold.
    Windows `CreateProcess` caps a command line at 32767 characters; a `params`
    dict carrying a `paths` list (e.g. a percolate round's changed-file set) can
    hold thousands of entries and measurably exceeds that before 1000 entries,
    raising `FileNotFoundError: [WinError 206] The filename or extension is too
    long` before the child ever starts (see the dispatch that fixed this: DoE
    percolate-round.py/scoped-git-commit's own `--pathspec-from-file` sibling
    fix, one layer up). A size-threshold branch was considered and rejected: it
    would leave the large-payload path as the rarely-exercised one, which is
    exactly how the argv form survived this long. `--params-file` is already
    unconditional in cc_invoke_bare(); this now matches it rather than
    special-casing "small" callers onto the narrower, capped transport.
    The engine-side receiver (`coordinator_core/invoke/__main__.py`) already
    accepts `--params-file` independently of `--bare` — no positional
    `params_json` argv is ever passed by this function anymore, so mode
    selection (file vs. argv) is unambiguous: the child only ever sees
    `--params-file <path>` for this call convention.

    Args:
        _claude_klabauter_root: already-resolved engine root (forwarded by route() to avoid a
            second resolution on the State-2 path). If None, resolved here via
            _resolve_claude_klabauter_root(). Keyword-only; callers outside route() should omit it.
        _stderr_sink: when provided, the child's captured stderr text is appended to
            this list on the SUCCESS return path (rung 4) if non-empty — lets a caller
            recover diagnostic text a well-formed op-level refusal envelope wrote to
            stderr (e.g. `_setup_error()`'s reason), which would otherwise be discarded
            once rc==0 and stdout parses cleanly. Never consulted on the raise paths
            above (those already fold stderr_text into their own message). Keyword-only;
            most callers omit it.

    Raises:
        RuntimeError: on any transport failure. Never returns legacy after a spawn.
    """
    # An already-resolved root is accepted from route() to avoid a double resolution
    # on the State-2 path.
    claude_klabauter_root = _claude_klabauter_root if _claude_klabauter_root is not None else _resolve_claude_klabauter_root()
    try:
        params_json = json.dumps(params, separators=(",", ":"))
    except TypeError as exc:
        raise RuntimeError(
            f"cc_invoke: params is not JSON-serializable (op={op}): {exc}"
        ) from exc

    # Build subprocess env: pass through os.environ, set COORDINATOR_ENGINE_ROOT, prepend PYTHONPATH.
    # Mirrors _cc_resolve_deps() PYTHONPATH idempotency check in the shell transport.
    env = _build_subprocess_env(claude_klabauter_root)

    # Per-op timeout ceiling (DEC-1..3): _t = engine_budget(op) + _CLIENT_START_MARGIN_SECS,
    # resolved once-per-process from the engine's --dump-op-timeouts map
    # (_NO_BUDGET_FALLBACK_SECS when absent/errored). Shares the ceiling path with
    # cc_invoke_bare so a composite op (e.g. session.boot_sweep, engine budget 30s) never
    # gets a facade timeout tighter than its engine-side DISPATCH_TIMEOUT_SECS budget.
    timeout = _op_timeout_ceiling(op, claude_klabauter_root, env)

    # Spawn invoke with timeout cap.
    # stderr captured to distinguish ImportError from op-error (same purpose as _stderr_tmp in sh).
    rc: int = 0
    stdout_text: str = ""
    stderr_text: str = ""

    # params ride a temp file (--params-file), NOT argv — ARG_MAX-immune (see the
    # docstring's Params transport note above). Written, closed, passed by path,
    # and unlinked in finally so a large payload never overflows argv. Mirrors
    # cc_invoke_bare()'s identical --params-file handling below.
    _params_fd, _params_path = tempfile.mkstemp(prefix="cc-invoke-params-")
    try:
        try:
            _pf = os.fdopen(_params_fd, "w", encoding="utf-8", newline="\n")
        except Exception:
            # fdopen failed before taking ownership of the fd — close it
            # directly or mkstemp's descriptor leaks for the process lifetime.
            os.close(_params_fd)
            raise
        with _pf:
            _pf.write(params_json)
        argv = [
            sys.executable, "-m", "coordinator_core.invoke", op,
            "--params-file", _params_path,
        ]
        if _should_pass_repo(op, claude_klabauter_root):
            argv += ["--repo", repo_root]

        try:
            proc = subprocess.run(
                # Review: cross-slice (DR-148) — sys.executable ensures the same interpreter that
                # loaded cc_invoke.py is used; hardcoded "python3" breaks on Windows.
                argv,  # popup-safe-env-suppressed
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                env=env,
                cwd=claude_klabauter_root,
                **_no_console_kw(claude_klabauter_root),
            )
            rc = proc.returncode
            stdout_text = proc.stdout
            stderr_text = proc.stderr
        except subprocess.TimeoutExpired:
            # (1) Timeout — mirrors the retired bash transport's cs_timeout exit 124 branch.
            raise RuntimeError(_timeout_exceeded_message(op, timeout))
    finally:
        try:
            os.unlink(_params_path)
        except OSError:
            pass

    # (2) Nonzero process exit — distinguish engine-start failure from op-level error.
    # (3) Empty stdout — invoke always produces output on success.
    # Shared fail-closed rungs (used identically by cc_invoke_bare).
    _raise_on_process_failure(rc, stdout_text, stderr_text, op, claude_klabauter_root)

    # (4) Parse the JSON-RPC envelope and extract the bare result object.
    #     Mirrors the inline python3 -c '...' parse in the retired bash transport.
    try:
        envelope = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"cc_invoke: invoke stdout is not valid JSON (op={op}): {exc}"
        ) from exc

    if not isinstance(envelope, dict):
        raise RuntimeError(
            f"cc_invoke: envelope is not a JSON object (op={op}): "
            f"got {type(envelope).__name__!r}"
        )

    # Error envelope: op returned {"error": {...}} with any exit code.
    if "error" in envelope and "result" not in envelope:
        err = envelope["error"]
        if isinstance(err, dict):
            raise RuntimeError(
                f"cc_invoke: op returned JSON-RPC error envelope (op={op}): "
                f"code={err.get('code', '?')} message={err.get('message', '?')}"
            )
        raise RuntimeError(
            f"cc_invoke: op returned JSON-RPC error envelope (op={op}): {err!r}"
        )

    # Missing result key (and no error key detected above).
    if "result" not in envelope:
        top_keys = list(envelope.keys())
        raise RuntimeError(
            f"cc_invoke: envelope missing 'result' key (op={op}): "
            f"top-level keys={top_keys!r}"
        )

    # SUCCESS — return bare result dict.
    # Callers read top-level keys directly (e.g. result['out_path']).
    # NEVER result['result']['X'] — cc_invoke already stripped the wrapper.
    if _stderr_sink is not None and stderr_text.strip():
        _stderr_sink.append(stderr_text)
    return envelope["result"]


# ---------------------------------------------------------------------------
# Public: cc_invoke_bare(op, params, repo_root) -> dict
# ---------------------------------------------------------------------------

def cc_invoke_bare(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    *,
    _claude_klabauter_root: str | None = None,
    _stderr_sink: list[str] | None = None,
) -> dict[str, Any]:
    """Bare-transport spawn of coordinator_core.invoke — the shared Python promotion of
    the retired bash cc_invoke (--bare ladder + DEC-1..3 op-timeout budget; see module Port of note).

    Downstream facades import THIS instead of inlining a per-facade mirror of the shell
    --bare ladder (the campaign anti-goal). Differs from cc_invoke() in three ways, each a
    faithful port of the shell oracle:
      - `--bare`: coordinator_core.invoke emits the BARE result object directly (no
        jsonrpc/id/result envelope), so stdout on rc0 IS the result dict — no envelope
        strip. cc_invoke() uses the non-bare envelope-parse convention.
      - `--params-file`: params ride a temp file, not argv — ARG_MAX-immune on
        Windows/msys, where a ~50KB+ payload overflows a bare argv arg (exit 126 HALT).
      - Per-op timeout ceiling (DEC-1..3): _t = engine_budget(op) +
        _CLIENT_START_MARGIN_SECS for every op, resolved once-per-process from the
        engine's --dump-op-timeouts map; _NO_BUDGET_FALLBACK_SECS when that surface is
        absent (older engine repo) or errored.

    Shares the timeout / nonzero-exit ImportError-vs-op / empty-stdout fail-closed rungs
    with cc_invoke() via _raise_on_process_failure — one ladder, two call conventions.

    Args:
        _claude_klabauter_root: already-resolved engine root (forwarded by route paths to avoid a
            second resolution). Keyword-only; callers outside a router should omit it.
        _stderr_sink: when provided, the child's captured stderr text is appended to
            this list on the SUCCESS return path if non-empty — same purpose as
            cc_invoke()'s param; see its docstring. Keyword-only; most callers omit it.

    Returns the bare result dict on success. Raises RuntimeError on any transport failure;
    NEVER returns legacy after a spawn.
    """
    claude_klabauter_root = _claude_klabauter_root if _claude_klabauter_root is not None else _resolve_claude_klabauter_root()
    try:
        params_json = json.dumps(params, separators=(",", ":"))
    except TypeError as exc:
        raise RuntimeError(
            f"cc_invoke: params is not JSON-serializable (op={op}): {exc}"
        ) from exc
    env = _build_subprocess_env(claude_klabauter_root)

    # Per-op timeout ceiling (DEC-1..3) — may spawn the op-budget dump once per process.
    # Resolved BEFORE the op spawn so the ceiling reflects the engine's budget for this op.
    timeout = _op_timeout_ceiling(op, claude_klabauter_root, env)

    rc: int = 0
    stdout_text: str = ""
    stderr_text: str = ""

    # params ride a temp file (--params-file), NOT argv — ARG_MAX-immune. Written, closed,
    # passed by path, and unlinked in finally so a large payload never overflows argv.
    _params_fd, _params_path = tempfile.mkstemp(prefix="cc-invoke-params-")
    try:
        try:
            _pf = os.fdopen(_params_fd, "w", encoding="utf-8", newline="\n")
        except Exception:
            # fdopen failed before taking ownership of the fd — close it
            # directly or mkstemp's descriptor leaks for the process lifetime.
            os.close(_params_fd)
            raise
        with _pf:
            _pf.write(params_json)
        _argv = [
            sys.executable, "-m", "coordinator_core.invoke", op,
            "--bare", "--params-file", _params_path,
        ]
        if _should_pass_repo(op, claude_klabauter_root):
            _argv += ["--repo", repo_root]
        try:
            proc = subprocess.run(
                _argv,  # popup-safe-env-suppressed
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                env=env,
                cwd=claude_klabauter_root,
                **_no_console_kw(claude_klabauter_root),
            )
            rc = proc.returncode
            stdout_text = proc.stdout
            stderr_text = proc.stderr
        except subprocess.TimeoutExpired:
            # (1) Timeout — mirrors the retired bash transport's cs_timeout exit 124 branch.
            raise RuntimeError(_timeout_exceeded_message(op, timeout))
    finally:
        try:
            os.unlink(_params_path)
        except OSError:
            pass

    # (2) nonzero exit + (3) empty stdout — shared fail-closed rungs.
    _raise_on_process_failure(rc, stdout_text, stderr_text, op, claude_klabauter_root)

    # (4) --bare: stdout IS the bare result object already (no jsonrpc/id/result wrapper,
    #     no second strip-the-envelope spawn). The engine only reaches rc0 on a success
    #     response (a JSON-RPC error always exits nonzero, caught by rung (2)), so on this
    #     path stdout is json.dumps(response["result"]). Parse to a dict for the caller.
    try:
        result = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"cc_invoke: --bare stdout is not valid JSON (op={op}): {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise RuntimeError(
            f"cc_invoke: --bare result is not a JSON object (op={op}): "
            f"got {type(result).__name__!r}"
        )
    if _stderr_sink is not None and stderr_text.strip():
        _stderr_sink.append(stderr_text)
    return result


# ---------------------------------------------------------------------------
# State-1 remediation — W0.5 Option B+C (PM-ratified 2026-07-19): the engine repo
# is a MANDATORY prerequisite of coordinator in every environment. A seam-absent
# route() call is not a legitimate "no engine installed, degrade gracefully"
# outcome anymore — it is a broken install. Prior to this, State-1 silently
# delegated to legacy_fn(), and under the big-bang bash-cutover legacy_fn is
# almost always a thin per-caller stub that raises a generic, non-actionable
# "native seam required (no bash fallback)" message (see e.g.
# the retired bash sweep-shipped-handoffs.sh's _no_fallback). This wraps any legacy_fn
# failure on the seam-absent path with the SAME four-rung remediation ladder
# _resolve_claude_klabauter_root() itself walks, so every caller gets one consistent,
# actionable error instead of N different bespoke stub messages.
# ---------------------------------------------------------------------------

def _state1_remediation_message(
    op: str,
    attempted_claude_klabauter_root: str | None,
    *,
    registry_read_timed_out: bool = False,
) -> str:
    """Build the engine-install-specific remediation text for a State-1 (seam-absent) failure.

    Enumerates the four-rung COORDINATOR_ENGINE_ROOT resolution ladder (mirrors
    _resolve_claude_klabauter_root's own rung order) so an operator sees exactly which
    rung to fix, instead of a bare caller-specific "no fallback wired" message.

    `registry_read_timed_out` (AC1/AC3, default False so the absent-key text
    below is unchanged byte-for-byte — AC2a): when True, `_resolve_claude_klabauter_root`
    raised `_RegistryReadTimeout` rather than genuinely finding no candidate —
    a transient reader timeout, not a missing/unregistered checkout. The
    clone/register remediation below is wrong for that case, so it gets its
    own text instead of sharing the generic one.
    """
    if registry_read_timed_out:
        return (
            f"cc_invoke: native seam resolution unavailable for op={op!r} — "
            f"{_REGISTRY_READ_TIMEOUT_TOKEN} ({_MACHINE_LOCAL_READ_TIMEOUT_SECS}s bound) "
            "while resolving COORDINATOR_ENGINE_ROOT via the machine-local registry, and self-location "
            "also missed.\n"
            "  This machine's declared load norm is 50-70 concurrent LLM sessions "
            "(CLAUDE.md § Load norm); a subprocess-bounded registry read timing out "
            "under that load is expected, not a sign claude-klabauter is unregistered.\n"
            "  Retry the operation."
        )
    root_line = (
        f"  COORDINATOR_ENGINE_ROOT resolved to {attempted_claude_klabauter_root!r} but coordinator_core.invoke "
        "was not importable from it (broken/partial checkout).\n"
        if attempted_claude_klabauter_root
        else "  COORDINATOR_ENGINE_ROOT could not be resolved via any rung below.\n"
    )
    return (
        f"cc_invoke: native seam unavailable for op={op!r} — claude-klabauter is a mandatory "
        "coordinator dependency in every environment (W0.5 Option B+C, 2026-07-19); there is "
        "no bash fallback under the big-bang cutover.\n"
        f"{root_line}"
        "  Resolution ladder (in order):\n"
        "    1. COORDINATOR_ENGINE_ROOT environment variable\n"
        "    2. <settings-home>/machine-local/.claude-klabauter-root pointer file\n"
        "    3. `machine-local get repos.claude_klabauter` registry entry\n"
        "    4. coordinator_core.invoke importable from the resolved root\n"
        "  Remediation: clone claude-klabauter as a sibling repo "
        "(git clone https://github.com/dbc-oduffy/claude-klabauter) and register it — "
        "set $COORDINATOR_ENGINE_ROOT, write the settings-home pointer file, or run "
        "`machine-local set repos.claude_klabauter /path/to/claude-klabauter` — then retry. "
        "See docs/install/AGENT.md § Fail-loud claude-klabauter resolution, or run /coordinator:setup."
    )


# ---------------------------------------------------------------------------
# Public: route(op, params, repo_root, legacy_fn) — two-state gate
# ---------------------------------------------------------------------------

def route(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    legacy_fn: Callable[[], Any],
    *,
    _stderr_sink: list[str] | None = None,
) -> Any:
    """Two-state coordinator_core.invoke router.

    State-1 (seam absent — coordinator_core.invoke not importable via the engine root):
        Call legacy_fn(); its return value passes through unchanged on success.
        If legacy_fn() raises, the exception is wrapped in an engine-install-specific
        remediation RuntimeError (the four-rung engine-root resolution ladder) instead
        of propagating whatever generic message the caller's legacy_fn happened to
        raise (see _state1_remediation_message). No native spawn attempted either way.
        Trigger: the engine root is unresolvable OR find_spec("coordinator_core.invoke") returns None.

    State-2 (seam present — coordinator_core.invoke importable):
        Call cc_invoke(op, params, repo_root); propagate result or exception.
        Transport failure → raise (HARD error). NEVER fall back to legacy_fn on State-2.

    Negative-spec: transport failure after seam-confirmation is NOT a legacy trigger.
    Masking a live-but-broken engine via silent legacy fallback is the anti-pattern this
    design explicitly rejects (DR-215 anti-scope).

    Args:
        _stderr_sink: forwarded to cc_invoke() unchanged (see its docstring); no effect
            on the State-1/legacy_fn path. Keyword-only; most callers omit it.
    """
    # Resolve the engine root; unresolvable root → treat as seam-absent (State-1).
    # Rationale: if the registry doesn't know about the engine repo, the seam is definitely absent.
    claude_klabauter_root: str | None
    _registry_read_timed_out = False
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except _RegistryReadTimeout:
        # Caught ahead of the general RuntimeError below (subclass) — threads the
        # distinguishable outcome (AC1/AC3) to _state1_remediation_message instead
        # of collapsing to the same "unresolvable root" the absent-key case gets.
        claude_klabauter_root = None
        _registry_read_timed_out = True
    except RuntimeError:
        claude_klabauter_root = None

    # Disk-presence gate (State-1 check).
    if claude_klabauter_root is None or not _seam_present(claude_klabauter_root):
        try:
            return legacy_fn()
        except Exception as exc:
            raise RuntimeError(
                _state1_remediation_message(
                    op, claude_klabauter_root, registry_read_timed_out=_registry_read_timed_out
                )
            ) from exc

    # State-2: seam confirmed present — route native; propagate or raise.
    # HARD contract: do NOT catch exceptions and fall to legacy_fn here.
    # Forward the already-resolved claude_klabauter_root to avoid a second _resolve_claude_klabauter_root()
    # call inside cc_invoke() on this path.
    return cc_invoke(op, params, repo_root, _claude_klabauter_root=claude_klabauter_root, _stderr_sink=_stderr_sink)


# ---------------------------------------------------------------------------
# Public: route_mutation(op, params, repo_root, legacy_fn) — mutation-aware transport
# ---------------------------------------------------------------------------

class RouteMutationError(RuntimeError):
    """route_mutation refusal — carries the full offending result payload.

    The raised message alone only carries exit_code and a failed *count*; a
    caller catching this exception (or a human reading a traceback) has no way
    to recover the actual failed-item detail or error text without re-deriving
    it from logs. `.result` gives structured access to the full dict route()
    returned, mirroring the shell oracle's STDOUT PASSTHROUGH contract
    (the retired bash strangler facade's STDOUT PASSTHROUGH contract) where the full captured JSON is always
    re-emitted alongside the refusal.

    `.op_stderr` (default "") carries the child invoke process's captured stderr text,
    when any — this is where a well-formed-but-refusing op (e.g. `_setup_error()`)
    writes its own diagnostic sentence, which a bare exit_code/failed[] inspection of
    `.result` never sees. Folded into the raised message too, so a bare `str(exc)` is
    self-diagnosing without the caller needing to reach for `.op_stderr` explicitly.
    """

    def __init__(self, message: str, result: dict[str, Any], op_stderr: str = "") -> None:
        super().__init__(message)
        self.result = result
        self.op_stderr = op_stderr


def mutation_refusal_message(op: str, result: Any, *, op_stderr: str = "") -> str | None:
    """Return route_mutation's refusal message for `result`, or None if `result`
    carries no in-envelope refusal.

    Extracted from route_mutation's own dict-inspection so a caller that reaches
    the engine via bare `cc_invoke()`/`route()` (not `route_mutation()` — e.g. a
    thin CLI door with no `legacy_fn` to route_mutation's own State-1 gate) can
    still apply the SAME exit_code/failed/error inspection to its own already-
    obtained result, without duplicating the shape-(1)/shape-(2) logic inline at
    each call site (C12, docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md).
    route_mutation() itself now calls this helper — see below — so the two never
    drift apart.
    """
    if not isinstance(result, dict):
        return None

    exit_code = result.get("exit_code")
    exit_code_int: int | None
    # Negative-spec: a non-castable `exit_code` is NOT evidence of success. The
    # retired bash oracle's `int()/except -> 0` fallback was bug-compatibility
    # and is deliberately dropped — coercing it manufactured a false-positive
    # success envelope for every caller of this shared transport at once. A
    # genuine `"0"` string is unaffected (`int("0")` still casts); see
    # `test_exit_code_noncastable_refuses` and its benign sibling
    # `test_exit_code_string_zero_does_not_false_positive`.
    exit_code_uncastable = False
    if exit_code is None:
        exit_code_int = None
    else:
        try:
            exit_code_int = int(exit_code)
        except (TypeError, ValueError):
            exit_code_int = None
            exit_code_uncastable = True

    failed = result.get("failed")
    failed_is_list = isinstance(failed, list)
    failed_count = len(failed) if failed_is_list else 0
    failed_truthy = bool(failed)

    error_field = result.get("error")
    error_text_available = isinstance(error_field, str) and len(error_field) > 0
    error_field_present = exit_code_int in (None, 0) and error_text_available

    if not (
        (exit_code_int is not None and exit_code_int != 0)
        or exit_code_uncastable
        or failed_truthy
        or error_field_present
    ):
        return None

    detail_parts = [f"exit_code={exit_code!r}"]
    if failed_is_list:
        detail_parts.append(f"failed={failed_count}")
    elif failed_truthy:
        detail_parts.append(f"failed={failed!r} (non-list shape)")
    if error_text_available:
        detail_parts.append(f"error={error_field!r}")
    message = f"route_mutation: op={op!r} refused ({', '.join(detail_parts)})"
    if op_stderr:
        message += f"\n  op stderr: {op_stderr}"
    return message


def route_mutation(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    legacy_fn: Callable[[], Any],
) -> Any:
    """Mutation-aware sibling of route() — honors the engine repo's in-envelope exit_code/failed/error.

    Purpose: route() returns the BARE result dict on transport success, but the engine repo's
    op-level refusals (build_setup_error_result -> {"exit_code": 1, ...}; build_act_result
    with partial/total failure -> {"exit_code": 2, "failed": [...]}) live INSIDE that
    result payload with no top-level 'error' key — cc_invoke's envelope ladder only
    raises on transport failure, so a bare route() call returns these refusals UNRAISED.
    route_mutation is the Python sibling of the shell transport's
    strangle_route_mutation() (see module Port of note): after a successful
    route(), it inspects the result for exit_code/failed/error and raises
    RouteMutationError so mutation callers (e.g. cross-repo-memo send) fail loud on an
    op-level refusal instead of proceeding as if the write succeeded. Closes the DR-215
    exit_code trap.

    Two distinct native refusal shapes are caught, mirroring strangle_route_mutation's
    documented two-shape contract:
      (1) {"exit_code": N, ...} with N != 0 — the handoff/memo _err shape.
      (2) {"error": "..."} with exit_code absent or 0 — the completion_ops/plan_ops
          shape (coordinator_core/ops/completion_ops.py, plan ops). This is DISTINCT
          from the top-level JSON-RPC error envelope cc_invoke() already raises on
          (cc_invoke.py's "error" in envelope check operates on the OUTER envelope,
          mutually exclusive with a "result" key being present) — shape (2) here is an
          "error" key nested INSIDE a present "result" payload, which cc_invoke's
          envelope ladder does not see and returns as an ordinary bare result. Without
          this branch, shape (2) would be a silent phantom success.
      The `failed`-list check (not present in the shell oracle) is this helper's own
      addition for build_act_result partial-failure shapes.

    State-1/State-2 gating and transport-fail-raises behavior are inherited unchanged
    from route() — this function only adds a post-hoc inspection of a successful result.

    Raises:
        RouteMutationError (a RuntimeError subclass with a `.result` attribute holding
            the full offending payload): if the result is a dict with a non-None,
            non-zero 'exit_code'; a truthy 'failed'; or a non-empty string 'error' with
            exit_code absent/0. `.op_stderr` carries the child invoke process's own
            stderr text when the refusing op wrote a diagnostic there (e.g.
            `_setup_error()`), and is folded into the raised message too — a well-
            formed refusal envelope's `failed[]` can be empty (nothing per-item to
            report) while stderr still names exactly what went wrong.
    """
    _stderr_sink: list[str] = []
    result = route(op, params, repo_root, legacy_fn, _stderr_sink=_stderr_sink)

    op_stderr = "\n".join(s.strip() for s in _stderr_sink if s.strip())
    message = mutation_refusal_message(op, result, op_stderr=op_stderr)
    if message is not None:
        raise RouteMutationError(message, cast(dict, result), op_stderr=op_stderr)

    return result
