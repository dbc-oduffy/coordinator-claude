#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit) naked-Python dispatcher.

Replaces the former ~10 `bash …/block-*.sh` + `bash …/nudge-*.sh` PreToolUse
registrations with ONE `python3` hook entry — zero Git-Bash cold-starts per edit
(each bash.exe spawn costs 200-500ms on Windows; this is the whole point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): resolve
the claude-klabauter engine, hand it the raw payload, relay its stdout. Claude-klabauter owns the
guard LOGIC (`coordinator_core.write_guards`, which also reuses
`coordinator_core.subagent_sandbox`). The engine is imported and run IN-PROCESS —
no bash, no `python3 -m` subprocess re-spawn — so a whole edit pays exactly one
Python interpreter start.

Contract (mirrors the bash hooks it replaces):
  stdin   — PreToolUse JSON (tool_name, tool_input, session_id, cwd, agent_id…)
  stdout  — one hookSpecificOutput JSON envelope on deny/advisory; NOTHING on allow
  exit 0  — always (ALLOW/DENY conveyed via stdout, never exit code)

Graceful degradation — REQUIRED: any failure to resolve/import/run the claude-klabauter
engine falls through to fail-open ALLOW (exit 0, no stdout). A missing sibling
engine must NEVER brick every edit — identical philosophy to the bash sandbox
shim it supersedes.

NOTE (transition): the legacy bash guards stay registered until hooks.json is
rewired to this dispatcher; both emitting is harmless (the harness aggregates
deny envelopes first-deny-wins), so there is no window with guards down.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

    def _arm_lazy_ops() -> None:
        return None

try:
    from _guard_runner import (  # noqa: E402
        REAL_GUARD_REGISTRY as _REAL_GUARD_REGISTRY,
        RegisteredGuard as _RegisteredGuard,
        build_registry_entries as _build_registry_entries,
        envelope_to_verdict as _envelope_to_verdict,
        run_guards as _run_guards,
        verdict_to_envelope as _verdict_to_envelope,
    )
except Exception:
    # Same defensive-fallback shape as the _engine_root import above -- a
    # missing sibling _guard_runner.py must degrade the runner to a no-op
    # (engine verdict passes through unchanged), never brick the hook.
    _RegisteredGuard = None  # type: ignore[assignment]
    _REAL_GUARD_REGISTRY = ()  # type: ignore[assignment]

    def _envelope_to_verdict(out):  # type: ignore[no-redef]
        return None

    def _verdict_to_envelope(result):  # type: ignore[no-redef]
        return None

    def _run_guards(guards, payload, skipped_out=None):  # type: ignore[no-redef]
        return {}

    def _build_registry_entries(registry, raw_payload_text, payload):  # type: ignore[no-redef]
        return []


# The in-process guard runner's enrolment list (contract clause 12,
# `_guard_runner_contract.ENROLLED_GUARD_MODULES`). C1 built the runner
# MECHANISM with this deliberately empty so the aggregation/lazy-import path
# was structurally exercised (AC1) before any real guard depended on it; C2
# (three guards), C3b (a fourth), and C3 (the fifth, `check-claude-md-size`,
# protocol-translated) proved each guard's parity in turn. C4 is what
# actually points this constant at `_guard_runner.REAL_GUARD_REGISTRY` --
# the live enrolment set -- rather than the placeholder empty tuple: without
# this line, every registry change C2/C3/C3b/C4 made to `_guard_runner.py`
# is inert in production, because THIS is the constant the dispatcher below
# actually reads on every edit.
_GUARD_REGISTRY: "tuple" = _REAL_GUARD_REGISTRY


def _compose_skipped_guard_breadcrumb(skipped: "list[str]") -> str:
    """Best-effort stderr breadcrumb naming write-guard module(s) that
    failed to import and were skipped (fail-open for those guards only).
    Pure -- takes the skipped-name list, returns the string; `main()` is
    the only caller and the only place that prints it."""
    return (
        "[preuse-write-dispatch] write-guard module(s) failed to import "
        f"and were skipped (fail-open for those guards only): {', '.join(skipped)}"
    )


