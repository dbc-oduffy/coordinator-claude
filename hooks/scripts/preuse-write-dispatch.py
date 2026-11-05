#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit) doctrine-plane guard shim.

The split: the warm `hook-run` door carries the engine verdict
(`coordinator_core.write_guards`); this shim carries ONLY the doctrine-plane
registry (`_guard_runner.REAL_GUARD_REGISTRY`), run in-process. It resolves,
imports and evaluates no engine code, so one edit pays one cheap interpreter
start with no `coordinator_core` import.

Contract:
  stdin   — PreToolUse JSON (tool_name, tool_input, session_id, cwd, agent_id…)
  stdout  — one hookSpecificOutput JSON envelope on deny/advisory; NOTHING on allow
  exit 0  — always (ALLOW/DENY conveyed via stdout, never exit code)

Graceful degradation — REQUIRED: a registry guard module that fails to import or
raises is skipped (fail-open for that guard only) and one stderr breadcrumb names
it. A missing `_guard_runner.py` degrades the shim to a silent no-op. It must
NEVER brick an edit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _guard_runner import (  # noqa: E402
        REAL_GUARD_REGISTRY as _REAL_GUARD_REGISTRY,
        RegisteredGuard as _RegisteredGuard,
        build_registry_entries as _build_registry_entries,
        run_guards as _run_guards,
        verdict_to_envelope as _verdict_to_envelope,
    )
except Exception:
    # A hook script deployed without its sibling _guard_runner.py must fail open, not crash.
    _RegisteredGuard = None  # type: ignore[assignment]
    _REAL_GUARD_REGISTRY = ()  # type: ignore[assignment]

    def _verdict_to_envelope(result):  # type: ignore[no-redef]
        return None

    def _run_guards(guards, payload, skipped_out=None):  # type: ignore[no-redef]
        return {}

    def _build_registry_entries(registry, raw_payload_text, payload):  # type: ignore[no-redef]
        return []


# The live enrolment set (contract clause 12, `_guard_runner_contract.ENROLLED_GUARD_MODULES`).
# This is the constant main() reads on every edit; a registry change in `_guard_runner.py`
# is inert in production unless it reaches this binding.
_GUARD_REGISTRY: "tuple" = _REAL_GUARD_REGISTRY


def _compose_skipped_guard_breadcrumb(skipped: "list[str]") -> str:
    """Best-effort stderr breadcrumb naming write-guard module(s) that failed to import and
    were skipped (fail-open for those guards only). Pure; main() is the only caller and the
    only place that prints it."""
    return (
        "[preuse-write-dispatch] write-guard module(s) failed to import "
        f"and were skipped (fail-open for those guards only): {', '.join(skipped)}"
    )


def main() -> int:
    raw = sys.stdin.read()

    payload: dict = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}

    # Populated in-place by `_run_guards` for each registry guard that raised.
    _skipped: list[str] = []

    out = None
    try:
        guard_entries: list = []
        if _GUARD_REGISTRY and _RegisteredGuard is not None:
            guard_entries.extend(_build_registry_entries(_GUARD_REGISTRY, raw, payload))
        aggregated = _run_guards(guard_entries, payload, skipped_out=_skipped)
        out = _verdict_to_envelope(aggregated)
    except Exception:
        # Guard-runner failure must never brick the edit.
        out = None

    # Best-effort signal only -- must never affect the ALLOW/DENY decision or the exit code.
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
