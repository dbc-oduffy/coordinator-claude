"""Agy context adapter: the peer-doctrine block only where the install-time seed is absent, plus a hand-edit routing line.

`~/.gemini/GEMINI.md` carries the managed peer-doctrine block when `unimatrix-install`
has run, so `render_context` never repeats it. The engine owns the session sizing and
the nag counter; `event_advisory` returns only a pointer line and never the engine's text.
"""
from __future__ import annotations
from types import ModuleType

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_SEED_MARKER = "BEGIN unimatrix-peer-doctrine"
_EDIT_TOOLS = ("edit_file", "write_file")
_XS_CHANGED_LINES = 30
_NON_CODE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv"}
_ROUTE_LINE = (
    "[em-code-dispatch nudge] Hand edit beyond the XS lane. Route it as an engine ask: "
    "engine_ask.submit with `executor: headless`, then workflow.revise for changes. "
    "See tripwire A-DENIED-XS-EDIT-RE-SIZES-NEVER-HANDS-OFF."
)


def _codex() -> ModuleType:
    spec = importlib.util.spec_from_file_location("agy_codex_adapter", _SCRIPTS / "codex-session-context.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize(payload) -> dict:
    """Map Agy's camelCase payload onto the `cwd` key the shared helpers read."""
    out = dict(payload)
    if not isinstance(out.get("cwd"), str):
        paths = out.get("workspacePaths")
        if isinstance(paths, list) and paths and isinstance(paths[0], str):
            out["cwd"] = paths[0]
    return out


def seed_delivers_block() -> bool:
    """True when Agy's global memory file already holds the managed peer-doctrine block."""
    try:
        return _SEED_MARKER in (Path.home() / ".gemini" / "GEMINI.md").read_text(encoding="utf-8")
    except OSError:
        return False


def render_context(payload, role, ue_route=None) -> str:
    """Return the audience line, plus the doctrine block only when the seed is missing."""
    if not seed_delivers_block():
        return _codex().render_context(normalize(payload), role, ue_route)
    if role not in ("em", "worker", "workflow-agent", "reviewer"):
        return "Coordinator role is unknown. Follow the assigned task; do not infer EM or top-level workflow authority."
    return f"Coordinator audience: {role}. Use live-peers for exact live identities and route/ACK evidence."


def _changed_lines(args) -> int:
    # edit_file carries Replacement, write_file carries Content.
    text = args.get("Replacement") if isinstance(args.get("Replacement"), str) else args.get("Content")
    return text.count("\n") + 1 if isinstance(text, str) and text else 0


def _is_product_code(path) -> bool:
    if not isinstance(path, str) or not path:
        return False
    parts = {p.lower() for p in Path(path.replace("\\", "/")).parts}
    return Path(path.replace("\\", "/")).suffix.lower() not in _NON_CODE_SUFFIXES and not parts & {"scratch", "tmp"}


def event_advisory(payload, role) -> str:
    """Return the routing line for an EM hand edit of product code beyond the XS line budget.

    Agy's payload carries no event name; the host wrapper must set `hook_event_name` before calling.
    """
    if role != "em" or payload.get("hook_event_name") != "PreToolUse":
        return ""
    call = payload.get("toolCall")
    if not isinstance(call, dict) or call.get("name") not in _EDIT_TOOLS:
        return ""
    args = call.get("args")
    if not isinstance(args, dict) or not _is_product_code(args.get("Path")):
        return ""
    return _ROUTE_LINE if _changed_lines(args) > _XS_CHANGED_LINES else ""
