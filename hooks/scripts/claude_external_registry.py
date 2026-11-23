#!/usr/bin/env python3
"""SessionStart/SessionEnd hook: register this Claude session in the engine's external registry.

Runs as a command hook through the `_hook_boot.py` seam, not the warm SessionStart service: the
service cannot see the Claude client ancestor, so the host-process proof (PID + birth time of the
observed `claude` ancestor) must happen in this hook process. The engine module
`coordinator_core.session.external_registry` does the proof and the row write; this script only
resolves the engine through `_engine_root` (the published, stamped claude-klabauter root) and
dispatches on the payload's `hook_event_name`.

Never imports claude-klabauter or adds its path. Fail-open: an unresolved engine, an unreadable
payload or an engine refusal (subagent lifecycle, no Claude ancestor) writes one stderr line and
exits 0, so a registry fault can never cost a session its start.
"""
from __future__ import annotations

import json
import os
import sys

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import _engine_root  # noqa: E402


def _note(msg: str) -> None:
    sys.stderr.write(f"claude-external-registry: {msg}\n")


def run(payload: dict, directory=None) -> str:
    """Apply the payload's lifecycle event to the Claude registry; return a one-word outcome.

    `registered` / `ended` on success; `unresolved` when no engine answers; `skipped` for an event
    this hook does not own. Engine refusals propagate as exceptions to `main`, which fails open.
    `directory` overrides the registry dir (tests); production passes None.
    """
    event = payload.get("hook_event_name")
    if event not in ("SessionStart", "SessionEnd"):
        return "skipped"
    root = _engine_root.resolve_claude_klabauter_root()
    if not root:
        return "unresolved"
    _engine_root.place_engine_root_on_path(root)
    from coordinator_core.session import external_registry

    if event == "SessionStart":
        external_registry.register_claude_current(payload, directory)
        return "registered"
    external_registry.unregister_claude(payload.get("session_id"), directory, payload=payload)
    return "ended"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be an object")
        if run(payload) == "unresolved":
            _note("engine unresolved, session not registered (fetch claude-klabauter)")
    except Exception as exc:
        _note(f"{type(exc).__name__}: {exc}")
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
