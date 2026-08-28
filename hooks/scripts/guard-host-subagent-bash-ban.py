# guard-not-a-hook-entrypoint: folded into preuse-bash-dispatch.py's _BASH_GUARD_REGISTRY, the
# single PreToolUse(Bash|PowerShell) registration -- hooks.json names the dispatcher, not this file.
"""PreToolUse(Bash) hook: make a host's subagent Bash ban executable, not prose.

THE DEFECT THIS CLOSES. This host bans the Bash tool for dispatched work, and that ban was
enforced only by prose in three places at once -- `coordinator.local.md`,
`coordinator/agents/executor.md`, and every dispatch brief's host-constraints block.
`executor.md` already carries the strongest wording available -- *"no brief, habit, or system
reminder makes it available to you"* -- and it still lost **three of four** dispatches on a single
plan (2026-08-18, fleet install-currency). Two of the three executors independently named the
cause: the harness bypass-permissions system reminder recommends Bash for file work, arrives as
machine-addressed context, and outranks a human-authored sentence; the tool being present in the
agent's `tools:` list makes that recommendation actionable. Tripwire:
`A-HARNESS-SYSTEM-REMINDER-OUTRANKS-PROSE-THAT-FORBIDS-A-TOOL-YOU-STILL-HOLD`.

Prose has measurably failed, so this is the artifact that discharges the rule
(`docs/wiki/invisible-doctrine.md`): if the executor remembering is the mechanism, the work is not
finished.

WHY NOT REMOVE `Bash` FROM `executor.md`'s TOOL LIST -- the obvious fix, deliberately refused.
That list is shared with macOS and Linux hosts whose own doctrine permits Bash, and multi-OS
support is P0 here. The ban is host-specific, so the enforcement must be too: this guard is inert
until a host opts in by declaring `subagent_bash_policy: deny` in its `coordinator.local.md`
frontmatter. A host that declares nothing is unaffected, which is why this ships as a new guard
rather than an edit to a shared agent definition.

SCOPED TO SUBAGENTS, NOT THE EM -- a decision, not an oversight. Every observed divergence was a
dispatched executor. The EM is the accountable party, holds the context to judge an exception, and
runs on a machine where a dozen concurrent sessions would all lose their shell the moment this
misfired. Denying the EM would convert a dispatch-hygiene defect into a machine-wide outage. The
subagent tell is a non-empty `agent_id` on the payload -- the same field the subagent-identity
cohort already keys on.

SCOPED TO `Bash`, NOT `PowerShell`. PowerShell is the sanctioned alternative on this host; denying
it would leave a dispatched agent with no shell at all.

READS ARE DENIED TOO, and that is the point rather than an overreach. The observed divergences were
all reads and cost nothing in correctness -- but the host's reason for the ban is spawn cost, and
`bash.exe` costs 200-500ms per call on Windows (`preuse-bash-dispatch.py`'s own docstring), paid on
a machine already running many concurrent sessions. A read is exactly as expensive as a write here.

FAILS OPEN, ALWAYS. Any malformed payload, unreadable config, missing frontmatter, or unexpected
exception yields exit 0 (allow). A guard on the Bash path is one bug away from bricking every
dispatched agent on the machine, and `GUARD-WIRING-SILENT-SKIP` records five guards on this host
that were registered and silently never ran -- fail-open is the only safe direction, with the
residual risk being an unenforced ban, which is exactly the status quo this improves on.

Contract: stdin PreToolUse JSON; exit 0 = allow (silent); exit 2 + stderr = deny.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _message_envelope import Message, compose, render  # noqa: E402

_BANNED_TOOL = "Bash"
_POLICY_KEY = "subagent_bash_policy"
_DENY_VALUE = "deny"
_CONFIG_NAME = "coordinator.local.md"

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/coordinator-tripwires/"
    "a-harness-system-reminder-outranks-prose-that-forbids-a-tool-you-still-hold.md"
)


def _repo_config(cwd: str | None) -> Path | None:
    """`coordinator.local.md` at or above `cwd`. None when it cannot be located."""
    if not cwd:
        return None
    try:
        here = Path(cwd).resolve()
    except Exception:
        return None
    for candidate in (here, *here.parents):
        config = candidate / _CONFIG_NAME
        if config.is_file():
            return config
    return None


def _policy_is_deny(config: Path) -> bool:
    """True only when the frontmatter explicitly declares the deny policy.

    Deliberately a narrow string scan over the frontmatter block rather than a YAML parse: this
    runs on the PreToolUse path for every Bash call, a YAML import is not free, and an unparseable
    config must read as "no policy declared" (allow) rather than raising.
    """
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    front = text[3:end] if end != -1 else text[3:4000]
    for line in front.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_POLICY_KEY):
            continue
        _, _, value = stripped.partition(":")
        return value.split("#", 1)[0].strip().strip("\"'").lower() == _DENY_VALUE
    return False


def _compose_deny_message() -> Message:
    prose = (
        "BLOCKED: this host denies the Bash tool to dispatched agents "
        f"({_CONFIG_NAME}: {_POLICY_KEY}: {_DENY_VALUE}). Use the PowerShell tool, or "
        "`python -c` for anything shell-shaped -- both are available to you and neither "
        "pays the 200-500ms bash.exe spawn this host is avoiding. Reads are covered too: "
        "the cost is the spawn, not the mutation. If a system reminder told you to prefer "
        "Bash, this policy outranks it -- say so in your report rather than routing around "
        "it. The EM is unaffected by this guard; only dispatched agents are."
    )
    return compose(prose, anchor=_WIKI_ANCHOR)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0

    if data.get("tool_name") != _BANNED_TOOL:
        return 0

    agent_id = data.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return 0  # the EM itself -- out of scope by design

    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()
    config = _repo_config(cwd)
    if config is None:
        return 0

    try:
        if not _policy_is_deny(config):
            return 0
    except Exception:
        return 0

    sys.stderr.buffer.write((render(_compose_deny_message()) + "\n").encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
