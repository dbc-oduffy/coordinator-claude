"""Codex context adapter over the existing EM manifest and Unreal notice sources.

The engine classifies the audience and verifies any runtime MCP route. This body
does not register sessions, launch services, mutate roles or infer tool readiness.
"""
from __future__ import annotations
from types import ModuleType

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_PLUGIN = _SCRIPTS.parents[1]


def _load(name, path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _consumer(payload) -> Path | None:
    raw = payload.get("cwd")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        return None
    start = Path(raw)
    return next((p for p in (start, *start.parents) if (p / ".git").exists()), start)


def is_unreal(payload) -> bool:
    consumer = _consumer(payload)
    if consumer is None:
        return False
    shared = _load("codex_unreal_launch_notice", _SCRIPTS / "_unreal_launch_notice.py")
    root = shared._repo_root(str(consumer))
    return bool(root and shared._lib_module("ue_review_signal").declares_unreal_engine(root))


def _read(path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _em_context(payload) -> str:
    # The established manifest owns ordering and the optional repo-only slot.
    manifest = _load("codex_em_manifest", _SCRIPTS / "assert-em-role.py")
    repo = _consumer(payload)
    chunks = []
    for root, relative in manifest._EM_SNIPPET_MANIFEST:
        if root == manifest._ROOT_PLUGIN:
            if relative == "agent-role-em.md":
                relative = "agent-role-em-codex.md"
            text = _read(_PLUGIN / "snippets" / relative)
            if not text:
                text = f"Coordinator EM context unavailable: snippets/{relative}."
        elif repo is not None:
            text = _read(repo / relative)
        else:
            text = ""
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def render_context(payload, role, ue_route=None) -> str:
    """Return audience-specific doctrine; `ue_route` must be live engine proof."""
    if role == "em":
        chunks = [_em_context(payload)]
    elif role in ("worker", "workflow-agent", "reviewer"):
        chunks = [_read(_PLUGIN / "snippets" / "agent-role-worker.md")]
    else:
        chunks = ["Coordinator role is unknown. Follow the assigned task; do not infer EM or top-level workflow authority."]
    chunks.append(f"Coordinator audience: {role}. Use live-peers for exact live identities and route/ACK evidence.")
    if not is_unreal(payload):
        return "\n\n".join(filter(None, chunks))
    shared = _load("codex_unreal_launch_notice", _SCRIPTS / "_unreal_launch_notice.py")
    solution = shared.solution_text(shared.EM_SOLUTION_FILE if role == "em" else shared.AGENT_SOLUTION_FILE)
    if solution:
        chunks.append(solution)
    else:
        chunks.append(shared.UNRELIABLE_LINE)
        chunks.append("UE APIs are arcane: training recall is not evidence. Record the project-rag MCP query, returned source/version, installed-source corroboration and an actually working LSP before UE decisions.")
    if isinstance(ue_route, dict) and ue_route.get("ready") is True and ue_route.get("addon") == "project-rag-ue-addon":
        chunks.append("SOLUTION: project-rag-ue-addon is serving through the configured project-rag MCP route. Use project_rag_instructions and engine_domain_status, then the matching engine/project tools. This confirms the route, not the current project's LSP or every indexed fact.")
    else:
        chunks.append("UE retrieval route not verified for this launch. Report the unavailable route to the operator and project-rag/UE owners; do not substitute training recall, restart shared services or duplicate repair.")
    return "\n\n".join(filter(None, chunks))


def event_advisory(payload, role) -> str:
    """Reuse doctrine text and the pure retrieval-result checker, not Claude logs."""
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        if role == "em":
            return _read(_PLUGIN / "snippets" / "agent-role-em-codex.md")
        return _read(_PLUGIN / "snippets" / "agent-role-worker.md") if role in ("worker", "workflow-agent", "reviewer") else ""
    if event == "PostToolUse":
        checker = _load("codex_project_rag_abort_banner", _SCRIPTS / "project_rag_abort_banner.py")
        # The shared checker suppresses a second Claude banner by reading Claude
        # hook registrations. Those registrations do not prove a native Codex
        # hook exists, so keep this independently loaded checker active here.
        checker.example_game_repo_banner_registered = lambda cwd: False
        normalized = dict(payload)
        response = normalized.get("tool_response")
        if isinstance(response, dict) and response.get("isError") is True:
            normalized.pop("tool_response", None)
            normalized["error"] = response
        return checker.banner_for(normalized)
    return ""
