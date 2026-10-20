"""guard-agent-model-pin.py -- PreToolUse(Agent) guard: a `model` override that
crosses the tier family of a coordinator agent's own `model:` pin is denied.

Tripwire token: GUARD-AGENT-MODEL-PIN. Hosted by `preuse-agent-dispatch.py`.

Logic (all silent allow unless stated):
  - tool_name != "Agent", or no string `model` in tool_input.
  - `subagent_type` with a "<prefix>:<name>" form resolves only when the prefix
    is "coordinator"; any other prefix is a foreign plugin's persona.
  - `<coordinator dir>/agents/<name>.md` missing, or its frontmatter carries no
    `model:` line (only the first `---` block is read; no YAML load).
  - Either side maps to no tier family (first of opus|sonnet|haiku found as a
    lowercase substring), or both map to the same family.
  - Different families deny, upgrade and downgrade alike, OR reroute: when the
    pinned agent declares `<passed family>-sibling: <bare-agent-name>` and that
    sibling's own file exists with a `model:` pin in the passed family, the
    guard emits `updatedInput` (subagent_type -> coordinator:<sibling>, `model`
    dropped so the sibling's pin governs) plus `additionalContext`, no
    permissionDecision. Fires whether or not the call is nested. No override
    env var: the remedy is a declared sibling or another agent type.

Workflow `agent()` dispatch never traverses PreToolUse(Agent) (branch A of the
plan's AC 12; see coordinator-tripwires/a-workflow-agent-call-bypasses-agent-
tool-pretooluse-hooks.md), so this guard needs no Workflow carve-out.

The Agent tool's input keys are `_named_dispatch_strip._KNOWN_AGENT_TOOL_INPUT_KEYS`;
`effort` is not among them, so only `model` is checked.

Spec: docs/plans/2026-09-22-agent-prompts-that-fabricate-root-causes.md (C2)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _message_envelope import compose, render  # noqa: E402

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/"
    "agent-model-pin-override-block-guard-agent-model-pin.md"
)

_AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"
_FAMILIES = ("opus", "sonnet", "haiku")


def _family(value: str) -> Optional[str]:
    low = value.lower()
    for fam in _FAMILIES:
        if fam in low:
            return fam
    return None


def _resolve_name(raw: object) -> Optional[str]:
    """Bare agent name for a coordinator-owned type, else None."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    if ":" in raw:
        prefix, _, name = raw.partition(":")
        if prefix != "coordinator":
            return None
        raw = name
    if not raw or "/" in raw or "\\" in raw or raw.startswith("."):
        return None
    return raw


def _read_frontmatter_value(name: str, key: str) -> Optional[str]:
    """The first-frontmatter-block `<key>:` value of coordinator/agents/<name>.md, or None."""
    try:
        text = (_AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    except Exception:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        line_key, sep, val = line.partition(":")
        if sep and line_key.strip() == key:
            return val.strip().strip("\"'") or None
    return None


def _read_pin(name: str) -> Optional[str]:
    """The frontmatter `model:` value of coordinator/agents/<name>.md, or None."""
    return _read_frontmatter_value(name, "model")


def _declared_sibling(name: str, passed_family: str) -> Optional[str]:
    """Bare sibling agent name when `name` declares a usable `<passed_family>-sibling`, else None.

    Usable: the value passes `_resolve_name`, its own .md exists, and its `model:` pin maps
    to `passed_family`.
    """
    sibling = _resolve_name(_read_frontmatter_value(name, f"{passed_family}-sibling"))
    if sibling is None:
        return None
    sibling_pin = _read_pin(sibling)
    if sibling_pin is None or _family(sibling_pin) != passed_family:
        return None
    return sibling


def _compose_reroute(name: str, sibling: str, passed: str):
    return compose(
        f"{name} is pinned to another tier than the {passed} the call passed; "
        f"rerouted to coordinator:{sibling}, whose own pin now governs.",
        anchor=_WIKI_ANCHOR,
    )


def _compose_deny(name: str, pin: str, passed: str):
    return compose(
        f"drop `model` (or dispatch an agent type pinned to the tier you need): "
        f"{name} is pinned to {pin}, the call passed {passed}.",
        anchor=_WIKI_ANCHOR,
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    passed = tool_input.get("model")
    if not isinstance(passed, str) or not passed.strip():
        return 0
    name = _resolve_name(tool_input.get("subagent_type"))
    if name is None:
        return 0
    pin = _read_pin(name)
    if pin is None:
        return 0
    pin_family, passed_family = _family(pin), _family(passed)
    if pin_family is None or passed_family is None or pin_family == passed_family:
        return 0
    sibling = _declared_sibling(name, passed_family)
    if sibling is not None:
        rerouted = {k: v for k, v in tool_input.items() if k != "model"}
        rerouted["subagent_type"] = f"coordinator:{sibling}"
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": rerouted,
                "additionalContext": render(_compose_reroute(name, sibling, passed)),
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": render(_compose_deny(name, pin, passed)),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
