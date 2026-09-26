from __future__ import annotations

import re

# CS_CANONICAL_AGENT_ID_RE — single source of truth for the bare-hex reviewer-guard
CS_CANONICAL_AGENT_ID_RE = re.compile(r"^[a-f0-9]{12,}$")

_NAMED_TEAMMATE_RE = re.compile(r"^a(.+)-[a-f0-9]{16}$")


def cs_canonical_agent_id_format_ok(agent_id: str) -> bool:
    """Return True iff <agent_id> matches CS_CANONICAL_AGENT_ID_RE.

    Shared predicate -- the reviewer-write guard and the e2e harness both call
    this, so a regex change in CS_CANONICAL_AGENT_ID_RE propagates to all
    callers atomically. Pure function -- no filesystem I/O; safe on the hook
    hot path.
    """
    return bool(CS_CANONICAL_AGENT_ID_RE.match(agent_id or ""))


def cs_build_canonical_agent_id(name: str, short_session: str) -> str:
    """Return the canonical EM-side agent id: "<name>@session-<short_session>".

    SHARED CONTRACT: this is the ONE place where the teammate canonical-id
    format string is constructed. Called ONLY on the subagent-side
    reconstruction path by resolve_subagent_identity (below). The EM-side
    writer (track-dispatched-agents, C1) receives the canonical id
    directly from the harness (tool_response.agent_id) and records it
    verbatim -- it does NOT call this builder.

    Forward-compat caveat: the <name>@session-<short> shape is probe-confirmed
    against harness 2.1.185. A format change must update ALL THREE surfaces:
    (1) this builder, (2) the harness-protocol expectation in
    resolve_subagent_identity, AND (3) the EM-side writer's format guard (the
    @session- value-guard regex at the `^[A-Za-z0-9_.-]+@session-` check).

    Pure function -- no filesystem I/O, no side effects; safe on the hook hot
    path. Raises ValueError when either argument is empty (mirrors the bash
    `${1:?name required}` / `${2:?short_session required}` parameter-expansion
    guard).
    """
    if not name:
        raise ValueError("name required")
    if not short_session:
        raise ValueError("short_session required")
    return f"{name}@session-{short_session}"


def resolve_subagent_identity(agent_id: str, session_id: str) -> str:
    agent_id = agent_id or ""
    session_id = session_id or ""

    if CS_CANONICAL_AGENT_ID_RE.match(agent_id):
        return agent_id

    match = _NAMED_TEAMMATE_RE.match(agent_id)
    if match:
        name = match.group(1)

        if len(session_id) < 8:
            return ""

        short = session_id[:8]
        return cs_build_canonical_agent_id(name, short)

    return ""
