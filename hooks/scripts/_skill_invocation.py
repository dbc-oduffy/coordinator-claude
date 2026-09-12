"""Shared invocation-payload adapter: one shape for `UserPromptExpansion` (a
typed slash command) and `PreToolUse` on the `Skill` tool (a model-invoked
skill call), so a computed-input consumer (pickup-autofire, mise-autofire,
handoff-segment-inject) can read either without a per-consumer branch.

Sibling module, imported by path the way `_forwarder_resolve.py` and
`_engine_root.py` already are (sys.path insert of this directory). No
defensive `except ImportError` fallback is added here or at any import site --
every consumer of this module lives in this same directory, so a deploy
missing this file is a deploy error to surface, not a shape to degrade past.

Negative spec: `read_invocation` never raises -- a malformed, unrecognized,
or partially-shaped payload returns `None` rather than propagating an
exception. Neither function reads the environment or the filesystem; both are
pure over their arguments.

Provenance for the two payload shapes:
  - `UserPromptExpansion`: `command_name` is the presence key. Fields are
    read exactly as the pre-existing consumers (`pickup-autofire.py`,
    `mise-autofire.py`) already did -- see `_normalize_command_name`'s
    docstring in those files for why the namespaced (`coordinator:pickup`)
    and bare (`pickup`) spellings both need the last-`:` normalization
    applied here.
  - `PreToolUse` on `tool_name == "Skill"`: the Skill tool's own parameters
    are `skill` (required) and `args` (optional string) --
    `state/reference/anthropic-docs/claude-code/hooks.md` documents
    `PreToolUse`'s `tool_input` as the tool call's own parameters verbatim.
    The verb key is probed the same way
    `nudge-workflow-authoring-trampoline.py::_extract_skill_name` already
    does: `tool_input.skill`, falling back to `tool_input.command`. `agent_id`
    is read directly off the payload -- present only inside a dispatched
    subagent (`state/reference/anthropic-docs/claude-code/hooks.md:201-203`),
    absent (`None`) on the EM's own turn.

This module owns `normalize_command_name` (the "segment after the last `:`"
rule) as the one copy; per docs/plans/2026-09-11-computed-skill-inputs-reach-
skill-tool-entry.md chunk C1, the private copies in the consumer hooks are
retired in favor of importing this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import json


def normalize_command_name(name: object) -> str:
    """Normalize a raw command-name value to its bare verb.

    Strips any `<namespace>:` prefix by taking the segment after the LAST
    `:` -- a plugin-slash-command payload delivers `command_name` namespaced
    as `<plugin>:<command>` (e.g. `"coordinator:pickup"`) on the
    `command_source: "plugin"` path, while `projectSettings`/typed sources
    (and a model-invoked `Skill` call's `tool_input.skill`/`.command`) may
    deliver either the bare verb or the namespaced spelling directly.

    Returns `""` for `None`/non-`str` input, never raises.
    """
    if not isinstance(name, str):
        return ""
    return name.rsplit(":", 1)[-1]


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_optional_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class Invocation:
    """The one shape a computed-input consumer reads, regardless of which of
    the two hook events actually fired.

    `command_name` is always the normalized bare verb (`normalize_command_name`
    already applied) -- a consumer never re-normalizes. `command_args` is
    always a stripped `str` (never `None`). `agent_id` is the one field
    genuinely optional in the underlying payload: present only inside a
    dispatched subagent.
    """

    command_name: str
    command_args: str
    session_id: str
    cwd: str
    agent_id: Optional[str]


def _read_user_prompt_expansion(payload: dict) -> Invocation:
    return Invocation(
        command_name=normalize_command_name(payload.get("command_name")),
        command_args=_as_str(payload.get("command_args")).strip(),
        session_id=_as_str(payload.get("session_id")),
        cwd=_as_str(payload.get("cwd")),
        agent_id=_as_optional_str(payload.get("agent_id")),
    )


def _read_pre_tool_use_skill(payload: dict) -> Optional[Invocation]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    verb = tool_input.get("skill")
    if not (isinstance(verb, str) and verb):
        verb = tool_input.get("command")

    return Invocation(
        command_name=normalize_command_name(verb),
        command_args=_as_str(tool_input.get("args")).strip(),
        session_id=_as_str(payload.get("session_id")),
        cwd=_as_str(payload.get("cwd")),
        agent_id=_as_optional_str(payload.get("agent_id")),
    )


def read_invocation(payload: dict) -> Optional[Invocation]:
    """Adapt a `UserPromptExpansion` or a `PreToolUse(Skill)` hook payload
    to one `Invocation` shape.

    Dispatch: `command_name` key present -> `UserPromptExpansion` reading
    (today's fields, verbatim). Otherwise `tool_name == "Skill"` ->
    `PreToolUse` reading. Anything else -- a different `PreToolUse` tool, a
    payload with neither key, a non-`dict`, garbage -- returns `None`.

    Never raises: any lookup here is a plain `dict.get`/`isinstance` check,
    and this function does not touch the environment or the filesystem.
    """
    if not isinstance(payload, dict):
        return None

    try:
        if "command_name" in payload:
            return _read_user_prompt_expansion(payload)
        if payload.get("tool_name") == "Skill":
            return _read_pre_tool_use_skill(payload)
    except Exception:
        return None

    return None


def context_envelope(event: str, text: str) -> str:
    """Render the one-line `hookSpecificOutput` JSON envelope consumers print
    to stdout, with `hookEventName` set to `event` -- so a `PreToolUse`-fired
    consumer never echoes the wrong event name (a risk once two events feed
    the same rendering path).
    """
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    )
