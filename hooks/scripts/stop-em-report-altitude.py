#!/usr/bin/env python3
"""Stop-dispatch REGISTRY member #6 -- relays engine op `hooks.em_report_altitude`.

This doctrine-plane repo owns only this thin PLUMBING shim (DR-047
transport-seam carve-out), following the shape `subagent-zero-tool-use-
detect.py` and the other `dispatch_ops_from_hook`-era call sites already
ship: parse the Stop payload, resolve the engine root, relay to the
engine op, and translate its return into this dispatcher's own advisory
channel. The engine owns the decision LOGIC (word-budget/citation-density
measurement, bark-once state) -- see
`coordinator_core/hooks/em_report_altitude.py` in the sibling engine
checkout, NOT built here.

DIVERGENCE FROM THE BRIEF'S LITERAL "dispatch_ops_from_hook" PHRASING: that
engine module's own docstring states plainly it "carries no `@register_op`-
decorated async handler ... Transport here is the DoE-resident stdin/stderr
shim calling `op(payload)` directly" -- it is never entered into
`OP_MODULE_MAP`/the op registry `dispatch_ops_from_hook` resolves against,
so routing through that seam would resolve to a returned
`HookDispatchError` (method not found) on every call, never actually
invoking `op()`. This shim instead imports the engine module directly and
calls `op(payload)`, matching the engine module's own stated contract and
the same in-process (no subprocess) shape every `_engine_root`-gated
sibling in this directory already uses (e.g. `_engine_root.
run_stop_hook_pointer_shim`, which calls `m.op(payload)` the same way for
its own Stop-hook pair) -- a permitted divergence, not a silent one.

Channel (staff-eng review F2/F11): `op()`'s `{"message": ...}` return is
printed to stdout as PLAIN ADVISORY TEXT on the Stop-family channel --
NEVER a JSON `hookSpecificOutput` envelope, which `stop-dispatch.py`'s
concatenate-all aggregation over raw stdout/stderr would mangle into other
guards' plain text. Always exits 0 -- this op is NON-BLOCKING BY
CONSTRUCTION (see the engine module's own docstring) and must never be
routed to the exit-2 Stop-blocking channel.

No-ops (never raises) when the engine root is unresolvable -- the same
fail-open shape every other `_engine_root`-gated entry in `stop-dispatch.py`
already has.

Contract:
  stdin   -- Stop JSON (session_id, transcript_path, cwd, stop_hook_active,
             agent_id, ...)
  stdout  -- the advisory message text, on fire only; NOTHING otherwise
  stderr  -- NOTHING, ever
  exit 0  -- always

Spec: state/dispatch-briefs/2026-08-29-structural-ten-bullet-cap-on-em-messages/C1.md
Engine op: coordinator_core.hooks.em_report_altitude
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a partial
    # deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        root = _resolve_claude_klabauter_root()
    except Exception:
        return 0  # fail-open -- resolver contract is never-raise, belt+braces
    if not root:
        return 0  # fail-open -- engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.hooks import em_report_altitude as _op
    except Exception:
        return 0  # engine unimportable -> fail-open

    try:
        result = _op.op(payload)
    except Exception:
        return 0  # any engine failure -> fail-open (never brick the Stop turn)

    try:
        if result and isinstance(result, dict):
            message = result.get("message")
            if isinstance(message, str) and message:
                sys.stdout.write(message)
                sys.stdout.write("\n")
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
