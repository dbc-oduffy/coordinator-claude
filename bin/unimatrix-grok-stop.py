#!/usr/bin/env python3
"""Stop hook: pending agent mail becomes a block reason for this session.

A turn with no prompt id is the session-end or idle ping. That one exits
without reading the spool, so shutting down does not eat a message and does
not keep the process alive. A subagent's stop is not this session's.
"""
from __future__ import annotations

import json
import os
import sys

_BIN = os.path.dirname(os.path.abspath(__file__))
if _BIN not in sys.path:
    sys.path.insert(0, _BIN)

from _unimatrix.adapters.grok import grok_home, take_shown  # noqa: E402


def decide(payload, home=None):
    """Block reason for a completed main-session turn, else None."""
    if not isinstance(payload, dict):
        return None
    if payload.get("subagentType") or payload.get("subagent_type"):
        return None
    if not (payload.get("promptId") or payload.get("prompt_id")):
        return None
    session_id = os.environ.get("GROK_SESSION_ID") or payload.get("session_id") or payload.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None
    text = take_shown(home or grok_home(), session_id)
    if not text:
        return None
    return {"decision": "block", "reason": text}


def main(argv=None):
    del argv
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    decision = decide(payload)
    if decision is not None:
        sys.stdout.write(json.dumps(decision) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
