#!/usr/bin/env python3
"""cc_invoke — Python-side transport for coordinator_core.invoke.

Port of: coordinator-core-invoke.sh (DoE c6d97219, 2026-07-22) — the bash transport's
fail-closed timeout/nonzero-exit/empty-stdout ladder and DEC-1..3 op-timeout budget
logic are mirrored here deliberately; several comments below note specific behavioral
parity points the port preserved.

Purpose: spawns `sys.executable -m coordinator_core.invoke <op> <params_json> --repo <repo_root>`
with a timeout cap; applies a fail-closed timeout/nonzero-exit/empty-stdout ladder,
then parses the
{jsonrpc,id,result} envelope that is coordinator_core.invoke's default (non---bare)
response shape (see DR-215 ref below). On the route() path, CLAUDE_KLABAUTER_ROOT is resolved ONCE via the native
_resolve_claude_klabauter_root ladder (env var → pointer file → coordinator_core.claude_klabauter_root,
no bash subprocess anywhere) — forwarded to cc_invoke() via _claude_klabauter_root for both the
find_spec gate and the subprocess env (single resolution source).

Public API:
    resolve_colocated_claude_klabauter_root(script_file) -> str
        Self-location-first CLAUDE_KLABAUTER_ROOT resolution for a CLI that lives INSIDE the
        claude-klabauter checkout (coordinator/bin/*.py). Tries Path(script_file)'s
        parents[2] first (probed against coordinator_core/ + pyproject.toml markers);
        falls back to _resolve_claude_klabauter_root()'s machine-local registry ladder only
        when that probe misses (the published/vendored-outside-the-checkout case).

    cc_invoke(op, params, repo_root) -> dict
        Returns the bare result dict on success (jsonrpc/id/result wrapper stripped).
        Raises RuntimeError on ANY transport failure (timeout / ImportError / empty stdout /
        bad envelope / op-error envelope) — except a structural contract-pin failure
        (engine rc=2), which raises the distinct StructuralPinError subclass instead.
        NEVER returns legacy after a native attempt. Uses the non-bare envelope-parse
        call convention (positional params argv).

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
        State-1 seam-absent (find_spec("coordinator_core.invoke") returns None with CLAUDE_KLABAUTER_ROOT
        on sys.path) → call and return legacy_fn(). No native spawn attempted.
        State-2 seam-present → cc_invoke(op, params, repo_root); propagate result or exception.
        Transport failure on the native path → raise (HARD error, never fall to legacy_fn).

    route_mutation(op, params, repo_root, legacy_fn)
        Mutation-aware sibling of route(): calls route(), then raises RouteMutationError
        if the returned dict carries a non-zero 'exit_code', a non-empty 'failed' list, or
        a non-empty string 'error' with exit_code absent/0 — claude-klabauter's op-level refusals
        live INSIDE the result payload with no top-level 'error' key at the ENVELOPE level,
        so bare route() would return them unraised. Python sibling of the shell transport's
        strangle_route_mutation (Port of: strangler-facade.sh, DoE c6d97219, 2026-07-22).

Spec backlink: docs/plans/2026-07-06-strang-08-arm-queue-facade-invoke-retarget.md § C1
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
      third state. Do NOT add one.
    - find_spec is an INTENTIONAL improvement over the retired shell facade's full-import
      probe; do NOT replace it with an execute-import to "match" the old bash behavior.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


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
# Lazy op registration — armed ONCE here, at the shared trampoline seam, so
# every in-process trampoline (all 135 route through _resolve_claude_klabauter_root
# before `from coordinator_core.ops.<name> import main`) has it set before
# coordinator_core.ops is ever imported, killing the ~108ms eager op-module
# load on the cold-trampoline path. Module-top imports above this line are
# stdlib-only (importlib.util, json, os, subprocess, sys, tempfile, typing) —
# no coordinator_core import sits above this line; every coordinator_core
# import in this module is function-local.
# Spec backlink: docs/plans/2026-07-21-retire-coordinator-venv-system-python.md § C8
#
# WHY A `sys` ATTRIBUTE AND NOT `os.environ` (2026-07-28). This used to be
# `os.environ.setdefault(_LAZY_OPS_ENV_KEY, "1")` — a PROCESS-environment
# mutation performed as an import side effect, which every subprocess a caller
# spawned afterwards inherited by default (subprocess.run/Popen with no
# explicit `env=` copies the live os.environ). That was correct for the
# caller's OWN in-process op import — the whole point of arming it — and wrong
# for every OTHER child the caller spawned: 59 test modules in this tree assert
# the op registry at import time, so a spawned pytest run saw a skipped
# eager-import and failed collection on a green tree (commit 5943ec01 patched
# one such site by hand; `child_env()` below generalised the strip). The
# variable was only ever needed as an in-process signal, so it now travels on
# `sys`, which no child inherits by any mechanism. Nothing but this process can
# observe it, which is exactly the scope the flag always wanted.
# Scoping study: docs/research/2026-07-28-lazy-ops-import-side-effect-scope.md § 6 (c).
#
# The conditional preserves the old `setdefault` semantics at this seam: an
# operator who exported COORDINATOR_CORE_LAZY_OPS keeps ownership of the
# decision in both directions. `coordinator_core/ops/__init__.py` reads the
# environment variable first for the same reason.
# ---------------------------------------------------------------------------
_LAZY_OPS_ENV_KEY = "COORDINATOR_CORE_LAZY_OPS"
_LAZY_OPS_SYS_ATTR = "_coordinator_core_lazy_ops"
_LAZY_OPS_INJECTED_BY_THIS_MODULE = _LAZY_OPS_ENV_KEY not in os.environ
if _LAZY_OPS_INJECTED_BY_THIS_MODULE:
    setattr(sys, _LAZY_OPS_SYS_ATTR, True)


def child_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return an env dict safe to pass as `env=` to a spawned child that is
    NOT itself a coordinator_core.invoke dispatch.

    BELT-AND-BRACES since 2026-07-28, no longer load-bearing. This module no
    longer writes COORDINATOR_CORE_LAZY_OPS into `os.environ` (see the channel
    note above), so a child can only inherit the variable when an operator
    exported it — and an operator's explicit choice is precisely what this
    function has always refused to strip. It is kept rather than deleted
    because the environment variable remains a supported operator override, so
    a copy-of-os.environ still has a defined, documented contract here.

    Historically: a plain `os.environ` copy carried the flag into the child
    whenever THIS module was the one that set it, silently making the child's
    own `import coordinator_core.ops` skip eager registration. This returns a
    copy with the key removed in exactly that case; an operator who set the
    variable themselves always keeps their own value, in this process and
    every child of it.

    `overrides`, if given, is applied on top (last-write-wins) after the
    strip — for a caller that wants to add its own env vars to the same
    spawn without a second dict-merge step.

    Callers that DO want the flag to reach the child (nested
    coordinator_core.invoke dispatch) should not use this — see
    `_build_subprocess_env`, which builds that env explicitly instead.
    """
    env = dict(os.environ)
    if _LAZY_OPS_INJECTED_BY_THIS_MODULE:
        env.pop(_LAZY_OPS_ENV_KEY, None)
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
# CLAUDE_KLABAUTER_ROOT resolution — native Python ladder, no bash subprocess.
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


