"""Grok context adapter: the peer-doctrine block only where the install-time seed is absent, plus a hand-edit routing line.

Grok hook support and payload shape are unverified; this adapter reads a Claude-shaped
payload (`cwd`, `hook_event_name`, `tool_name`, `tool_input`) and fires only when a host
wrapper supplies one. `$GROK_HOME/rules/unimatrix-peer-doctrine.md` already carries the
block when `unimatrix-install` has run, so `render_context` never repeats it. The engine
owns the sizing and nag counter; `event_advisory` returns only a pointer line.
"""
from __future__ import annotations
from types import ModuleType

import importlib.util
import os
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SEED_MARKER = "BEGIN unimatrix-peer-doctrine"
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "edit_file", "write_file")
_XS_CHANGED_LINES = 30
_NON_CODE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv"}
_ROUTE_LINE = (
    "[em-code-dispatch nudge] Hand edit beyond the XS lane. Route it as an engine ask: "
    "engine_ask.submit with `executor: headless`, then workflow.revise for changes. "
    "See tripwire A-DENIED-XS-EDIT-RE-SIZES-NEVER-HANDS-OFF."
)


def _codex() -> ModuleType:
    spec = importlib.util.spec_from_file_location("grok_codex_adapter", _SCRIPTS / "codex-session-context.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_delivers_block() -> bool:
    """True when Grok's rules directory already holds the managed peer-doctrine block."""
    home = os.environ.get("GROK_HOME")
    root = Path(home) if home else Path.home() / ".grok"
    try:
        return _SEED_MARKER in (root / "rules" / "unimatrix-peer-doctrine.md").read_text(encoding="utf-8")
    except OSError:
        return False


def render_context(payload, role, ue_route=None) -> str:
    """Return the audience line, plus the doctrine block only when the seed is missing."""
    if not seed_delivers_block():
        return _codex().render_context(payload, role, ue_route)
    if role not in ("em", "worker", "workflow-agent", "reviewer"):
        return "Coordinator role is unknown. Follow the assigned task; do not infer EM or top-level workflow authority."
    return f"Coordinator audience: {role}. Use live-peers for exact live identities and route/ACK evidence."


def _changed_lines(args) -> int:
    for key in ("new_string", "Replacement", "content", "Content"):
        text = args.get(key)
        if isinstance(text, str) and text:
            return text.count("\n") + 1
    return 0


def _is_product_code(path) -> bool:
    if not isinstance(path, str) or not path:
        return False
    posix = Path(path.replace("\\", "/"))
    return posix.suffix.lower() not in _NON_CODE_SUFFIXES and not {p.lower() for p in posix.parts} & {"scratch", "tmp"}


def event_advisory(payload, role) -> str:
    """Return the routing line for an EM hand edit of product code beyond the XS line budget."""
    if role != "em" or payload.get("hook_event_name") != "PreToolUse":
        return ""
    if payload.get("tool_name") not in _EDIT_TOOLS:
        return ""
    args = payload.get("tool_input")
    if not isinstance(args, dict):
        return ""
    path = args.get("file_path") or args.get("path") or args.get("Path")
    return _ROUTE_LINE if _is_product_code(path) and _changed_lines(args) > _XS_CHANGED_LINES else ""
