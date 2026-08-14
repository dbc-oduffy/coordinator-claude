# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""append-plan-session.py — plan.append_session native trampoline (DR-216, strang-10).

Purpose: routes plan.append_session through cc_invoke.route_mutation (native-only,
finish-strangler per T2-g1 — the pre-facade legacy body is retired, not a fallback
trigger). Windows de-bash campaign (Category B, shape-(b) per-op trampoline):
replaces the bash forwarder append-plan-session.sh, which sourced
coordinator/lib/strangler-facade.sh (strangle_route_mutation) + coordinator-session.sh.
No shell is spawned by this module (repo-root resolution runs via
repo_identity.resolve_checked_repo_root(), which shells out to `git rev-parse`
via subprocess.run() with an argv list, never through a shell string).

Two-state routing model (inherited from cc_invoke.route()/route_mutation()):
  State 2 (seam present + invoke succeeds) -> native op ran.
  State 3 (seam absent, or seam present + cc_invoke fails, or op-level refusal)
           -> fail-loud, non-zero exit, no plan-file write. NEVER falls back to
              a legacy body.

The docs/plans/ scope constraint (DR-216 D2(iv) noun-confinement) is enforced
server-side by the plan.append_session op itself (completion_ops.py
_append_session_handler: returns {"error": ..., "no_op": true} for any
plan_path outside <worktree>/docs/plans/) — this module does not pre-filter by
path; every path takes the same unconditional native dispatch and the op is the
sole scope adjudicator.

Session-id resolution mirrors tiers 1-3 of the retired coordinator-session.sh's
_cs_resolve_session_id (COORDINATOR_SESSION_ID > CLAUDE_SESSION_ID >
CLAUDE_CODE_SESSION_ID). Tier 4 (the .git/coordinator-sessions/.current-session-id
sentinel + live-session ambiguity guard) is intentionally NOT ported here — this
module's own session-id resolution predates and is independent of
coordinator_session.py's repoint onto js_bridge_cli (that repoint covers the
self-claim helper, not this module's tier-1-3 resolver). Modern
Claude Code (>= ~2.1.150) always sets CLAUDE_CODE_SESSION_ID (tier 3), so this
covers the steady-state case; the sentinel fallback only mattered for old Claude
Code releases without that env var. When unresolved, session_id is sent as JSON
null and the op falls back to its own CLAUDE_CODE_SESSION_ID env read
(completion_ops.py:591-592) — a no-op in that case since tier 3 already tried it.

Spec backlink: DoE-claude:pln-ceremony-as-pipeline-2-land-th-aa5ace
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1b)

Usage (unchanged from the bash facade — zero caller-arg repoints):
    python coordinator/bin/append-plan-session.py <absolute-or-repo-relative-plan-path>

Exit codes (preserved from strangle_route_mutation's contract, strangler-facade.sh):
  0: native op succeeded (write landed, or idempotent no-op).
  N: native op reported {"exit_code": N, ...} with N != 0 (handoff/memo _err shape).
  1: native op reported {"error": "..."} with exit_code absent/0 (completion_ops/plan_ops
     shape), OR git-repo-root resolution failed.
  2: transport failure (seam absent, cc_invoke import/timeout failure) — mirrors the
     retired bash facade's _append_plan_session_seam_absent stand-in (rc=2).

Negative-spec (retired transport patterns — DO NOT reintroduce):
    - No `#!/bin/sh` polyglot header — this is a pure Python entrypoint. Windows
      bare-name invocation is covered by the generated append-plan-session.cmd
      launcher (gen-launcher-shim.py), not a shell shebang trick.
    - Does NOT source coordinator/lib/strangler-facade.sh or coordinator-session.sh
      — cc_invoke.route_mutation() is the sole transport, `_resolve_session_id()`
      below is the sole (partial, tiers-1-3-only) session-id resolver.
    - Does NOT fall back to a direct-write/legacy body on any State-1/2/3 outcome —
      legacy_append_plan_session() below only ever raises.
    - Does NOT assume `coordinator_core` is ambiently importable. Only `bin/lib`
      lands on sys.path from the script dir, so a box without an editable install
      of the engine (and the `~/.coordinator-claude-settings/bin` trampoline, which
      `runpy.run_path`s this file without touching sys.path) died at import time on
      `ModuleNotFoundError: coordinator_core` — advisory-only at the call site, so
      plan<->session links silently stopped being recorded. The engine root is now
      resolved via cc_invoke.ensure_engine_on_path() before the import, and the
      import itself fails OPEN to an inline reproduction of the primitive's
      contract: console suppression is a nicety, and losing it must not take the
      whole CLI down with it. The op dispatch below still fails LOUD (rc=2) when
      the engine is genuinely absent.
"""
from __future__ import annotations

import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)

try:
    from coordinator_core.win_portability import (
        no_console_creationflags as _no_console_creationflags,
    )
except ImportError:  # engine root unresolvable — see the negative-spec block above

    def _no_console_creationflags() -> dict:
        if os.name != "nt":
            return {}
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_SESSION_ID_ENV_TIERS = (
    "COORDINATOR_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
)


def _resolve_session_id() -> str:
    """Tiers 1-3 of the 4-tier chain — see module docstring for the tier-4 carve-out."""
    for var in _SESSION_ID_ENV_TIERS:
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


def _resolve_repo_root() -> str | None:
    """Resolve the current git worktree root via the checked resolver.

    READER classification (DR-277 / plan C5): MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root. Returns None only when
    no root at all could be resolved (caller maps this to exit 1, matching
    the bash oracle's `return 1` on the same failure). UNRESOLVED never
    refuses (AC4).
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    return root


def legacy_append_plan_session() -> None:
    """Fail-loud stand-in for the deleted legacy body (T2-g1 finish-strangler).

    Only reached when coordinator_core.invoke is NOT importable on disk
    (State-1 dispatch target) — route_mutation still requires a legacy_fn
    argument, but the pre-facade bash implementation is gone, so a
    genuinely-absent seam is now a hard error, not a legacy fallback.
    """
    raise RuntimeError(
        "append-plan-session.py: coordinator_core.invoke seam absent — legacy "
        "path removed (T2-g1 finish-strangler); cannot dispatch plan.append_session"
    )


def main(argv: list[str]) -> int:
    plan_path = argv[1] if len(argv) > 1 else ""
    if plan_path and not os.path.isabs(plan_path):
        plan_path = os.path.join(os.getcwd(), plan_path)

    repo_root = _resolve_repo_root()
    if repo_root is None:
        print(
            f"append-plan-session.py: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        return 1

    session_id = _resolve_session_id()
    params = {
        "plan_path": plan_path,
        "session_id": session_id or None,
    }

    try:
        cc_invoke.route_mutation(
            "plan.append_session", params, repo_root, legacy_append_plan_session
        )
    except cc_invoke.RouteMutationError as exc:
        result = exc.result if isinstance(exc.result, dict) else {}
        raw_exit_code = result.get("exit_code")
        try:
            exit_code = int(raw_exit_code) if raw_exit_code is not None else 1
        except (TypeError, ValueError):
            exit_code = 1
        if exit_code == 0:
            exit_code = 1
        print(f"append-plan-session.py: {exc}", file=sys.stderr)
        return exit_code
    except RuntimeError as exc:
        # Transport failure (State-3) or legacy-seam-absent raise (State-1) —
        # both converge on rc=2, mirroring the retired bash facade's
        # _append_plan_session_seam_absent stand-in / cc_invoke's transport-fail rc.
        print(f"append-plan-session.py: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