def _machine_local_get(key: str) -> str | None:
    """Read a machine-local registry key via a direct sys.executable subprocess.

    Native Python replacement for the bash `machine-local` forwarder: invokes
    bin/_machine_local.py (the real reader) directly with the same interpreter
    that loaded this module — no shell, no bash. Mirrors
    gen-claude-klabauter-root-pointer.py::_machine_local_get and
    coordinator_core.claude_klabauter_root.coordinator_claude_klabauter_root's own rung-2 lookup.

    Returns the resolved value, or None on any failure (missing impl, non-zero
    exit, empty stdout) — a registry miss is a normal fallback state here, not
    an error; the caller decides whether that's terminal.

    Settings-home first (DR-210 Amendment 2026-07-24): resolves via
    machine_local_impl_resolve.machine_local_impl_path(env_override=None) —
    `env_override=None` preserves this function's pre-existing contract of
    never honouring a MACHINE_LOCAL_IMPL test-isolation override (it never
    did before this precedence fix, and gaining that side effect here would be
    an unrelated behavior change).
    """
    impl = _machine_local_impl_resolver().machine_local_impl_path(env_override=None)
    if not os.path.isfile(impl):
        return None
    try:
        result = subprocess.run(
            [sys.executable, impl, "get", key],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            env=child_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _resolve_claude_klabauter_root() -> str:
    """Resolve CLAUDE_KLABAUTER_ROOT natively — no bash subprocess anywhere in the ladder.

    Resolution order (mirrors coordinator_core.claude_klabauter_root.coordinator_claude_klabauter_root,
    the native port of coordinator-claude-klabauter-root.sh):
      Rung 1:   CLAUDE_KLABAUTER_ROOT already set in environment → fast-path return.
      Rung 1.5: <settings-home>/machine-local/.claude-klabauter-root pointer file → cheap
                direct file read, no subprocess spawn (docs/plans/2026-07-14-
                claude-klabauter-windows-portability.md § C1).
      Rung 2+:  native resolver. coordinator_core.claude_klabauter_root lives INSIDE the
                claude-klabauter checkout this function is trying to locate, so it can't
                be imported before a candidate path is known (the bootstrap
                circularity coordinator-claude-klabauter-root.sh never had, since that
                script lived in THIS repo). Bootstrap the candidate via a direct
                Python subprocess to bin/_machine_local.py (_machine_local_get —
                the same registry lookup coordinator_core.claude_klabauter_root's own
                rung 2 performs, just invoked without a bash intermediary), then
                hand resolution authority to the native module itself for
                byte-identical behavior/remediation text once it's importable.

    Returns the resolved absolute path.
    Raises RuntimeError on failure (unresolvable root).
    """
    # Rung 1: already in environment — same idempotency gate as the shell transport.
    existing = os.environ.get("CLAUDE_KLABAUTER_ROOT", "")
    if existing:
        return existing

    # Rung 1.5 (NEW): cheap direct-file-read pointer, checked ahead of the
    # expensive bash-spawn resolver below. On Windows this avoids spawning a
    # bash subprocess on the per-invoke resolution hot path (fleet-wide
    # hook-latency fix). Plain file read only — never spawns a subprocess.
    # Writer follows reader: the install surface is expected to write
    # <settings-home>/machine-local/.claude-klabauter-root; absence here is a normal
    # fallback state, not an error — falls through to the bash resolver below.
    #
    # Settings-home precedence mirrors _machine_local.py::_settings_home()
    # (Port of: settings-home.sh's _coordinator_settings_home, DoE b644d5a9,
    # 2026-07-22) inline (kept inline here for the same single-file-module
    # reason _machine_local.py documents — no cross-file import hack across
    # the source/install-tree split):
    #   COORDINATOR_SETTINGS_HOME (explicit override) →
    #   ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
    #
    # Spec backlink: docs/plans/2026-07-14-claude-klabauter-windows-portability.md § C1
    _settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or os.path.expanduser("~"),
        ".coordinator-claude-settings",
    )
    _pointer_path = os.path.join(_settings_home, "machine-local", ".claude-klabauter-root")
    try:
        with open(_pointer_path, "r", encoding="utf-8") as _f:
            _pointer_val = _f.read().strip()
        if _pointer_val:
            return _pointer_val
    except OSError:
        pass  # Pointer absent/unreadable — fall through to the bash resolver.

    # Rung 2+: native bootstrap — locate a candidate root via the machine-local
    # registry (no bash), then delegate to coordinator_core.claude_klabauter_root itself
    # once it's importable, so the FINAL answer (and any future rung additions
    # to that module) come from the single native oracle, not a re-derivation
    # duplicated here.
    _remediation = (
        "cc_invoke: cannot resolve CLAUDE_KLABAUTER_ROOT — repos.claude_klabauter is not set.\n"
        "  The machine-local registry has no 'repos.claude_klabauter' entry on this machine.\n"
        "  Remediate (choose one):\n"
        "    machine-local set repos.claude_klabauter /path/to/claude-klabauter\n"
        "    Re-run /coordinator:install to populate the repos.* registry entries.\n"
        "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c"
    )

    _candidate = _machine_local_get("repos.claude_klabauter")
    if not _candidate or not os.path.isdir(_candidate):
        raise RuntimeError(_remediation)

    _injected = _candidate not in sys.path
    if _injected:
        sys.path.insert(0, _candidate)
    try:
        try:
            from coordinator_core.claude_klabauter_root import coordinator_claude_klabauter_root
        except ImportError as exc:
            raise RuntimeError(
                f"cc_invoke: CLAUDE_KLABAUTER_ROOT candidate {_candidate!r} (from machine-local "
                f"repos.claude_klabauter) is not a valid claude-klabauter checkout — "
                f"coordinator_core.claude_klabauter_root not importable: {exc}"
            ) from exc
        resolved = coordinator_claude_klabauter_root()
    finally:
        if _injected:
            try:
                sys.path.remove(_candidate)
            except ValueError:
                pass

    if not resolved:
        raise RuntimeError(_remediation)
    return resolved


