"""PostToolUse(Write|Edit|MultiEdit) naked-Python dispatcher for the three
Stop-family write-path advisory guards (C4b,
docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md § C4b) --
`derive-setup-copies.py`, `nudge-initiative-goals-ladder.py`,
`nudge-new-file-zero-budget-ratchets.py`.

Replaces those scripts' standalone `hooks.json` PostToolUse
registrations with ONE `python3` hook entry -- same fan-in motivation as
`preuse-write-dispatch.py`, applied to the sibling event. Doctrine-plane-resident
throughout: none of the three guards import the sibling engine for their own
logic (one uses it only incidentally, via `_resolve_claude_klabauter_root`, for an
"engine leg" path classification -- see `nudge-new-file-zero-budget-
ratchets.py`), so unlike `preuse-write-dispatch.py` this dispatcher never
itself resolves/imports the sibling engine.

Contract:
  stdin   -- PostToolUse JSON (tool_name, tool_input, session_id, cwd, ...)
  stdout  -- NOTHING (this protocol has no stdout envelope -- see below)
  stderr  -- ONE combined blob (contract clause 4, CONCATENATE-ALL) when one
             or more of the three guards fires; nothing otherwise
  exit 2  -- only if this dispatcher declares a protected act in the roster (none does)
  exit 0  -- otherwise: a fired blob goes to the friction log, never to context
             (including any internal failure -- fail-open)

Batches the three guards via `_stop_family_runner.run_registered_stop_family_
guards` -- see `_stop_family_runner_contract.py` for the aggregation rule
this implements (concatenate-all, never first-fires-wins) and why it is a
SIBLING mechanism to `_guard_runner.py`/`preuse-write-dispatch.py`, not an
extension of it.

Graceful degradation -- REQUIRED: any failure to import `_stop_family_
runner` or to parse stdin falls through to fail-open (exit 0, no stderr).
A missing sibling module must never brick a tool call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _stop_family_runner import (  # noqa: E402
        REAL_STOP_FAMILY_REGISTRY as _REAL_STOP_FAMILY_REGISTRY,
        run_registered_stop_family_guards as _run_registered_stop_family_guards,
    )
except Exception:
    # Same defensive-fallback shape every dispatcher in this directory
    # already uses -- a missing sibling module must degrade to a no-op,
    # never crash the hook.
    _REAL_STOP_FAMILY_REGISTRY = ()  # type: ignore[assignment]

    def _run_registered_stop_family_guards(registry, raw_payload_text, payload, skipped_out=None):  # type: ignore[no-redef]
        return 0, ""


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

    _skipped: "list[str]" = []
    try:
        exit_code, text = _run_registered_stop_family_guards(
            _REAL_STOP_FAMILY_REGISTRY, raw, payload, skipped_out=_skipped
        )
    except Exception:
        return 0  # any runner failure -> fail-open (never brick a tool call)

    # Best-effort signal only -- must never affect the exit code above;
    # mirrors preuse-write-dispatch.py's own `_skipped` breadcrumb.
    if _skipped:
        try:
            sys.stderr.write(
                "[postuse-stop-family-dispatch] guard module(s) failed and "
                f"were skipped (fail-open for those guards only): {', '.join(_skipped)}\n"
            )
        except Exception:
            pass

    if text:
        try:
            from _protected_act import protected_act_for, advise_and_record
            if protected_act_for("postuse-stop-family-dispatch.py") is None:
                advise_and_record(
                    "postuse-stop-family-dispatch.py", text, payload.get("hook_event_name") or "PostToolUse"
                )
                return 0
        except Exception:
            pass
        try:
            sys.stderr.buffer.write(text.encode("utf-8"))
            sys.stderr.buffer.write(b"\n")
        except Exception:
            sys.stderr.write(text + "\n")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