def main() -> int:
    raw = sys.stdin.read()

    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open ALLOW — claude-klabauter unresolvable on this machine

    # Contract clause 8 (SYS.PATH ORDERING, `_guard_runner_contract.py`):
    # the engine root is APPENDED, never inserted at index 0 -- the hooks
    # dir (inserted at index 0 above, before this point) must stay AHEAD
    # of the engine root on sys.path, so a module-name collision between a
    # doctrine-plane-local helper and a same-named engine-side module resolves toward
    # the doctrine-plane-local helper.
    if root not in sys.path:
        sys.path.append(root)

    # Must precede the first coordinator_core.* import -- see
    # _engine_root.arm_lazy_ops for the ~90ms package-init cost this avoids.
    _arm_lazy_ops()

    try:
        from coordinator_core.write_guards.engine import evaluate_payload_json
    except Exception:
        return 0  # engine unimportable → fail-open ALLOW

    # Policy file for the reused subagent_sandbox guard lives at the doctrine-plane plugin root.
    # __file__ parents: [0]=scripts [1]=hooks [2]=coordinator(plugin root)
    policy_path = str(Path(__file__).resolve().parents[2] / "subagent-sandbox-policy.yaml")

    cwd = None
    payload: dict = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            payload = parsed
            cwd = parsed.get("cwd") or None
    except Exception:
        cwd = None
        payload = {}

    # `_skipped` is populated in-place by evaluate_payload_json()'s own
    # discovery pass -- this is the runtime-visible half of the
    # silent-import-failure fix (C12, docs/plans/2026-07-29-hook-fan-in-
    # write-path.md): a guard module that raised on import is otherwise just
    # absent, with nothing to show for it. Sharing the one discovery pass
    # `evaluate_payload_json()` already runs (rather than a second,
    # independent `discover_guard_names()` call) keeps this fold to exactly
    # one `_discover_guards()` invocation per write. The in-process guard
    # runner (below) reuses this SAME list for its own exception isolation
    # (contract clause 11) -- one breadcrumb surface, not two.
    _skipped: list[str] = []
    try:
        out = evaluate_payload_json(raw, policy_path=policy_path, cwd=cwd, skipped_out=_skipped)
    except Exception:
        return 0  # any engine failure → fail-open ALLOW (never brick an edit)

    # In-process guard runner (C1): batches the doctrine-plane-resident write-path
    # guards named in `_GUARD_REGISTRY` into this SAME interpreter, after
    # the engine call, with zero subprocess spawns of its own (AC1). The
    # registry is empty until C2 (next wave) enrols the three residual
    # guards -- this call is still exercised structurally today, and folds
    # cleanly into the same aggregation the engine's own verdict runs
    # through, so the two verdict sources are never reconciled by two
    # separate code paths.
    try:
        engine_verdict = _envelope_to_verdict(out)
        guard_entries: list = [engine_verdict] if engine_verdict else []
        if _GUARD_REGISTRY and _RegisteredGuard is not None:
            guard_entries.extend(_build_registry_entries(_GUARD_REGISTRY, raw, payload))
        aggregated = _run_guards(guard_entries, payload, skipped_out=_skipped)
        merged_out = _verdict_to_envelope(aggregated)
        if merged_out is not None:
            out = merged_out
    except Exception:
        # Guard-runner failure must never override the engine's own
        # verdict, nor brick the edit -- fall through with `out` unchanged.
        pass

    # Best-effort signal only -- must never affect the ALLOW/DENY decision
    # above or this hook's own exit code; any failure here is swallowed.
    try:
        if _skipped:
            print(_compose_skipped_guard_breadcrumb(_skipped), file=sys.stderr)
    except Exception:
        pass

    if out is not None:
        sys.stdout.write(json.dumps(out))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
