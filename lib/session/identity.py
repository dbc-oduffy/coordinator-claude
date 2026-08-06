"""identity.py — teammate identity resolution — shared canonical-id contract.

Pure functions — no filesystem I/O, no side effects; safe to import on any
hot path (hook, CLI, or in-process).

Spec backlink: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C7
"""
from __future__ import annotations

import re

# CS_CANONICAL_AGENT_ID_RE — single source of truth for the bare-hex reviewer-guard
# agent_id format predicate. The production guard that once branched on this format
# is retired; its successor does not source this module and has no reference to
# this constant. The sole surviving consumer is the e2e test harness, which
# asserts this constant is populated and format-correct — this is now purely
# an e2e-test invariant for the self-persist reviewer flow, not a production
# dispatch condition.
#
# Format: lowercase hex, >= 12 chars. Probe 0.1 captured 17-char hex ids for
# unnamed agents -- this regex is the de-facto contract the D3 23/0 unit test pins.
# Named-agent ids (produced by cs_build_canonical_agent_id) use a different shape:
#   <name>@session-<short_session> -- those are NOT matched by this predicate.
#
# Spec backlink: docs/plans/2026-06-30-reviewer-findings-self-persist.md § D3, AC4
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
    """Translate a subagent-side agent_id to the canonical EM-side id.

    Returns the empty string on no-match (fail-closed). Three paths:

    (a) Bare hex  ^[a-f0-9]{12,}$  -- unnamed agent fast path. Returns
        agent_id unchanged; session_id is ignored. Byte-identical to the
        bash predecessor's behaviour -- no regression risk for unnamed
        background/foreground dispatches.

    (b) Named teammate  ^a(.+)-[a-f0-9]{16}$  -- strip leading 'a' and
        fixed-length 16-hex suffix to extract <name> (robust even when the
        name contains dashes, e.g. aprobe2-teammate-64cd7f42c270a899 ->
        probe2-teammate). Requires: non-empty extracted name AND session_id
        with >= 8 chars. On success returns
        cs_build_canonical_agent_id(name, session_id[:8]). On failure
        returns the empty string (fail-closed).

    (c) Anything else -> return the empty string (fail-closed).

    Forward-compat caveat: the subagent-side grammar a<name>-<16hex> is
    probe-confirmed against harness 2.1.185. If a future harness changes the
    subagent session_id shape or the a<name>-<16hex> prefix this function
    fails closed (path (c)) rather than silently mapping to a wrong id --
    callers must handle empty as "unknown agent / treat as unnamed". Do NOT
    parse agent_type for the name; the a<name>-<16hex> parse is
    self-contained.

    Pure function -- no filesystem I/O, no side effects; safe on the hook hot
    path.
    """
    agent_id = agent_id or ""
    session_id = session_id or ""

    # (a) Bare hex -- unnamed agent fast path; session_id ignored.
    if CS_CANONICAL_AGENT_ID_RE.match(agent_id):
        return agent_id

    # (b) Named teammate: a<name>-<16hex>
    match = _NAMED_TEAMMATE_RE.match(agent_id)
    if match:
        name = match.group(1)

        # Require session_id with at least 8 chars.
        # (.+) in the regex guarantees non-empty name -- the empty-name branch
        # is unreachable.
        if len(session_id) < 8:
            return ""

        short = session_id[:8]
        return cs_build_canonical_agent_id(name, short)

    # (c) Unrecognised shape -- fail-closed.
    return ""
