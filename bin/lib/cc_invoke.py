#!/usr/bin/env python3
"""cc_invoke — Python-side transport sibling of coordinator-core-invoke.sh cc_invoke.

Purpose: spawns `sys.executable -m coordinator_core.invoke <op> <params_json> --repo <repo_root>`
with a timeout cap; applies the SAME fail-closed envelope-parse ladder as `cc_invoke.sh`
lines 120–221. On the route() path, EXAMPLE_ORCHESTRATION_HUB_ROOT is resolved ONCE via coordinator-example-orchestration-hub-root.sh
subprocess — forwarded to cc_invoke() via _example_orchestration_hub_root for both the find_spec gate and
the subprocess env (single resolution source).

Public API:
    cc_invoke(op, params, repo_root) -> dict
        Returns the bare result dict on success (jsonrpc/id/result wrapper stripped).
        Raises RuntimeError on ANY transport failure (timeout / ImportError / empty stdout /
        bad envelope / op-error envelope). NEVER returns legacy after a native attempt.

    route(op, params, repo_root, legacy_fn)
        State-1 seam-absent (find_spec("coordinator_core.invoke") returns None with EXAMPLE_ORCHESTRATION_HUB_ROOT
        on sys.path) → call and return legacy_fn(). No native spawn attempted.
        State-2 seam-present → cc_invoke(op, params, repo_root); propagate result or exception.
        Transport failure on the native path → raise (HARD error, never fall to legacy_fn).

Spec backlink: docs/plans/2026-07-06-strang-08-arm-queue-facade-invoke-retarget.md § C1
DR-215 ref: coordinator/lib/coordinator-core-invoke.sh (cc_invoke, lines 120–221) is the
            byte-oracle; this module mirrors its spawn shape and fail-closed ladder exactly.

Negative-spec (retired transport patterns — DO NOT reintroduce):
    - The coordinator_core client-module seam is retired (DR-215); this module does NOT
      import or use it.
    - Unix domain sockets are retired (DR-215); this module does NOT open one.
    - IPC authentication tokens are retired (DR-215); this module does NOT read one.
    - This is a TWO-STATE router (seam-present / seam-absent); there is no daemon-aware
      third state. Do NOT add one.
    - find_spec is an INTENTIONAL improvement over the shell facade's full-import probe;
      do NOT replace it with an execute-import to "match" strangler-facade.sh:186.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from typing import Any, Callable


# ---------------------------------------------------------------------------
# EXAMPLE_ORCHESTRATION_HUB_ROOT resolution — single source via coordinator-example-orchestration-hub-root.sh subprocess.
# Exact fidelity with the shell transport: the four-rung discovery ladder inside
# coordinator-example-orchestration-hub-root.sh is the authoritative resolver; we call it, not re-derive it.
# ---------------------------------------------------------------------------

def _resolve_example_orchestration_hub_root() -> str:
    """Resolve EXAMPLE_ORCHESTRATION_HUB_ROOT via coordinator-example-orchestration-hub-root.sh for exact fidelity with the shell ladder.

    Resolution order (mirrors cc_invoke.sh's _cc_resolve_deps → coordinator_example_orchestration_hub_root):
      Rung 1: EXAMPLE_ORCHESTRATION_HUB_ROOT already set in environment → fast-path return.
      Rung 2+: subprocess-call coordinator-example-orchestration-hub-root.sh (sources the script, calls the function).

    Returns the resolved absolute path.
    Raises RuntimeError on failure (unresolvable root).
    """
    # Rung 1: already in environment — same idempotency gate as the shell transport.
    existing = os.environ.get("EXAMPLE_ORCHESTRATION_HUB_ROOT", "")
    if existing:
        return existing

    # Rung 2+: delegate to the shell resolver (four-rung ladder lives there, not here).
    # This file is at coordinator/bin/lib/cc_invoke.py;
    # the resolver is at coordinator/lib/coordinator-example-orchestration-hub-root.sh.
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    # bin/lib/ → bin/ → coordinator/
    _coordinator_root = os.path.dirname(os.path.dirname(_this_dir))
    _resolver = os.path.join(_coordinator_root, "lib", "coordinator-example-orchestration-hub-root.sh")

    if not os.path.isfile(_resolver):
        raise RuntimeError(
            f"cc_invoke: coordinator-example-orchestration-hub-root.sh not found at {_resolver!r}. "
            "This is an install-integrity failure — ensure the coordinator plugin is installed."
        )

    try:
        proc = subprocess.run(
            # Pass resolver path via positional arg to avoid shell-quoting hazards.
            ["bash", "-c", 'source "$1" && coordinator_example_orchestration_hub_root', "--", _resolver],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "cc_invoke: EXAMPLE_ORCHESTRATION_HUB_ROOT resolution timed out (coordinator-example-orchestration-hub-root.sh)"
        ) from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"cc_invoke: EXAMPLE_ORCHESTRATION_HUB_ROOT resolution failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()}"
        )

    resolved = proc.stdout.strip()
    if not resolved:
        raise RuntimeError(
            "cc_invoke: coordinator-example-orchestration-hub-root.sh returned empty path — "
            "check repos.example_orchestration_hub_repo in machine-local registry"
        )
    return resolved


# ---------------------------------------------------------------------------
# Seam gate — disk-presence check via find_spec. Note: find_spec on a dotted name
# imports the parent package (coordinator_core) as a side-effect — sys.path is
# restored after the probe, sys.modules is not. Intentional improvement over the
# shell facade's full-import probe (strangler-facade.sh:186): a broken-but-present
# engine routes native → ImportError → hard error rather than silently falling to
# legacy.
# ---------------------------------------------------------------------------

def _seam_present(example_orchestration_hub_root: str) -> bool:
    """Return True if coordinator_core.invoke is importable from example_orchestration_hub_root.

    Uses importlib.util.find_spec — disk-presence check with a sys.modules side-effect.
    Temporarily injects example_orchestration_hub_root onto sys.path for the probe; restores sys.path on exit.

    Note: find_spec on a dotted name ("coordinator_core.invoke") imports the parent
    package coordinator_core as an internal step when it is not already in sys.modules —
    coordinator_core may remain in sys.modules after this call. Only sys.path is restored.

    Negative-spec: does NOT execute the module or probe liveness; a broken module
    that find_spec can locate routes to the native path and raises hard on import.
    """
    # Review: code-reviewer — F1: find_spec on dotted name imports parent pkg as side-effect;
    # sys.modules is not restored, only sys.path. Docstring corrected.

    # Module-hijack defense-in-depth: the registry-resolved root is trusted, but an
    # un-validated relative or non-directory path on sys.path[0] is the hijack vector —
    # treat it as seam-absent and route to the safe legacy default.
    if not os.path.isabs(example_orchestration_hub_root) or not os.path.isdir(example_orchestration_hub_root):
        return False

    _injected = example_orchestration_hub_root not in sys.path
    if _injected:
        sys.path.insert(0, example_orchestration_hub_root)
    try:
        spec = importlib.util.find_spec("coordinator_core.invoke")
        return spec is not None
    except (ModuleNotFoundError, ValueError):
        return False
    finally:
        if _injected:
            try:
                sys.path.remove(example_orchestration_hub_root)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Public: cc_invoke(op, params, repo_root) -> dict
# ---------------------------------------------------------------------------

def cc_invoke(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    *,
    _example_orchestration_hub_root: str | None = None,
) -> dict[str, Any]:
    """Spawn coordinator_core.invoke and return the bare result dict.

    Mirrors cc_invoke.sh lines 120–221 fail-closed ladder exactly:
      (1) Timeout → raise.
      (2) Nonzero process exit → distinguish ImportError (engine-won't-start)
          from op-error → raise either way.
      (3) Empty stdout → raise.
      (4) Parse the JSON-RPC envelope; require top-level 'result' key;
          return the BARE result dict (strips jsonrpc/id/result wrapper).

    Args:
        _example_orchestration_hub_root: already-resolved EXAMPLE_ORCHESTRATION_HUB_ROOT (forwarded by route() to avoid a
            second resolution on the State-2 path). If None, resolved here via
            _resolve_example_orchestration_hub_root(). Keyword-only; callers outside route() should omit it.

    Raises:
        RuntimeError: on any transport failure. Never returns legacy after a spawn.
    """
    # Review: code-reviewer — F2: read timeout per-call (mirrors shell oracle's laziness);
    # F3: accept already-resolved root from route() to avoid double resolution on State-2 path.
    _raw_timeout = os.environ.get("CC_INVOKE_TIMEOUT_SECS", "10")
    try:
        timeout = int(_raw_timeout)
        if timeout <= 0:
            raise ValueError("non-positive")
    except ValueError:
        print(
            f"warn: cc_invoke: invalid CC_INVOKE_TIMEOUT_SECS={_raw_timeout!r}, using default 10s",
            file=sys.stderr,
        )
        timeout = 10
    example_orchestration_hub_root = _example_orchestration_hub_root if _example_orchestration_hub_root is not None else _resolve_example_orchestration_hub_root()
    params_json = json.dumps(params, separators=(",", ":"))

    # Build subprocess env: pass through os.environ, set EXAMPLE_ORCHESTRATION_HUB_ROOT, prepend PYTHONPATH.
    # Mirrors _cc_resolve_deps() PYTHONPATH idempotency check in the shell transport.
    env: dict[str, str] = {**os.environ, "EXAMPLE_ORCHESTRATION_HUB_ROOT": example_orchestration_hub_root}
    existing_pp = env.get("PYTHONPATH", "")
    if f":{example_orchestration_hub_root}:" not in f":{existing_pp}:":
        env["PYTHONPATH"] = f"{example_orchestration_hub_root}:{existing_pp}" if existing_pp else example_orchestration_hub_root

    # Spawn invoke with timeout cap.
    # stderr captured to distinguish ImportError from op-error (same purpose as _stderr_tmp in sh).
    rc: int = 0
    stdout_text: str = ""
    stderr_text: str = ""

    try:
        proc = subprocess.run(
            # Review: cross-slice (DR-148) — sys.executable ensures the same interpreter that
            # loaded cc_invoke.py is used; hardcoded "python3" breaks on Windows.
            [sys.executable, "-m", "coordinator_core.invoke", op, params_json, "--repo", repo_root],  # popup-safe-env-suppressed
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rc = proc.returncode
        stdout_text = proc.stdout
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired:
        # (1) Timeout — mirrors cs_timeout exit 124 branch in cc_invoke.sh.
        raise RuntimeError(
            f"cc_invoke: engine timeout after {timeout}s (op={op}) — "
            "coordinator_core.invoke did not respond\n"
            f"  Verify EXAMPLE_ORCHESTRATION_HUB_ROOT ({example_orchestration_hub_root!r}) and coordinator_core installation"
        )

    # (2) Nonzero process exit — distinguish engine-start failure from op-level error.
    if rc != 0:
        _is_import_err = any(
            tok in stderr_text
            for tok in ("ImportError", "ModuleNotFoundError", "No module named")
        )
        if _is_import_err:
            raise RuntimeError(
                f"cc_invoke: engine will not import/start (op={op}, rc={rc})\n"
                "  ImportError — verify EXAMPLE_ORCHESTRATION_HUB_ROOT and coordinator_core installation:\n"
                f"    EXAMPLE_ORCHESTRATION_HUB_ROOT={example_orchestration_hub_root!r}\n"
                f"    stderr: {stderr_text.strip()}"
            )
        else:
            raise RuntimeError(
                f"cc_invoke: invoke process exited {rc} (op={op}) — op or dispatch error\n"
                f"  stderr: {stderr_text.strip()}"
            )

    # (3) Empty stdout — invoke always produces output on success.
    # Review: code-reviewer — F7: literal empty test, consistent with shell oracle's
    # post-newline-strip behaviour (bash $() strips trailing newlines only, not all whitespace).
    if not stdout_text:
        raise RuntimeError(
            f"cc_invoke: empty stdout from invoke (op={op}) — invoke produced no output"
        )

    # (4) Parse the JSON-RPC envelope and extract the bare result object.
    #     Mirrors the inline python3 -c '...' parse in cc_invoke.sh lines 182–213.
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
    return envelope["result"]


# ---------------------------------------------------------------------------
# Public: route(op, params, repo_root, legacy_fn) — two-state gate
# ---------------------------------------------------------------------------

def route(
    op: str,
    params: dict[str, Any],
    repo_root: str,
    legacy_fn: Callable[[], Any],
) -> Any:
    """Two-state coordinator_core.invoke router.

    State-1 (seam absent — coordinator_core.invoke not importable via EXAMPLE_ORCHESTRATION_HUB_ROOT):
        Call and return legacy_fn(). No native spawn attempted.
        Trigger: EXAMPLE_ORCHESTRATION_HUB_ROOT unresolvable OR find_spec("coordinator_core.invoke") returns None.

    State-2 (seam present — coordinator_core.invoke importable):
        Call cc_invoke(op, params, repo_root); propagate result or exception.
        Transport failure → raise (HARD error). NEVER fall back to legacy_fn on State-2.

    Negative-spec: transport failure after seam-confirmation is NOT a legacy trigger.
    Masking a live-but-broken engine via silent legacy fallback is the anti-pattern this
    design explicitly rejects (DR-215 anti-scope).
    """
    # Resolve EXAMPLE_ORCHESTRATION_HUB_ROOT; unresolvable root → treat as seam-absent (State-1).
    # Rationale: if the registry doesn't know about example-orchestration-hub, the seam is definitely absent.
    try:
        example_orchestration_hub_root = _resolve_example_orchestration_hub_root()
    except RuntimeError:
        return legacy_fn()

    # Disk-presence gate (State-1 check).
    if not _seam_present(example_orchestration_hub_root):
        return legacy_fn()

    # State-2: seam confirmed present — route native; propagate or raise.
    # HARD contract: do NOT catch exceptions and fall to legacy_fn here.
    # Review: code-reviewer — F3: forward already-resolved example_orchestration_hub_root to avoid a second
    # _resolve_example_orchestration_hub_root() call inside cc_invoke() on this path.
    return cc_invoke(op, params, repo_root, _example_orchestration_hub_root=example_orchestration_hub_root)