def resolve_colocated_claude_klabauter_root(script_file: str) -> str:
    """Resolve CLAUDE_KLABAUTER_ROOT for a CLI that lives INSIDE the claude-klabauter checkout itself.

    Self-location-first ladder for scripts under coordinator/bin/ (e.g. the
    distill-*.py CLIs): those scripts need to find their OWN repo root, which
    `Path(__file__)` answers with zero external dependency and can never be
    "unset" — unlike `_resolve_claude_klabauter_root`'s machine-local registry lookup,
    which exists to resolve a *different* repo across a repo boundary and is a
    manufactured fail-hard dependency for a co-located script.

    Rung 1: `Path(script_file).resolve().parents[2]` — for a script at
            coordinator/bin/X.py, parents[0]=coordinator/bin, parents[1]=coordinator,
            parents[2]=the claude-klabauter root. Accepted only if it probes as a real
            claude-klabauter checkout (has BOTH a coordinator_core/ directory AND a
            pyproject.toml — the same two-marker probe on every caller, so a
            change here can't silently diverge across the six distill CLIs).
    Rung 2: `_resolve_claude_klabauter_root()` (machine-local registry ladder) — only reached
            when rung 1's probe misses, i.e. the script has been published/vendored
            to a location outside its own claude-klabauter checkout (the case the previous
            registry-only resolution was actually trying to cover).

    Raises RuntimeError (via _resolve_claude_klabauter_root's own fail-loud remediation text)
    if BOTH rungs miss.
    """
    _candidate = Path(script_file).resolve().parents[2]
    if (_candidate / "coordinator_core").is_dir() and (_candidate / "pyproject.toml").is_file():
        return str(_candidate)
    return _resolve_claude_klabauter_root()


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

def _read_positive_int_env(name: str, default: int) -> int:
    """Read a positive-int tuning knob from the environment, defaulting on any garbage.

    A malformed timeout/margin knob must never break the transport — defaulting is the
    resilient choice (mirrors the retired bash transport's ${VAR:-N} floors, which silently ignore a
    non-numeric override). Emits a single warn line to stderr when the value is present
    but unusable.
    """
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("non-positive")
    except ValueError:
        print(
            f"warn: cc_invoke: invalid {name}={raw!r}, using default {default}s",
            file=sys.stderr,
        )
        return default
    return value


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
    only coordinator/bin/lib on sys.path, not the claude-klabauter root itself, so the
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


def _build_subprocess_env(claude_klabauter_root: str) -> dict[str, str]:
    """Build the subprocess env for a coordinator_core.invoke spawn.

    Passes os.environ through, sets CLAUDE_KLABAUTER_ROOT, and prepends it to PYTHONPATH only if
    not already present (idempotency fence — mirrors _cc_resolve_deps() in the shell
    transport). Shared by cc_invoke(), cc_invoke_bare(), and the op-budget dump spawn.
    """
    env: dict[str, str] = {**os.environ, "CLAUDE_KLABAUTER_ROOT": claude_klabauter_root}
    existing_pp = env.get("PYTHONPATH", "")
    _sep = os.pathsep
    if f"{_sep}{claude_klabauter_root}{_sep}" not in f"{_sep}{existing_pp}{_sep}":
        env["PYTHONPATH"] = f"{claude_klabauter_root}{_sep}{existing_pp}" if existing_pp else claude_klabauter_root
    return env


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

    (2) Nonzero exit → distinguish, in precedence order: ImportError (engine-won't-start)
        > rc==2 structural contract-pin failure (StructuralPinError, non-self-healing) >
        generic op-level error.
    (3) Empty stdout → invoke always produces output on success.
    """
    if rc != 0:
        _is_import_err = any(
            tok in stderr_text.lower()
            for tok in ("importerror", "modulenotfounderror", "no module named")
        )
        if _is_import_err:
            raise RuntimeError(
                f"cc_invoke: engine will not import/start (op={op}, rc={rc})\n"
                "  ImportError — verify CLAUDE_KLABAUTER_ROOT and coordinator_core installation:\n"
                f"    CLAUDE_KLABAUTER_ROOT={claude_klabauter_root!r}\n"
                f"    stderr: {stderr_text.strip()}"
            )
        if rc == 2:
            raise StructuralPinError(
                f"cc_invoke: structural contract-pin failure (op={op}, rc=2) — "
                "non-self-healing, will recur on retry\n"
                f"  stderr: {stderr_text.strip()}"
            )
        raise RuntimeError(
            f"cc_invoke: invoke process exited {rc} (op={op}) — op or dispatch error\n"
            f"  stderr: {stderr_text.strip()}"
        )

    if not stdout_text.strip():
        raise RuntimeError(
            f"cc_invoke: empty stdout from invoke (op={op}) — invoke produced no output"
        )


def _resolve_op_timeouts(claude_klabauter_root: str, env: dict[str, str], floor: int) -> None:
    """Resolve the engine's per-op timeout budget map ONCE per process (DEC-1..3).

    Spawns `coordinator_core.invoke --dump-op-timeouts` (capped at FLOOR) and feature-
    detects three outcomes into _OP_TIMEOUTS_STATE, faithfully porting the shell
    transport's _cc_resolve_op_timeouts DEC-2a/2b split:
      "ok"     — dump succeeded; _OP_TIMEOUTS_MAP holds the {op: secs} map (incl. the
                 required "__default__" key).
      "absent" — dump surface not present (older claude-klabauter; argparse "unrecognized" on
                 stderr) — DEC-2a, silent, expected.
      "error"  — surface present but the call failed (timeout / nonzero for another
                 reason / empty / malformed / missing "__default__") — DEC-2b, still
                 falls back to flat FLOOR but earns a once-per-process breadcrumb.

    The DEC-1 dump surface ships server-side today, so the probe always runs — once
    per process, memoized via the `_OP_TIMEOUTS_STATE is not None` guard above, so it
    never doubles the per-op subprocess/CreateProcess spawn count (the single most
    expensive syscall path on Windows) beyond that one-time cost. Older claude-klabauter
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
            timeout=floor,
            env=env,
            cwd=claude_klabauter_root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        # A timeout means the surface responded (or was expected to) and wedged — DEC-2b.
        _OP_TIMEOUTS_STATE = "error"
        return

    if proc.returncode != 0:
        # DEC-2 split: an argparse-style "unrecognized" error is an older claude-klabauter without
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
    """Per-op timeout ceiling (DEC-1..3): _t = max(FLOOR, engine_budget(op) + MARGIN).

    FLOOR (CC_INVOKE_TIMEOUT_SECS, default 10) is a floor-only knob — the minimum the
    client will ever wait, NOT a ceiling for override-less ops. MARGIN
    (CC_INVOKE_CLIENT_MARGIN_SECS, default 10) covers cold python startup + import on top
    of the engine's own dispatch budget. Falls back to flat FLOOR when the engine's
    op-budget dump is absent or errored (with a once-per-process breadcrumb on error).
    """
    global _OP_TIMEOUTS_BREADCRUMB_SHOWN
    floor = _read_positive_int_env("CC_INVOKE_TIMEOUT_SECS", 10)
    margin = _read_positive_int_env("CC_INVOKE_CLIENT_MARGIN_SECS", 10)

    _resolve_op_timeouts(claude_klabauter_root, env, floor)

    if _OP_TIMEOUTS_STATE == "ok":
        budget = _OP_TIMEOUTS_MAP.get(op, _OP_TIMEOUTS_MAP["__default__"])
        budget_int = int(budget)  # integer-truncate a float budget (e.g. 30.0 -> 30)
        return max(floor, budget_int + margin)

    if _OP_TIMEOUTS_STATE == "error" and not _OP_TIMEOUTS_BREADCRUMB_SHOWN:
        print(
            "cc_invoke: op-budget dump failed; using flat floor — "
            "overridden ops may hit the client cap",
            file=sys.stderr,
        )
        _OP_TIMEOUTS_BREADCRUMB_SHOWN = True
    return floor


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

    Args:
        _claude_klabauter_root: already-resolved CLAUDE_KLABAUTER_ROOT (forwarded by route() to avoid a
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
    params_json = json.dumps(params, separators=(",", ":"))

    # Build subprocess env: pass through os.environ, set CLAUDE_KLABAUTER_ROOT, prepend PYTHONPATH.
    # Mirrors _cc_resolve_deps() PYTHONPATH idempotency check in the shell transport.
    env = _build_subprocess_env(claude_klabauter_root)

    # Per-op timeout ceiling (DEC-1..3): _t = max(FLOOR, engine_budget(op)+MARGIN),
    # resolved once-per-process from the engine's --dump-op-timeouts map (flat-FLOOR
    # fallback when absent/errored). Shares the ceiling path with cc_invoke_bare so a
    # composite op (e.g. session.boot_sweep, engine budget 30s) never gets a facade
    # timeout tighter than its engine-side DISPATCH_TIMEOUT_SECS budget — the flat
    # CC_INVOKE_TIMEOUT_SECS floor (default 10s) was strangling heavy ops here.
    timeout = _op_timeout_ceiling(op, claude_klabauter_root, env)

    # Spawn invoke with timeout cap.
    # stderr captured to distinguish ImportError from op-error (same purpose as _stderr_tmp in sh).
    rc: int = 0
    stdout_text: str = ""
    stderr_text: str = ""

    argv = [sys.executable, "-m", "coordinator_core.invoke", op, params_json]
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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired:
        # (1) Timeout — mirrors the retired bash transport's cs_timeout exit 124 branch.
        raise RuntimeError(
            f"cc_invoke: engine timeout after {timeout}s (op={op}) — "
            "coordinator_core.invoke did not respond\n"
            f"  Verify CLAUDE_KLABAUTER_ROOT ({claude_klabauter_root!r}) and coordinator_core installation"
        )

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
      - Per-op timeout ceiling (DEC-1..3): _t = max(FLOOR, engine_budget(op)+MARGIN) for
        every op, resolved once-per-process from the engine's --dump-op-timeouts map;
        flat-FLOOR fallback when that surface is absent (older claude-klabauter) or errored.

    Shares the timeout / nonzero-exit ImportError-vs-op / empty-stdout fail-closed rungs
    with cc_invoke() via _raise_on_process_failure — one ladder, two call conventions.

    Args:
        _claude_klabauter_root: already-resolved CLAUDE_KLABAUTER_ROOT (forwarded by route paths to avoid a
            second resolution). Keyword-only; callers outside a router should omit it.
        _stderr_sink: when provided, the child's captured stderr text is appended to
            this list on the SUCCESS return path if non-empty — same purpose as
            cc_invoke()'s param; see its docstring. Keyword-only; most callers omit it.

    Returns the bare result dict on success. Raises RuntimeError on any transport failure;
    NEVER returns legacy after a spawn.
    """
    claude_klabauter_root = _claude_klabauter_root if _claude_klabauter_root is not None else _resolve_claude_klabauter_root()
    params_json = json.dumps(params, separators=(",", ":"))
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
        with os.fdopen(_params_fd, "w", encoding="utf-8") as _pf:
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
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            rc = proc.returncode
            stdout_text = proc.stdout
            stderr_text = proc.stderr
        except subprocess.TimeoutExpired:
            # (1) Timeout — mirrors the retired bash transport's cs_timeout exit 124 branch.
            raise RuntimeError(
                f"cc_invoke: engine timeout after {timeout}s (op={op}) — "
                "coordinator_core.invoke did not respond\n"
                f"  Verify CLAUDE_KLABAUTER_ROOT ({claude_klabauter_root!r}) and coordinator_core installation"
            )
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
# State-1 remediation — W0.5 Option B+C (PM-ratified 2026-07-19): claude-klabauter
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

def _state1_remediation_message(op: str, attempted_claude_klabauter_root: str | None) -> str:
    """Build the claude-klabauter-install-specific remediation text for a State-1 (seam-absent) failure.

    Enumerates the four-rung CLAUDE_KLABAUTER_ROOT resolution ladder (mirrors
    _resolve_claude_klabauter_root's own rung order) so an operator sees exactly which
    rung to fix, instead of a bare caller-specific "no fallback wired" message.
    """
    root_line = (
        f"  CLAUDE_KLABAUTER_ROOT resolved to {attempted_claude_klabauter_root!r} but coordinator_core.invoke "
        "was not importable from it (broken/partial checkout).\n"
        if attempted_claude_klabauter_root
        else "  CLAUDE_KLABAUTER_ROOT could not be resolved via any rung below.\n"
    )
    return (
        f"cc_invoke: native seam unavailable for op={op!r} — claude-klabauter is a mandatory "
        "coordinator dependency in every environment (W0.5 Option B+C, 2026-07-19); there is "
        "no bash fallback under the big-bang cutover.\n"
        f"{root_line}"
        "  Resolution ladder (in order):\n"
        "    1. CLAUDE_KLABAUTER_ROOT environment variable\n"
        "    2. <settings-home>/machine-local/.claude-klabauter-root pointer file\n"
        "    3. `machine-local get repos.claude_klabauter` registry entry\n"
        "    4. coordinator_core.invoke importable from the resolved root\n"
        "  Remediation: clone claude-klabauter as a sibling repo "
        "(git clone https://github.com/dbc-oduffy/claude-klabauter) and register it — "
        "set $CLAUDE_KLABAUTER_ROOT, write the settings-home pointer file, or run "
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

    State-1 (seam absent — coordinator_core.invoke not importable via CLAUDE_KLABAUTER_ROOT):
        Call legacy_fn(); its return value passes through unchanged on success.
        If legacy_fn() raises, the exception is wrapped in a claude-klabauter-install-specific
        remediation RuntimeError (the four-rung CLAUDE_KLABAUTER_ROOT resolution ladder) instead
        of propagating whatever generic message the caller's legacy_fn happened to
        raise (see _state1_remediation_message). No native spawn attempted either way.
        Trigger: CLAUDE_KLABAUTER_ROOT unresolvable OR find_spec("coordinator_core.invoke") returns None.

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
    # Resolve CLAUDE_KLABAUTER_ROOT; unresolvable root → treat as seam-absent (State-1).
    # Rationale: if the registry doesn't know about claude-klabauter, the seam is definitely absent.
    claude_klabauter_root: str | None
    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError:
        claude_klabauter_root = None

    # Disk-presence gate (State-1 check).
    if claude_klabauter_root is None or not _seam_present(claude_klabauter_root):
        try:
            return legacy_fn()
        except Exception as exc:
            raise RuntimeError(_state1_remediation_message(op, claude_klabauter_root)) from exc

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


def route_mutation(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    legacy_fn: Callable[[], Any],
) -> Any:
    """Mutation-aware sibling of route() — honors claude-klabauter's in-envelope exit_code/failed/error.

    Purpose: route() returns the BARE result dict on transport success, but claude-klabauter's
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

    if isinstance(result, dict):
        exit_code = result.get("exit_code")
        # Coerce to int the same way the retired bash oracle did (its
        # inline python3 parser wraps `ec` in int()/except, falling back to 0 on
        # cast failure) — defends against a stringly-typed exit_code producing a
        # Python cross-type false-positive ("0" != 0 is True).
        exit_code_int: int | None
        if exit_code is None:
            exit_code_int = None
        else:
            try:
                exit_code_int = int(exit_code)
            except (TypeError, ValueError):
                exit_code_int = 0

        failed = result.get("failed")
        # `failed` may not be list-shaped on a malformed/future-drifted payload (an
        # int, a bool, ...) — guard with isinstance before len() so an unexpected
        # shape still raises the intended RouteMutationError instead of crashing
        # with an uncaught TypeError.
        failed_is_list = isinstance(failed, list)
        failed_count = len(failed) if failed_is_list else 0
        failed_truthy = bool(failed)

        # The completion_ops/plan_ops error-field refusal shape (see docstring
        # above) only TRIGGERS a refusal when exit_code is absent/0, so it doesn't
        # double-report a shape-(1) refusal as shape-(2) too. `error_text_available`
        # is broader: whenever an 'error' string is present it's folded into the
        # message regardless of which condition triggered the raise, so a shape-(1)
        # refusal carrying an 'error' key alongside its non-zero exit_code doesn't
        # discard that detail either.
        error_field = result.get("error")
        error_text_available = isinstance(error_field, str) and len(error_field) > 0
        error_field_present = exit_code_int in (None, 0) and error_text_available

        if (
            (exit_code_int is not None and exit_code_int != 0)
            or failed_truthy
            or error_field_present
        ):
            detail_parts = [f"exit_code={exit_code!r}"]
            if failed_is_list:
                detail_parts.append(f"failed={failed_count}")
            elif failed_truthy:
                detail_parts.append(f"failed={failed!r} (non-list shape)")
            if error_text_available:
                detail_parts.append(f"error={error_field!r}")
            op_stderr = "\n".join(s.strip() for s in _stderr_sink if s.strip())
            message = f"route_mutation: op={op!r} refused ({', '.join(detail_parts)})"
            if op_stderr:
                message += f"\n  op stderr: {op_stderr}"
            raise RouteMutationError(message, result, op_stderr=op_stderr)

    return result
